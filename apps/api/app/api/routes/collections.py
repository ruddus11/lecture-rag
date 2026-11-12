from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db, require_admin
from app.core.errors import AppError
from app.core.scope import permitted_collections
from app.schemas.collections import (
    CollectionCreate,
    CollectionCreated,
    CollectionItem,
    CollectionList,
    SearchProfile,
)
from app.storage.models import Collection, Document, User
from app.storage.seed import DEFAULT_SEARCH_PROFILE

router = APIRouter(prefix="/collections", tags=["collections"])

_LIVE = ("queued", "processing", "ready", "failed")


@router.get("", response_model=CollectionList)
async def list_collections(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> CollectionList:
    cols = permitted_collections(db, user)
    counts: dict[tuple[str, str], int] = {}
    if cols:
        rows = db.execute(
            select(Document.collection_id, Document.status, func.count())
            .where(Document.collection_id.in_([c.id for c in cols]), Document.status.in_(_LIVE))
            .group_by(Document.collection_id, Document.status)
        ).all()
        counts = {(cid, st): n for cid, st, n in rows}
    items = [
        CollectionItem(
            id=c.id,
            slug=c.slug,
            name=c.name,
            document_count=sum(counts.get((c.id, st), 0) for st in _LIVE),
            ready_count=counts.get((c.id, "ready"), 0),
            version=c.version,
            search_profile=SearchProfile(**{**DEFAULT_SEARCH_PROFILE, **(c.search_profile or {})}),
        )
        for c in cols
    ]
    return CollectionList(items=items)


@router.post("", response_model=CollectionCreated, status_code=201)
async def create_collection(
    body: CollectionCreate, user: User = Depends(require_admin), db: Session = Depends(get_db)
) -> CollectionCreated:
    exists = db.scalar(
        select(Collection.id).where(
            Collection.institution_id == user.institution_id, Collection.slug == body.slug
        )
    )
    if exists:
        raise AppError(409, "duplicate_collection", "같은 slug 의 컬렉션이 이미 있습니다.")
    profile = (body.search_profile or SearchProfile(**DEFAULT_SEARCH_PROFILE)).model_dump()
    col = Collection(
        id=str(uuid.uuid4()),
        institution_id=user.institution_id,
        slug=body.slug,
        name=body.name,
        allowed_roles=list(dict.fromkeys(body.allowed_roles)),
        search_profile=profile,
        version=1,
    )
    db.add(col)
    db.commit()
    return CollectionCreated(id=col.id, slug=col.slug, name=col.name, version=col.version)
