from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from api.dependencies import get_current_user
from api.models import (
    NotebookCreate,
    NotebookDeletePreview,
    NotebookDeleteResponse,
    NotebookResponse,
    NotebookShareCreate,
    NotebookShareResponse,
    NotebookUpdate,
    RecentlyViewedResponse,
    UserSearchResult,
)
from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.notebook import Notebook, NotebookShare, Source
from open_notebook.domain.user import User
from open_notebook.exceptions import (
    InvalidInputError,
    NotFoundError,
    OpenNotebookError,
)

router = APIRouter()

async def _get_owned_notebook(
    notebook_id: str,
    current_user: User,
) -> Notebook:
    """
    It retrieves a notebook only if it belongs to the current user
    It also returns 404 when the notebook exists but belongs to another account, thus avoiding the disclosure of private information
    """
    try:
        notebook = await Notebook.get(notebook_id)
    except NotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Notebook not found",
        )

    if (
        not notebook.owner_id
        or str(notebook.owner_id) != str(current_user.id)
    ):
        raise HTTPException(
            status_code=404,
            detail="Notebook not found",
        )

    return notebook


async def _get_viewable_notebook(
    notebook_id: str,
    current_user: User,
) -> Notebook:
    """
    Retrieves a notebook if the current user can view it: they own it, it's
    public, or their email is on the notebook's share list. This is
    read-only access — every edit/delete endpoint keeps using
    _get_owned_notebook above, which stays strictly owner-only.
    """
    try:
        notebook = await Notebook.get(notebook_id)
    except NotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Notebook not found",
        )

    is_owner = bool(notebook.owner_id) and str(notebook.owner_id) == str(
        current_user.id
    )
    if is_owner or notebook.is_public:
        return notebook

    if current_user.email and await NotebookShare.is_shared_with(
        str(notebook.id), current_user.email
    ):
        return notebook

    raise HTTPException(
        status_code=404,
        detail="Notebook not found",
    )


def _last_viewed_sort_key(item: RecentlyViewedResponse) -> str:
    return item.last_viewed_at


async def _stamp_notebook_view(notebook_id: str) -> None:
    # Best-effort write-on-read: recording the view timestamp must never turn a
    # successful read into a 500. Log and move on if the stamp update fails.
    try:
        await repo_query(
            "UPDATE $notebook_id SET last_viewed_at = time::now();",
            {"notebook_id": ensure_record_id(notebook_id)},
        )
    except Exception as e:
        logger.warning(
            f"Failed to stamp last_viewed_at for notebook {notebook_id}: {e}"
        )


def _recently_viewed_notebook(row: dict) -> RecentlyViewedResponse:
    return RecentlyViewedResponse(
        type="notebook",
        id=str(row.get("id", "")),
        title=row.get("title") or row.get("name") or "Untitled notebook",
        last_viewed_at=str(row.get("last_viewed_at", "")),
    )


def _recently_viewed_source(row: dict) -> RecentlyViewedResponse:
    return RecentlyViewedResponse(
        type="source",
        id=str(row.get("id", "")),
        title=row.get("title") or "Untitled source",
        last_viewed_at=str(row.get("last_viewed_at", "")),
    )


@router.get("/notebooks", response_model=List[NotebookResponse])
async def get_notebooks(
    archived: Optional[bool] = Query(None, description="Filter by archived status"),
    order_by: str = Query("updated desc", description="Order by field and direction"),
    current_user: User = Depends(get_current_user),
):
    """Get all notebooks with optional filtering and ordering."""
    try:
        # Validate order_by against allowlist to prevent SurrealQL injection
        allowed_fields = {"name", "created", "updated"}
        allowed_directions = {"asc", "desc"}

        parts = order_by.strip().lower().split()
        if len(parts) == 1:
            if parts[0] not in allowed_fields:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid order_by field: '{order_by}'. Allowed fields: {', '.join(sorted(allowed_fields))}",
                )
            validated_order_by = parts[0]
        elif len(parts) == 2:
            if parts[0] not in allowed_fields or parts[1] not in allowed_directions:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid order_by: '{order_by}'. Allowed fields: {', '.join(sorted(allowed_fields))}. Allowed directions: asc, desc",
                )
            validated_order_by = f"{parts[0]} {parts[1]}"
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid order_by format: '{order_by}'. Expected 'field' or 'field direction'",
            )

        # Build the query with counts
        query = f"""
            SELECT *,
            count(<-reference.in) as source_count,
            count(<-artifact.in) as note_count
            FROM notebook
            WHERE owner_id = $owner_id
            ORDER BY {validated_order_by}
        """

        assert current_user.id is not None
        result = await repo_query(
            query,
            {"owner_id": ensure_record_id(current_user.id)},
        )

        # Filter by archived status if specified
        if archived is not None:
            result = [nb for nb in result if nb.get("archived") == archived]

        return [
            NotebookResponse(
                id=str(nb.get("id", "")),
                name=nb.get("name", ""),
                description=nb.get("description", ""),
                archived=nb.get("archived", False),
                is_public=nb.get("is_public", False),
                created=str(nb.get("created", "")),
                updated=str(nb.get("updated", "")),
                source_count=nb.get("source_count", 0),
                note_count=nb.get("note_count", 0),
            )
            for nb in result
        ]
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error fetching notebooks: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching notebooks: {str(e)}"
        )


@router.post("/notebooks", response_model=NotebookResponse)
async def create_notebook(
    notebook: NotebookCreate,
    current_user: User = Depends(get_current_user),
):
    """Create a new notebook."""
    try:
        new_notebook = Notebook(
            name=notebook.name,
            description=notebook.description,
            owner_id=current_user.id,
        )
        await new_notebook.save()

        return NotebookResponse(
            id=new_notebook.id or "",
            name=new_notebook.name,
            description=new_notebook.description,
            archived=new_notebook.archived or False,
            created=str(new_notebook.created),
            updated=str(new_notebook.updated),
            source_count=0,  # New notebook has no sources
            note_count=0,  # New notebook has no notes
        )
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error creating notebook: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error creating notebook: {str(e)}"
        )


@router.get("/recently-viewed", response_model=List[RecentlyViewedResponse])
async def get_recently_viewed(
    limit: int = Query(12, ge=1, le=50, description="Number of items to return"),
    current_user: User = Depends(get_current_user),
):
    """Get recently viewed notebooks and sources, newest first."""
    try:
        assert current_user.id is not None
        notebooks = await repo_query(
            """
            SELECT id, name AS title, last_viewed_at
            FROM notebook
            WHERE owner_id = $owner_id
              AND last_viewed_at != NONE
              AND last_viewed_at != NULL
            ORDER BY last_viewed_at DESC
            LIMIT $limit
            """,
            {
                "limit": limit,
                "owner_id": ensure_record_id(current_user.id),
            },
        )
        sources = await repo_query(
            """
            SELECT id, title, last_viewed_at
            FROM source
            WHERE last_viewed_at != NONE AND last_viewed_at != NULL
            ORDER BY last_viewed_at DESC
            LIMIT $limit
            """,
            {"limit": limit},
        )

        items = [
            *[_recently_viewed_notebook(nb) for nb in notebooks],
            *[_recently_viewed_source(src) for src in sources],
        ]
        items.sort(key=_last_viewed_sort_key, reverse=True)
        return items[:limit]
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        # Log full context server-side; return a generic message so internal
        # details are not leaked to clients.
        logger.exception(f"Error fetching recently viewed items: {e}")
        raise HTTPException(
            status_code=500, detail="Error fetching recently viewed items"
        )


@router.get(
    "/notebooks/{notebook_id}/delete-preview", response_model=NotebookDeletePreview
)
async def get_notebook_delete_preview(
    notebook_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get a preview of what will be deleted when this notebook is deleted."""
    try:
        notebook = await _get_owned_notebook(notebook_id, current_user)

        preview = await notebook.get_delete_preview()

        return NotebookDeletePreview(
            notebook_id=str(notebook.id),
            notebook_name=notebook.name,
            note_count=preview["note_count"],
            exclusive_source_count=preview["exclusive_source_count"],
            shared_source_count=preview["shared_source_count"],
        )
    except HTTPException:
        raise
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Notebook not found")
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error getting delete preview for notebook {notebook_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching notebook deletion preview: {str(e)}",
        )


@router.get("/notebooks/{notebook_id}", response_model=NotebookResponse)
async def get_notebook(
    notebook_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get a specific notebook by ID."""
    try:
        await _get_viewable_notebook(notebook_id, current_user)
                
        # Query with counts for single notebook
        query = """
            SELECT *,
            count(<-reference.in) as source_count,
            count(<-artifact.in) as note_count
            FROM $notebook_id
        """
        result = await repo_query(query, {"notebook_id": ensure_record_id(notebook_id)})

        if not result:
            raise HTTPException(status_code=404, detail="Notebook not found")

        await _stamp_notebook_view(notebook_id)

        nb = result[0]
        return NotebookResponse(
            id=str(nb.get("id", "")),
            name=nb.get("name", ""),
            description=nb.get("description", ""),
            archived=nb.get("archived", False),
            is_public=nb.get("is_public", False),
            created=str(nb.get("created", "")),
            updated=str(nb.get("updated", "")),
            source_count=nb.get("source_count", 0),
            note_count=nb.get("note_count", 0),
        )
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error fetching notebook {notebook_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching notebook: {str(e)}"
        )


@router.put("/notebooks/{notebook_id}", response_model=NotebookResponse)
async def update_notebook(
    notebook_id: str,
    notebook_update: NotebookUpdate,
    current_user: User = Depends(get_current_user),
):
    """Update a notebook."""
    try:
        notebook = await _get_owned_notebook(notebook_id, current_user)

        # Update only provided fields
        if notebook_update.name is not None:
            notebook.name = notebook_update.name
        if notebook_update.description is not None:
            notebook.description = notebook_update.description
        if notebook_update.archived is not None:
            notebook.archived = notebook_update.archived
        if notebook_update.is_public is not None:
            notebook.is_public = notebook_update.is_public

        await notebook.save()

        # Query with counts after update
        query = """
            SELECT *,
            count(<-reference.in) as source_count,
            count(<-artifact.in) as note_count
            FROM $notebook_id
        """
        result = await repo_query(query, {"notebook_id": ensure_record_id(notebook_id)})

        if result:
            nb = result[0]
            return NotebookResponse(
                id=str(nb.get("id", "")),
                name=nb.get("name", ""),
                description=nb.get("description", ""),
                archived=nb.get("archived", False),
                is_public=nb.get("is_public", False),
                created=str(nb.get("created", "")),
                updated=str(nb.get("updated", "")),
                source_count=nb.get("source_count", 0),
                note_count=nb.get("note_count", 0),
            )

        # Fallback if query fails
        return NotebookResponse(
            id=notebook.id or "",
            name=notebook.name,
            description=notebook.description,
            archived=notebook.archived or False,
            is_public=notebook.is_public or False,
            created=str(notebook.created),
            updated=str(notebook.updated),
            source_count=0,
            note_count=0,
        )
    except HTTPException:
        raise
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Notebook not found")
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error updating notebook {notebook_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error updating notebook: {str(e)}"
        )


@router.post("/notebooks/{notebook_id}/sources/{source_id}")
async def add_source_to_notebook(
    notebook_id: str,
    source_id: str,
    current_user: User = Depends(get_current_user),
):
    """Add an existing source to a notebook (create the reference)."""
    try:
        # Verify the notebook and source exist (raises NotFoundError -> 404)
        await _get_owned_notebook(notebook_id, current_user)
        await Source.get(source_id)

        # Check if reference already exists (idempotency)
        existing_ref = await repo_query(
            "SELECT * FROM reference WHERE out = $source_id AND in = $notebook_id",
            {
                "notebook_id": ensure_record_id(notebook_id),
                "source_id": ensure_record_id(source_id),
            },
        )

        # If reference doesn't exist, create it
        if not existing_ref:
            await repo_query(
                "RELATE $source_id->reference->$notebook_id",
                {
                    "notebook_id": ensure_record_id(notebook_id),
                    "source_id": ensure_record_id(source_id),
                },
            )

        return {"message": "Source linked to notebook successfully"}
    except HTTPException:
        raise
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Notebook or source not found")
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(
            f"Error linking source {source_id} to notebook {notebook_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=500, detail=f"Error linking source to notebook: {str(e)}"
        )


@router.delete("/notebooks/{notebook_id}/sources/{source_id}")
async def remove_source_from_notebook(
    notebook_id: str,
    source_id: str,
    current_user: User = Depends(get_current_user),
):
    """Remove a source from a notebook (delete the reference)."""
    try:
        # Verify the notebook exists (raises NotFoundError -> 404)
        await _get_owned_notebook(notebook_id, current_user)

        # Delete the reference record linking source to notebook
        await repo_query(
            "DELETE FROM reference WHERE out = $notebook_id AND in = $source_id",
            {
                "notebook_id": ensure_record_id(notebook_id),
                "source_id": ensure_record_id(source_id),
            },
        )

        return {"message": "Source removed from notebook successfully"}
    except HTTPException:
        raise
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Notebook not found")
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(
            f"Error removing source {source_id} from notebook {notebook_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=500, detail=f"Error removing source from notebook: {str(e)}"
        )


@router.delete("/notebooks/{notebook_id}", response_model=NotebookDeleteResponse)
async def delete_notebook(
    notebook_id: str,
    delete_exclusive_sources: bool = Query(
        False,
        description="Whether to delete sources that belong only to this notebook",
    ),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a notebook with cascade deletion.

    Always deletes all notes associated with the notebook.
    If delete_exclusive_sources is True, also deletes sources that belong only
    to this notebook (not linked to any other notebooks).
    """
    try:
        notebook = await _get_owned_notebook(notebook_id, current_user)

        result = await notebook.delete(
            delete_exclusive_sources=delete_exclusive_sources
        )

        return NotebookDeleteResponse(
            message="Notebook deleted successfully",
            deleted_notes=result["deleted_notes"],
            deleted_sources=result["deleted_sources"],
            unlinked_sources=result["unlinked_sources"],
            deleted_chat_sessions=result["deleted_chat_sessions"],
        )
    except HTTPException:
        raise
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Notebook not found")
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error deleting notebook {notebook_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error deleting notebook: {str(e)}"
        )

@router.get(
    "/notebooks/{notebook_id}/share", response_model=List[NotebookShareResponse]
)
async def list_notebook_shares(
    notebook_id: str,
    current_user: User = Depends(get_current_user),
):
    """List the emails this notebook is shared with. Owner only."""
    try:
        await _get_owned_notebook(notebook_id, current_user)
        shares = await NotebookShare.list_for_notebook(notebook_id)
        return [
            NotebookShareResponse(email=share.email, created=str(share.created))
            for share in shares
        ]
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error listing shares for notebook {notebook_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error listing notebook shares: {str(e)}"
        )


@router.post("/notebooks/{notebook_id}/share", response_model=NotebookShareResponse)
async def share_notebook(
    notebook_id: str,
    share: NotebookShareCreate,
    current_user: User = Depends(get_current_user),
):
    """Share this notebook with another user's email. Owner only."""
    try:
        await _get_owned_notebook(notebook_id, current_user)
        record = NotebookShare(notebook_id=notebook_id, email=share.email)
        await record.save()
        return NotebookShareResponse(email=record.email, created=str(record.created))
    except HTTPException:
        raise
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error sharing notebook {notebook_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error sharing notebook: {str(e)}")


@router.delete("/notebooks/{notebook_id}/share/{email}")
async def unshare_notebook(
    notebook_id: str,
    email: str,
    current_user: User = Depends(get_current_user),
):
    """Remove an email from this notebook's share list. Owner only."""
    try:
        await _get_owned_notebook(notebook_id, current_user)
        await NotebookShare.remove(notebook_id, email)
        return {"message": "Removed"}
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error removing share from notebook {notebook_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error removing notebook share: {str(e)}"
        )


@router.get("/users/search", response_model=List[UserSearchResult])
async def search_users(
    q: str = Query("", description="Email prefix/substring to search for"),
    current_user: User = Depends(get_current_user),
):
    """
    Search among users already registered in this app (for the notebook
    sharing autocomplete). Does NOT touch the logged-in user's Google
    Contacts — only matches people who have already logged into this
    instance at least once.
    """
    try:
        query = (q or "").strip().lower()
        if len(query) < 2:
            return []
        rows = await repo_query(
            "SELECT name, email FROM app_user WHERE string::contains(string::lowercase(email), $q) LIMIT 10",
            {"q": query},
        )
        return [
            UserSearchResult(name=row.get("name", ""), email=row.get("email", ""))
            for row in rows
            if row.get("email")
        ]
    except Exception as e:
        logger.error(f"Error searching users: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error searching users: {str(e)}")