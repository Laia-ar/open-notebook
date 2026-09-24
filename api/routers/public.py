from typing import List, Optional

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

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