"""FastAPI router exposing transparency and evidence audit endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .transparency_repository import default_repository

repository = default_repository()
router = APIRouter(prefix="/transparency", tags=["transparency"])


@router.get("/status")
def transparency_status() -> dict:
    """Return repository health, counts, and integrity summary."""
    return repository.get_status()


@router.get("/facts")
def list_facts(limit: int = Query(20, ge=1, le=200)) -> dict:
    """List recent fact summaries sorted by most recent update."""
    facts = repository.list_facts(limit=limit)
    return {"facts": facts}


@router.get("/facts/{fact_id}")
def get_fact(fact_id: str) -> dict:
    """Return a single fact with joined article, cluster, and evidence metadata."""
    try:
        payload = repository.get_fact(fact_id)
        if payload["missing_assets"]:
            payload["integrity"] = {
                "status": "degraded",
                "missing_assets": payload["missing_assets"],
            }
        else:
            payload["integrity"] = {"status": "ok"}
        return payload
    except FileNotFoundError as exc:  # pragma: no cover - exercised in API tests
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/clusters/{cluster_id}")
def get_cluster(cluster_id: str) -> dict:
    """Return cluster details and linked facts."""
    try:
        payload = repository.get_cluster(cluster_id)
        if payload["missing_facts"]:
            payload["integrity"] = {
                "status": "degraded",
                "missing_facts": payload["missing_facts"],
            }
        else:
            payload["integrity"] = {"status": "ok"}
        return payload
    except FileNotFoundError as exc:  # pragma: no cover - exercised in API tests
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/articles/{article_id}")
def get_article(article_id: str) -> dict:
    """Return article metadata with related fact and cluster summaries."""
    try:
        return repository.get_article(article_id)
    except FileNotFoundError as exc:  # pragma: no cover - exercised in API tests
        raise HTTPException(status_code=404, detail=str(exc)) from exc


__all__ = ["router", "repository"]
