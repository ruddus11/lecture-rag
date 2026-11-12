from __future__ import annotations

import pytest

from tests.conftest import DEMO_PASSWORDS


@pytest.mark.parametrize("username", ["a_admin", "a_student", "b_student"])
async def test_login_and_me(api, username):
    r = await api.c.post(
        "/api/v1/auth/login", json={"username": username, "password": DEMO_PASSWORDS[username]}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 28800
    me = await api.c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["username"] == username
    assert me.json()["institution_name"].startswith("캠퍼스")


async def test_login_wrong_password_401(api):
    r = await api.c.post("/api/v1/auth/login", json={"username": "a_admin", "password": "wrong-password"})
    assert r.status_code == 401
    err = r.json()["error"]
    assert err["code"] == "unauthorized" and err["request_id"] and err["retryable"] is False


async def test_login_unknown_user_401(api):
    r = await api.c.post("/api/v1/auth/login", json={"username": "nobody", "password": "whatever-123"})
    assert r.status_code == 401


async def test_no_token_401_and_bad_token_401(api):
    assert (await api.c.get("/api/v1/auth/me")).json()["error"]["code"] == "unauthorized"
    r = await api.c.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


async def test_expired_token_401_token_expired(api):
    from app.core.auth import issue_token

    s = api.services.settings
    tok = issue_token(s.auth_secret.get_secret_value(), "x", "campus_a", "admin", ttl_seconds=-10)
    r = await api.c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "token_expired"


async def test_validation_422(api):
    r = await api.c.post("/api/v1/auth/login", json={"username": "ab", "password": "short"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error" and isinstance(err["details"], list)


async def test_invalid_json_400(api):
    r = await api.c.post(
        "/api/v1/auth/login", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_request"


async def test_collection_visibility_three_accounts(api):
    a_admin = await api.collections("a_admin")
    a_student = await api.collections("a_student")
    b_student = await api.collections("b_student")
    assert set(a_admin) == {"ai_basics", "operating_systems", "ta_only"}
    assert set(a_student) == {"ai_basics", "operating_systems"}
    assert set(b_student) == {"networks"}
    r = await api.c.get("/api/v1/collections", headers=await api.h("a_admin"))
    item = r.json()["items"][0]
    assert item["document_count"] == 0 and item["version"] == 1
    assert item["search_profile"]["mode"] == "hybrid"


async def test_create_collection_student_403(api):
    r = await api.c.post(
        "/api/v1/collections", json={"slug": "new_one", "name": "새 컬렉션"}, headers=await api.h("a_student")
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden_role"


async def test_create_collection_admin_and_duplicate_409(api):
    h = await api.h("a_admin")
    r = await api.c.post("/api/v1/collections", json={"slug": "algorithms", "name": "알고리즘"}, headers=h)
    assert r.status_code == 201 and r.json()["version"] == 1
    r = await api.c.post("/api/v1/collections", json={"slug": "algorithms", "name": "중복"}, headers=h)
    assert r.status_code == 409
    # 다른 기관은 같은 slug 를 쓸 수 있고, 새 컬렉션이 보이지 않는다
    assert "algorithms" not in await api.collections("b_student")


async def test_create_collection_validation_422(api):
    r = await api.c.post(
        "/api/v1/collections", json={"slug": "Bad Slug!", "name": "x"}, headers=await api.h("a_admin")
    )
    assert r.status_code == 422


async def test_unknown_route_404_standard_format(api):
    r = await api.c.get("/api/v1/does-not-exist")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize(
    "settings_overrides", [{"rate_limit_enabled": True, "rate_limit_upload_per_hour": 2}]
)
async def test_rate_limiter_429(api):
    from app.core.errors import AppError

    rl = api.services.ratelimiter
    rl.check("u1", "upload")
    rl.check("u1", "upload")
    with pytest.raises(AppError) as e:
        rl.check("u1", "upload")
    assert e.value.status == 429 and int(e.value.headers["Retry-After"]) >= 1
    rl.check("u2", "upload")  # 사용자별 분리
