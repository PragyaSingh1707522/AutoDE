from datetime import datetime, timedelta, timezone
import io

import jwt
from fastapi.testclient import TestClient

from backend.app.main import JWT_ALGORITHM, JWT_SECRET, SessionLocal
from backend.tests.conftest import bearer, register_user


def upload(client: TestClient, token: str, payload: bytes, filename: str = "records.csv"):
    return client.post("/api/sources", headers=bearer(token), files={"file": (filename, io.BytesIO(payload), "text/csv")})


def test_register_login_and_email_normalization(client: TestClient):
    created = register_user(client, " Owner@Example.Org ")
    assert created["user"]["email"] == "owner@example.org"
    assert created["role"] == "owner"
    response = client.post("/auth/login", json={"email": "OWNER@example.org", "password": "long-test-password-123"})
    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.json()["refresh_token"]
    assert response.cookies.get("autode_refresh")


def test_auth_me_and_spoofed_identity_headers_have_no_effect(client: TestClient):
    created = register_user(client, "a@example.org")
    token = created["access_token"]
    response = client.get("/auth/me", headers={**bearer(token), "X-Role": "viewer", "X-Organization-Id": "other-org"})
    assert response.status_code == 200
    assert response.json()["organization"]["id"] == created["organization"]["id"]
    assert response.json()["role"] == "owner"
    assert client.get("/api/sources", headers={"X-Role": "owner", "X-Organization-Id": created["organization"]["id"]}).status_code == 401


def test_refresh_rotation_reuse_and_logout_revocation(client: TestClient):
    created = register_user(client, "a@example.org")
    old_refresh = created["refresh_token"]
    rotated = client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert rotated.status_code == 200
    new_refresh = rotated.json()["refresh_token"]
    assert new_refresh != old_refresh
    assert client.post("/auth/refresh", json={"refresh_token": old_refresh}).status_code == 401
    assert client.post("/auth/logout", json={"refresh_token": new_refresh}).status_code == 200
    assert client.post("/auth/refresh", json={"refresh_token": new_refresh}).status_code == 401


def test_expired_and_tampered_access_tokens_are_rejected(client: TestClient):
    created = register_user(client, "a@example.org")
    claims = {"sub": created["user"]["id"], "organization_id": created["organization"]["id"], "role": "owner", "iat": datetime.now(timezone.utc) - timedelta(hours=1), "exp": datetime.now(timezone.utc) - timedelta(minutes=1), "jti": "expired", "type": "access"}
    expired = jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)
    assert client.get("/auth/me", headers=bearer(expired)).status_code == 401
    token = created["access_token"]
    tampered = token[:-2] + ("aa" if token[-2:] != "aa" else "bb")
    assert client.get("/auth/me", headers=bearer(tampered)).status_code == 401


def test_role_matrix_and_owner_approval_decisions(client: TestClient):
    owner = register_user(client, "owner@example.org")
    org_id = owner["organization"]["id"]
    analyst_response = client.post(f"/organizations/{org_id}/members", headers=bearer(owner["access_token"]), json={"email": "analyst@example.org", "role": "analyst", "password": "analyst-password-123"})
    viewer_response = client.post(f"/organizations/{org_id}/members", headers=bearer(owner["access_token"]), json={"email": "viewer@example.org", "role": "viewer", "password": "viewer-password-123"})
    assert analyst_response.status_code == viewer_response.status_code == 201
    analyst = client.post("/auth/login", json={"email": "analyst@example.org", "password": "analyst-password-123", "organization_id": org_id}).json()
    viewer = client.post("/auth/login", json={"email": "viewer@example.org", "password": "viewer-password-123", "organization_id": org_id}).json()
    assert client.post("/api/sources", headers={**bearer(viewer["access_token"]), "X-Role": "owner"}, files={"file": ("records.csv", b"name\nViewer\n", "text/csv")}).status_code == 403
    assert upload(client, analyst["access_token"], b"name\nOne\n").status_code == 201
    second = upload(client, analyst["access_token"], b"name,age\nOne,1\n")
    assert second.status_code == 201
    approval_id = second.json()["approval_id"]
    assert client.post(f"/api/approvals/{approval_id}", headers=bearer(analyst["access_token"]), json={"approved": True}).status_code == 403
    assert client.post(f"/api/approvals/{approval_id}", headers=bearer(owner["access_token"]), json={"approved": True}).json()["status"] == "approved"
    third = upload(client, analyst["access_token"], b"name,age\nOne,2\n")
    approval_id_2 = third.json()["approval_id"]
    assert client.post(f"/api/approvals/{approval_id_2}", headers=bearer(owner["access_token"]), json={"approved": False}).json()["status"] == "rejected"
    listed_statuses = {item["status"] for item in client.get("/api/approvals", headers=bearer(owner["access_token"])).json()}
    assert {"approved", "rejected"} <= listed_statuses


def test_cross_organization_source_profile_approval_and_audit_isolation(client: TestClient):
    org_a = register_user(client, "a@example.org")
    org_b = register_user(client, "b@example.org")
    upload(client, org_a["access_token"], b"name\nA\n", "a.csv")
    upload(client, org_b["access_token"], b"name\nB\n", "b.csv")
    changed = upload(client, org_b["access_token"], b"name,score\nB,2\n", "b.csv").json()
    a_headers = bearer(org_a["access_token"])
    sources = client.get("/api/sources", headers=a_headers).json()
    approvals = client.get("/api/approvals", headers=a_headers).json()
    audit = client.get("/api/audit", headers=a_headers).json()
    assert all(item["filename"] != "b.csv" for item in sources)
    assert all(item["id"] != changed["approval_id"] for item in approvals)
    assert client.post(f"/api/approvals/{changed['approval_id']}", headers=a_headers, json={"approved": True}).status_code == 404
    assert all(event["organization_id"] == org_a["organization"]["id"] for event in audit)
    assert client.get("/api/sources", headers={**a_headers, "X-Organization-Id": org_b["organization"]["id"]}).json() == sources


def test_login_errors_are_generic_and_rate_limited(client: TestClient):
    register_user(client, "known@example.org")
    missing = client.post("/auth/login", json={"email": "missing@example.org", "password": "wrong-password"})
    wrong = client.post("/auth/login", json={"email": "known@example.org", "password": "wrong-password"})
    assert missing.status_code == wrong.status_code == 401
    assert missing.json()["detail"] == wrong.json()["detail"]
    for _ in range(3):
        response = client.post("/auth/login", json={"email": "known@example.org", "password": "wrong-password"})
        assert response.status_code == 401
    limited = client.post("/auth/login", json={"email": "known@example.org", "password": "wrong-password"})
    assert limited.status_code == 429


def test_registration_is_rate_limited(client: TestClient):
    for index in range(5):
        response = client.post("/auth/register", json={"email": f"owner{index}@example.org", "password": "long-test-password-123", "organization_name": "Org"})
        assert response.status_code == 201
    limited = client.post("/auth/register", json={"email": "sixth@example.org", "password": "long-test-password-123", "organization_name": "Org"})
    assert limited.status_code == 429


def test_auth_audit_events_have_actor_org_ip_and_timestamp(client: TestClient):
    created = register_user(client, "owner@example.org")
    client.post("/auth/login", json={"email": "owner@example.org", "password": "long-test-password-123"})
    refreshed = client.post("/auth/refresh", json={"refresh_token": created["refresh_token"]}).json()
    client.post("/auth/logout", json={"refresh_token": refreshed["refresh_token"]})
    audit = client.get("/api/audit", headers=bearer(created["access_token"])).json()
    names = {event["event"] for event in audit}
    assert {"auth.register.success", "auth.login.success", "auth.refresh", "auth.logout"} <= names
    assert all(event["user_id"] == created["user"]["id"] and event["organization_id"] == created["organization"]["id"] and event["ip_address"] and event["created_at"] for event in audit)


def test_failed_login_is_audited_without_disclosing_account_existence(client: TestClient):
    created = register_user(client, "known@example.org")
    known = client.post("/auth/login", json={"email": "known@example.org", "password": "wrong-password"})
    missing = client.post("/auth/login", json={"email": "missing@example.org", "password": "wrong-password"})
    assert known.status_code == missing.status_code == 401
    assert known.json() == missing.json()
    audit = client.get("/api/audit", headers=bearer(created["access_token"])).json()
    failure = next(event for event in audit if event["event"] == "auth.login.failure")
    assert failure["user_id"] == created["user"]["id"]
    assert failure["organization_id"] == created["organization"]["id"]
    assert failure["ip_address"] and failure["created_at"]


def test_refresh_token_hash_is_stored_instead_of_plain_token(client: TestClient):
    created = register_user(client, "owner@example.org")
    with SessionLocal() as db:
        from backend.app.main import RefreshToken, hash_refresh
        stored = db.query(RefreshToken).one()
        assert stored.token_hash == hash_refresh(created["refresh_token"])
        assert stored.token_hash != created["refresh_token"]
