"""Public brief endpoints.

* ``GET /briefs`` — newest-first list.
* ``GET /briefs/{id}`` — full brief with lineage ids.
* ``GET /briefs/{id}/verify`` — live re-hash + on-chain lookup.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from agents.common.hasher import hash_payload

router = APIRouter(prefix="/briefs", tags=["briefs"])


@router.get("", response_model=None)
async def list_briefs(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Return the newest-first list of AlphaBriefs."""
    rows = await request.app.state.findings.list_briefs(limit=limit, offset=offset)
    return {
        "items": [
            {
                "msg_id": r.msg_id,
                "payload": r.payload,
                "payload_hash": r.payload_hash,
                "upstream_ids": r.upstream_ids,
                "model_used": r.model_used,
                "created_at": r.created_at,
                "on_chain_tx": r.on_chain_tx,
                "on_chain_block": r.on_chain_block,
            }
            for r in rows
        ],
        "limit": limit,
        "offset": offset,
    }


@router.get("/{msg_id}", response_model=None)
async def get_brief(request: Request, msg_id: str) -> dict[str, Any]:
    """Return a single brief by ``msg_id`` (404 if unknown)."""
    row = await request.app.state.findings.get(msg_id)
    if row is None:
        raise HTTPException(status_code=404, detail="brief not found")
    return {
        "msg_id": row.msg_id,
        "agent": row.agent,
        "payload": row.payload,
        "payload_hash": row.payload_hash,
        "upstream_ids": row.upstream_ids,
        "model_used": row.model_used,
        "created_at": row.created_at,
        "on_chain_tx": row.on_chain_tx,
        "on_chain_block": row.on_chain_block,
    }


@router.get("/{msg_id}/verify", response_model=None)
async def verify_brief(request: Request, msg_id: str) -> dict[str, Any]:
    """Compare the stored payload's hash against the on-chain record."""
    row = await request.app.state.findings.get(msg_id)
    if row is None:
        raise HTTPException(status_code=404, detail="brief not found")
    local_hash = hash_payload(row.payload)
    hash_match = local_hash == row.payload_hash
    on_chain = await request.app.state.anchor.verify(msg_id)
    on_chain_match = bool(on_chain) and on_chain.payload_hash_hex == row.payload_hash
    return {
        "msg_id": row.msg_id,
        "local_hash": local_hash,
        "stored_hash": row.payload_hash,
        "hash_match": hash_match,
        "on_chain_present": on_chain is not None,
        "on_chain_match": on_chain_match,
        "on_chain_tx": row.on_chain_tx,
        "on_chain_block": row.on_chain_block,
    }
