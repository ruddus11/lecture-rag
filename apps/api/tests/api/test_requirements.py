"""고객 요구: 원장 설정 변경은 재로그인 없이 다음 요청부터 반영한다."""

from app.storage.models import Collection

Q = "교착 상태의 네 가지 필요 조건은?"


async def test_allowed_roles_change_immediately_revokes_access(api, pdfs):
    uploaded = await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    cid = (await api.collections("a_admin"))["operating_systems"]
    did = uploaded["document_id"]
    assert (await api.answer("a_student", Q, collection_ids=[cid])).json()["hits"]
    assert (
        await api.c.get(f"/api/v1/documents/{did}/file", headers=await api.h("a_student"))
    ).status_code == 200
    with api.services.db.session() as db:
        col = db.get(Collection, cid)
        col.allowed_roles = ["admin"]
        db.commit()
    assert "operating_systems" not in await api.collections("a_student")
    assert (await api.search("a_student", Q, collection_ids=[cid])).status_code == 404
    assert (await api.answer("a_student", Q, collection_ids=[cid])).status_code == 404
    for suffix in ("", "/file"):
        assert (
            await api.c.get(f"/api/v1/documents/{did}{suffix}", headers=await api.h("a_student"))
        ).status_code == 404
    assert (await api.search("a_admin", Q, collection_ids=[cid])).status_code == 200


async def test_search_profile_mode_change_applies_next_request(api, pdfs):
    await api.ingest("a_admin", "operating_systems", pdfs["korean_text.pdf"])
    cid = (await api.collections("a_admin"))["operating_systems"]
    for mode in ("keyword", "vector", "hybrid"):
        with api.services.db.session() as db:
            col = db.get(Collection, cid)
            col.search_profile = {**col.search_profile, "mode": mode}
            db.commit()
        for request in (api.search, api.answer):
            r = await request("a_student", Q, collection_ids=[cid])
            assert r.status_code == 200
            assert r.json()["mode"] == mode
            assert r.json()["hits"]
    assert (await api.search("a_student", Q, collection_ids=[cid], mode="keyword")).json()[
        "mode"
    ] == "keyword"


async def test_new_collection_keeps_institution_and_role_isolation(api, pdfs):
    r = await api.c.post(
        "/api/v1/collections",
        headers=await api.h("a_admin"),
        json={
            "slug": "customer_private",
            "name": "추가 과목",
            "allowed_roles": ["admin"],
        },
    )
    assert r.status_code == 201
    cid = r.json()["id"]
    uploaded = await api.upload("a_admin", cid, pdfs["korean_text.pdf"])
    assert uploaded.status_code == 202
    await api.drain()
    did = uploaded.json()["document_id"]
    assert (await api.search("a_admin", Q, collection_ids=[cid])).json()["hits"]
    for user in ("a_student", "b_admin", "b_student"):
        assert "customer_private" not in await api.collections(user)
        assert (await api.search(user, Q, collection_ids=[cid])).status_code == 404
        assert (await api.answer(user, Q, collection_ids=[cid])).status_code == 404
        assert (
            await api.c.get(f"/api/v1/documents/{did}/file", headers=await api.h(user))
        ).status_code == 404
