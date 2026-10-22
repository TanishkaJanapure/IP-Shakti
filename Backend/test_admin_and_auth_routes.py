"""
Tests for /admin/corpus and auth endpoints:
- Registration, Login, Current User, Logout
- History persistence and retrieval
- Admin corpus statistics and document list
"""
import pytest
from fastapi.testclient import TestClient
from main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_admin_corpus_overview(client):
    res = client.get("/admin/corpus")
    assert res.status_code == 200
    data = res.json()
    assert "total_documents" in data
    assert "total_chunks" in data
    assert "total_pages" in data
    assert "total_characters" in data
    assert "index_built" in data
    assert "documents" in data
    assert isinstance(data["documents"], list)
    assert data["total_documents"] >= 90
    assert data["total_chunks"] > 0

    first_doc = data["documents"][0]
    assert "filename" in first_doc
    assert "document_id" in first_doc
    assert "pages" in first_doc
    assert "character_count" in first_doc
    assert "pdf_available" in first_doc

def test_auth_registration_login_lifecycle(client):
    import secrets
    uniq = secrets.token_hex(4)
    email = f"user_{uniq}@ayurveda.org"
    password = "securePassword123"

    # Register
    reg_res = client.post("/auth/register", json={
        "name": f"Researcher {uniq}",
        "email": email,
        "password": password
    })
    assert reg_res.status_code == 200
    reg_data = reg_res.json()
    assert "token" in reg_data
    token = reg_data["token"]
    assert reg_data["user"]["email"] == email

    # /auth/me with bearer token
    me_res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.json()["user"]["email"] == email

    # Post history entry
    hist_post = client.post("/auth/history", headers={"Authorization": f"Bearer {token}"}, json={
        "question": "Can I patent an Ayurvedic herbal extract?",
        "answer": "Section 3(p) of the Patents Act, 1970 excludes traditional knowledge.",
        "language": "English"
    })
    assert hist_post.status_code == 200

    # Retrieve history
    hist_get = client.get("/auth/history", headers={"Authorization": f"Bearer {token}"})
    assert hist_get.status_code == 200
    items = hist_get.json().get("items", [])
    assert len(items) >= 1
    assert items[0]["question"] == "Can I patent an Ayurvedic herbal extract?"

    # Login with same credentials
    login_res = client.post("/auth/login", json={
        "email": email,
        "password": password
    })
    assert login_res.status_code == 200
    assert "token" in login_res.json()

    # Logout
    logout_res = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_res.status_code == 200

    # After logout, old token is unauthorized
    unauth_me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert unauth_me.status_code == 401
