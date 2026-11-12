"""scope 교집합·404 규칙 (설계서 6.1, 9.2)."""

from __future__ import annotations

import uuid

import pytest

from app.core.errors import AppError
from app.core.scope import resolve_scope
from app.storage.db import Database
from app.storage.models import Collection, Institution, User


@pytest.fixture
def db(tmp_path):
    d = Database(f"sqlite:///{tmp_path / 't.db'}")
    d.create_all()
    with d.session() as s:
        s.add_all([Institution(id="A", name="A"), Institution(id="B", name="B")])
        s.flush()
        for cid, inst, slug, roles in [
            ("a1", "A", "ai", ["student", "admin"]),
            ("a2", "A", "os", ["student", "admin"]),
            ("a3", "A", "ta", ["admin"]),
            ("b1", "B", "net", ["student", "admin"]),
        ]:
            s.add(
                Collection(
                    id=cid,
                    institution_id=inst,
                    slug=slug,
                    name=slug,
                    allowed_roles=roles,
                    search_profile={},
                    version=1,
                )
            )
        for uid, inst, role in [("sa", "A", "student"), ("aa", "A", "admin"), ("sb", "B", "student")]:
            s.add(
                User(
                    id=uid,
                    username=uid + str(uuid.uuid4())[:4],
                    password_hash="x",
                    institution_id=inst,
                    role=role,
                )
            )
        s.commit()
    return d


def _user(db, uid):
    with db.session() as s:
        return s.get(User, uid)


def test_empty_request_returns_all_permitted(db):
    with db.session() as s:
        assert resolve_scope(s, _user(db, "sa"), []).collection_ids == ("a1", "a2")
        assert resolve_scope(s, _user(db, "aa"), None).collection_ids == ("a1", "a2", "a3")
        assert resolve_scope(s, _user(db, "sb"), []).collection_ids == ("b1",)


def test_subset_request(db):
    with db.session() as s:
        assert resolve_scope(s, _user(db, "sa"), ["a2"]).collection_ids == ("a2",)


def test_partially_disallowed_request_is_404(db):
    with db.session() as s, pytest.raises(AppError) as e:
        resolve_scope(s, _user(db, "sa"), ["a1", "zzz"])
    assert e.value.status == 404 and e.value.code == "collection_not_found"


def test_other_institution_is_404(db):
    with db.session() as s, pytest.raises(AppError) as e:
        resolve_scope(s, _user(db, "sb"), ["a1"])
    assert e.value.status == 404


def test_role_not_allowed_is_404(db):
    with db.session() as s, pytest.raises(AppError) as e:
        resolve_scope(s, _user(db, "sa"), ["a3"])
    assert e.value.code == "collection_not_found"


def test_admin_only_collection_visible_to_admin(db):
    with db.session() as s:
        assert resolve_scope(s, _user(db, "aa"), ["a3"]).collection_ids == ("a3",)


def test_fingerprint_changes_with_version_and_set(db):
    with db.session() as s:
        u = _user(db, "sa")
        f1 = resolve_scope(s, u, []).fingerprint
        assert resolve_scope(s, u, ["a2", "a1"]).fingerprint == f1  # 순서 무관
        assert resolve_scope(s, u, ["a1"]).fingerprint != f1
        s.get(Collection, "a1").version += 1
        s.commit()
        assert resolve_scope(s, u, []).fingerprint != f1
