"""Minimal FastAPI server exposing the router over HTTP."""

from __future__ import annotations

import argparse
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import uvicorn

from .router import InferenceRouter, RouteCriteria
from .providers import ProviderRegistry

app = FastAPI(title="OpenMoE Router", version="0.1.0")
router = InferenceRouter()


class ChatRequest(BaseModel):
    model: str = "openmoe/auto"
    messages: list[dict[str, Any]]
    criteria: dict[str, Any] = Field(default_factory=dict)


class RankRequest(BaseModel):
    model: str
    criteria: dict[str, Any] = Field(default_factory=dict)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "providers": [p.id for p in router.registry.list()]}


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    criteria = RouteCriteria(**req.criteria)
    try:
        response, receipt = await router.route(req.model, req.model_dump(exclude={"criteria"}), criteria)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        **response,
        "routing_receipt": receipt,
    }


@app.post("/v1/rank")
async def rank_providers(req: RankRequest):
    criteria = RouteCriteria(**req.criteria)
    try:
        ranked = router.rank(req.model, criteria)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "model": req.model,
        "criterion": criteria.optimize,
        "ranking": [
            {"provider": p.id, "model": p.default_model or p.models[0], "score": round(score, 4)}
            for p, score in ranked
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenMoE inference router server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8100)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
