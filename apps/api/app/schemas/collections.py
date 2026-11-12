from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["student", "admin"]


def _default_roles() -> list[Role]:
    return ["student", "admin"]


class SearchProfile(BaseModel):
    mode: Literal["keyword", "vector", "hybrid"] = "hybrid"
    candidate_k: int = Field(20, ge=1, le=100)
    context_k: int = Field(5, ge=1, le=20)
    rrf_rank_constant: int = Field(60, ge=1, le=1000)
    max_chunks_per_page: int = Field(2, ge=1, le=10)


class CollectionCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9_]{2,40}$")
    name: str = Field(min_length=1, max_length=100)
    allowed_roles: list[Role] = Field(default_factory=_default_roles, min_length=1)
    search_profile: SearchProfile | None = None


class CollectionCreated(BaseModel):
    id: str
    slug: str
    name: str
    version: int


class CollectionItem(BaseModel):
    id: str
    slug: str
    name: str
    document_count: int
    ready_count: int
    version: int
    search_profile: SearchProfile


class CollectionList(BaseModel):
    items: list[CollectionItem]
