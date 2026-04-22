"""Health and liveness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    """Return heartbeats for every known agent plus a top-level status."""
    try:
        hbs = await request.app.state.heartbeats.all()
    except Exception as err:  # noqa: BLE001
        return {"status": "degraded", "error": str(err), "agents": []}
    all_online = all(h.get("status") == "online" for h in hbs) if hbs else False
    return {
        "status": "ok" if all_online else "degraded",
        "agents": hbs,
    }


@router.get("/ready")
async def ready() -> dict[str, str]:
    """Kubernetes-style readiness check — lightweight."""
    return {"status": "ready"}
