from typing import List, Optional

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel

from open_notebook.domain.notebook import Notebook
from open_notebook.exceptions import NotFoundError, OpenNotebookError

router = APIRouter()


class PublicNotebookResponse(BaseModel):
    id: str
    name: str
    description: str


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