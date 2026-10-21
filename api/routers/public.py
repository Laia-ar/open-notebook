from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel

from api.models import NoteCreate, NoteUpdate, SourceResponse
from api.models import NoteResponse as ApiNoteResponse
from api.routers.notes import create_note as _create_note
from api.routers.notes import delete_note as _delete_note
from api.routers.notes import update_note as _update_note
from api.routers.sources import create_source as _create_source
from api.routers.sources import parse_source_form_data
from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.notebook import Notebook, Source
from open_notebook.exceptions import NotFoundError, OpenNotebookError

router = APIRouter()


class PublicNotebookResponse(BaseModel):
    id: str
    name: str
    description: str
    public_role: str = "viewer"


class PublicSourceResponse(BaseModel):
    id: str
    title: Optional[str] = None
    topics: Optional[List[str]] = None
    full_text: Optional[str] = None


class PublicNoteResponse(BaseModel):
    id: str
    title: Optional[str] = None
    content: Optional[str] = None


async def _get_public_notebook(notebook_id: str) -> Notebook:
    """
    Retrieves a notebook with NO login required, only if it is marked
    public. This is the "anyone with the link" door — read-only, and
    completely separate from the authenticated endpoints in notebooks.py.
    """
    try:
        notebook = await Notebook.get(notebook_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Notebook not found")

    if not notebook.is_public:
        raise HTTPException(status_code=404, detail="Notebook not found")

    return notebook


@router.get("/public/notebooks/{notebook_id}", response_model=PublicNotebookResponse)
async def get_public_notebook(notebook_id: str):
    """View a public notebook. No login required."""
    try:
        notebook = await _get_public_notebook(notebook_id)
        return PublicNotebookResponse(
            id=str(notebook.id),
            name=notebook.name,
            description=notebook.description or "",
            public_role=notebook.public_role,
        )
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error fetching public notebook {notebook_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching notebook")


@router.get(
    "/public/notebooks/{notebook_id}/sources", response_model=List[PublicSourceResponse]
)
async def get_public_notebook_sources(notebook_id: str):
    """List a public notebook's sources. No login required."""
    try:
        notebook = await _get_public_notebook(notebook_id)
        sources = await notebook.get_sources(include_full_text=True)
        return [
            PublicSourceResponse(
                id=str(s.id),
                title=s.title,
                topics=s.topics,
                full_text=s.full_text,
            )
            for s in sources
        ]
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error fetching public notebook sources {notebook_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching sources")


@router.get(
    "/public/notebooks/{notebook_id}/notes", response_model=List[PublicNoteResponse]
)
async def get_public_notebook_notes(notebook_id: str):
    """List a public notebook's notes. No login required."""
    try:
        notebook = await _get_public_notebook(notebook_id)
        notes = await notebook.get_notes(include_content=True)
        return [
            PublicNoteResponse(
                id=str(n.id),
                title=n.title,
                content=n.content,
            )
            for n in notes
        ]
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error fetching public notebook notes {notebook_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching notes")
    
async def _get_public_editable_notebook(notebook_id: str) -> Notebook:
    """
    Same as _get_public_notebook, but only lets through notebooks whose
    general access is set to "editor" — a public notebook left as "viewer"
    (the default) stays read-only here too.
    """
    notebook = await _get_public_notebook(notebook_id)
    if notebook.public_role != "editor":
        raise HTTPException(status_code=403, detail="This notebook is read-only")
    return notebook


@router.post("/public/notebooks/{notebook_id}/sources/{source_id}")
async def add_public_notebook_source(notebook_id: str, source_id: str):
    """
    Add an existing source to a public notebook. No login required — only
    works when the notebook's general access role is "editor".
    """
    try:
        await _get_public_editable_notebook(notebook_id)
        await Source.get(source_id)

        existing_ref = await repo_query(
            "SELECT * FROM reference WHERE out = $source_id AND in = $notebook_id",
            {
                "notebook_id": ensure_record_id(notebook_id),
                "source_id": ensure_record_id(source_id),
            },
        )
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
            f"Error linking source {source_id} to public notebook {notebook_id}: {str(e)}"
        )
        raise HTTPException(status_code=500, detail="Error linking source to notebook")


@router.delete("/public/notebooks/{notebook_id}/sources/{source_id}")
async def remove_public_notebook_source(notebook_id: str, source_id: str):
    """
    Remove a source from a public notebook. No login required — only works
    when the notebook's general access role is "editor".
    """
    try:
        await _get_public_editable_notebook(notebook_id)

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
            f"Error removing source {source_id} from public notebook {notebook_id}: {str(e)}"
        )
        raise HTTPException(status_code=500, detail="Error removing source from notebook")
    
async def _note_belongs_to_notebook(note_id: str, notebook_id: str) -> bool:
    rows = await repo_query(
        "SELECT * FROM artifact WHERE in = $note_id AND out = $notebook_id LIMIT 1",
        {
            "note_id": ensure_record_id(note_id),
            "notebook_id": ensure_record_id(notebook_id),
        },
    )
    return bool(rows)


@router.post("/public/notebooks/{public_notebook_id}/sources", response_model=SourceResponse)
async def create_public_notebook_source(
    public_notebook_id: str,
    form_data: tuple = Depends(parse_source_form_data),
):
    """
    Add a brand-new source (upload/link/text) to a public notebook. No
    login required — reuses the same validated logic as the authenticated
    endpoint in sources.py; only works when the notebook's general access
    role is "editor".
    """
    await _get_public_editable_notebook(public_notebook_id)
    source_data, _upload_file = form_data
    if not source_data.notebooks:
        source_data.notebooks = [public_notebook_id]
    return await _create_source(form_data)


@router.post("/public/notebooks/{notebook_id}/notes", response_model=ApiNoteResponse)
async def create_public_notebook_note(notebook_id: str, note_data: NoteCreate):
    """Create a note in a public notebook. No login required — editor role only."""
    try:
        await _get_public_editable_notebook(notebook_id)
        note_data.notebook_id = notebook_id
        return await _create_note(note_data)
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error creating public note for notebook {notebook_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error creating note")


@router.put("/public/notebooks/{notebook_id}/notes/{note_id}", response_model=ApiNoteResponse)
async def update_public_notebook_note(
    notebook_id: str, note_id: str, note_update: NoteUpdate
):
    """Edit a note in a public notebook. No login required — editor role only."""
    try:
        await _get_public_editable_notebook(notebook_id)
        if not await _note_belongs_to_notebook(note_id, notebook_id):
            raise HTTPException(status_code=404, detail="Note not found in this notebook")
        return await _update_note(note_id, note_update)
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error updating public note {note_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error updating note")


@router.delete("/public/notebooks/{notebook_id}/notes/{note_id}")
async def delete_public_notebook_note(notebook_id: str, note_id: str):
    """Delete a note from a public notebook. No login required — editor role only."""
    try:
        await _get_public_editable_notebook(notebook_id)
        if not await _note_belongs_to_notebook(note_id, notebook_id):
            raise HTTPException(status_code=404, detail="Note not found in this notebook")
        return await _delete_note(note_id)
    except HTTPException:
        raise
    except OpenNotebookError:
        raise
    except Exception as e:
        logger.error(f"Error deleting public note {note_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error deleting note")