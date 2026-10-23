"""LLM status and toggle (BUILD §5.3)."""

from fastapi import APIRouter
from pydantic import BaseModel

from rakt import llm

router = APIRouter()


class ToggleBody(BaseModel):
    enabled: bool


@router.get("/llm")
def status() -> dict:
    return llm.status()


@router.post("/llm")
def toggle(body: ToggleBody) -> dict:
    llm.set_enabled(body.enabled)
    return llm.status()
