"""
Flashcard endpoints: the spaced-repetition review loop, plus authoring.

Separate from the challenge endpoints on purpose — see migration
032_flashcards_srs. Challenges are cohort-scheduled and graded; flashcards are
scheduled per learner by FSRS from their own 1-4 self-assessment.

Request/response models are declared here rather than in webapp/schemas.py to
keep this feature self-contained.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..dependencies import get_current_user
from handlers.translator import translate_text
from services import flashcard_service
from utils.logger import get_logger

router = APIRouter(prefix="/api/flashcards", tags=["flashcards"])
logger = get_logger(__name__)


# --- models ---------------------------------------------------------------


class ReferenceIn(BaseModel):
    # 'content' | 'segment' | 'highlight' | 'asset' | 'url'
    kind: str
    content_id: Optional[str] = None
    asset_id: Optional[str] = None
    segment_id: Optional[str] = None
    highlight_id: Optional[str] = None
    # {"page": 16, "rects": [...]} | {"start_ms": 92000} | {"url": "https://..."}
    locator: Dict[str, Any] = Field(default_factory=dict)
    label: Optional[str] = None


class NoteIn(BaseModel):
    # Must match the existing root exactly. A different spelling silently
    # creates a second root, which is how "Français" and "French" once became
    # two unrelated-looking decks.
    deck_path: str = "French::B1"
    note_type: str = "vocab"
    # {front, back, note_fa, example, source_page, tags}
    fields: Dict[str, Any]
    references: List[ReferenceIn] = Field(default_factory=list)


class NoteUpdateIn(BaseModel):
    fields: Dict[str, Any]
    note_type: Optional[str] = None
    deck_path: Optional[str] = None


class DeckUpdateIn(BaseModel):
    promise_id: Optional[str] = None


class ReviewIn(BaseModel):
    card_id: str
    rating: int = Field(ge=1, le=4, description="1=Again 2=Hard 3=Good 4=Easy")
    duration_ms: Optional[int] = Field(default=None, ge=0)


class WordLookupIn(BaseModel):
    word: str = Field(min_length=1, max_length=120)
    source_language: str = Field(default="fr", min_length=2, max_length=5)
    target_language: str = Field(default="fa", min_length=2, max_length=5)


_LOOKUP_LANGUAGES = {"en", "fr", "fa"}


# --- review loop ----------------------------------------------------------


@router.get("/queue")
async def get_queue(
    limit: int = 50,
    deck_id: Optional[str] = None,
    user_id: int = Depends(get_current_user),
):
    """Cards to review now: overdue first, then new material up to the daily cap."""
    return flashcard_service.get_queue(str(user_id), limit=limit, deck_id=deck_id)


@router.post("/review")
async def submit_review(
    payload: ReviewIn,
    user_id: int = Depends(get_current_user),
):
    result = flashcard_service.review_card(
        str(user_id),
        card_id=payload.card_id,
        rating=payload.rating,
        duration_ms=payload.duration_ms,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return result


@router.post("/lookup")
async def lookup_word(
    payload: WordLookupIn,
    user_id: int = Depends(get_current_user),
):
    """Translate one subtitle word for the in-player learning popover.

    The client debounces and caches requests, while the translator keeps a
    process cache. Authentication prevents the endpoint becoming an open
    translation proxy.
    """
    source = payload.source_language.strip().lower().split("-", 1)[0]
    target = payload.target_language.strip().lower().split("-", 1)[0]
    if source not in _LOOKUP_LANGUAGES or target not in _LOOKUP_LANGUAGES:
        raise HTTPException(status_code=422, detail="Unsupported language")

    word = " ".join(payload.word.strip().split())
    if not word:
        raise HTTPException(status_code=422, detail="word is required")

    translation = translate_text(word, target_lang=target, source_lang=source)
    return {
        "word": word,
        "translation": translation,
        "source_language": source,
        "target_language": target,
        "available": bool(translation and translation.strip() and translation != word),
    }


# --- authoring ------------------------------------------------------------


@router.get("/decks")
async def list_decks(user_id: int = Depends(get_current_user)):
    return flashcard_service.list_decks(str(user_id))


@router.get("/summary")
async def deck_summary(user_id: int = Depends(get_current_user)):
    """Top-level decks with due/new/total counts, for study entry points."""
    return flashcard_service.deck_summary(str(user_id))


@router.patch("/decks/{deck_id}")
async def update_deck(
    deck_id: str,
    payload: DeckUpdateIn,
    user_id: int = Depends(get_current_user),
):
    """Attach a deck to a promise so it appears under Play, or detach it.

    `promise_id: null` is a real instruction to detach, which is why the field
    is optional-with-sentinel rather than merged only when truthy.
    """
    ok = flashcard_service.set_deck_promise(
        str(user_id), deck_id, payload.promise_id
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Deck not found")
    return {"deck_id": deck_id, "promise_id": payload.promise_id}


@router.get("/notes")
async def list_notes(
    deck_id: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 500,
    user_id: int = Depends(get_current_user),
):
    """Notes with their references and read-only scheduling stats, for the editor."""
    return flashcard_service.list_notes(
        str(user_id), deck_id=deck_id, search=search, limit=limit
    )


@router.post("/notes")
async def create_note(payload: NoteIn, user_id: int = Depends(get_current_user)):
    if not payload.fields.get("front"):
        raise HTTPException(status_code=422, detail="fields.front is required")
    return flashcard_service.create_note(
        str(user_id),
        deck_path=payload.deck_path,
        fields=payload.fields,
        note_type=payload.note_type,
        references=[r.model_dump() for r in payload.references],
    )


@router.patch("/notes/{note_id}")
async def update_note(
    note_id: str,
    payload: NoteUpdateIn,
    user_id: int = Depends(get_current_user),
):
    """Edit content. Scheduling is deliberately untouched — fixing a typo must
    not reset how well the word is known."""
    updated = flashcard_service.update_note(
        str(user_id),
        note_id,
        fields=payload.fields,
        note_type=payload.note_type,
        deck_path=payload.deck_path,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return updated


@router.delete("/notes/{note_id}")
async def delete_note(note_id: str, user_id: int = Depends(get_current_user)):
    """Deletes the note, its cards and their review history."""
    if not flashcard_service.delete_note(str(user_id), note_id):
        raise HTTPException(status_code=404, detail="Note not found")
    return {"ok": True}


@router.post("/notes/{note_id}/references")
async def add_reference(
    note_id: str,
    payload: ReferenceIn,
    user_id: int = Depends(get_current_user),
):
    """Point a card at where it came from: a PDF highlight, a moment in a video
    or podcast (content_segment), or any URL."""
    try:
        reference = flashcard_service.add_reference(
            str(user_id), note_id, **payload.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if reference is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return reference


@router.delete("/notes/{note_id}/references/{reference_id}")
async def delete_reference(
    note_id: str,
    reference_id: str,
    user_id: int = Depends(get_current_user),
):
    if not flashcard_service.delete_reference(str(user_id), note_id, reference_id):
        raise HTTPException(status_code=404, detail="Note not found")
    return {"ok": True}
