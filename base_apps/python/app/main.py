from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("edge-api")

JAVA_API_BASE_URL = os.getenv("JAVA_API_BASE_URL", "http://localhost:8080")
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT_SECONDS", "10"))
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")
    if o.strip()
]

app = FastAPI(title="Edge API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    client = request.client.host if request.client else "-"
    logger.info(
        "%s %s -> %d (%.1fms) client=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
        client,
    )
    return response


class ItemIn(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None


class ItemOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    display_name: str

    @classmethod
    def from_upstream(cls, data: dict[str, Any]) -> "ItemOut":
        name = data.get("name") or ""
        return cls(
            id=data["id"],
            name=name,
            description=data.get("description"),
            # light-weight enrichment performed by this proxy layer
            display_name=name.strip().title(),
        )


async def _log_request(req: httpx.Request) -> None:
    logger.info("upstream -> %s %s", req.method, req.url)


async def _log_response(resp: httpx.Response) -> None:
    logger.info(
        "upstream <- %s %s %d",
        resp.request.method,
        resp.request.url,
        resp.status_code,
    )


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=JAVA_API_BASE_URL,
        timeout=HTTP_TIMEOUT,
        event_hooks={"request": [_log_request], "response": [_log_response]},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/hello")
async def hello() -> str:
    return "hello world"


@app.get("/items", response_model=list[ItemOut])
async def list_items() -> list[ItemOut]:
    async with _client() as client:
        resp = await client.get("/api/items")
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return [ItemOut.from_upstream(x) for x in resp.json()]


@app.get("/items/{item_id}", response_model=ItemOut)
async def get_item(item_id: int) -> ItemOut:
    async with _client() as client:
        resp = await client.get(f"/api/items/{item_id}")
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Item not found")
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return ItemOut.from_upstream(resp.json())


@app.post("/items", response_model=ItemOut, status_code=201)
async def create_item(item: ItemIn) -> ItemOut:
    async with _client() as client:
        resp = await client.post("/api/items", json=item.model_dump())
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return ItemOut.from_upstream(resp.json())


@app.put("/items/{item_id}", response_model=ItemOut)
async def update_item(item_id: int, item: ItemIn) -> ItemOut:
    async with _client() as client:
        resp = await client.put(f"/api/items/{item_id}", json=item.model_dump())
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Item not found")
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return ItemOut.from_upstream(resp.json())


@app.delete("/items/{item_id}", status_code=204)
async def delete_item(item_id: int) -> None:
    async with _client() as client:
        resp = await client.delete(f"/api/items/{item_id}")
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Item not found")
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return None
