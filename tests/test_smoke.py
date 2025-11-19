"""Smoke tests using FastAPI TestClient with mocked Astra DB calls."""
import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Set minimal env vars for tests before importing app
os.environ.setdefault("ASTRA_DB_ID", "test-db-id")
os.environ.setdefault("ASTRA_REGION", "us-east1")
os.environ.setdefault("TOKENS_JSON", '{"acme":{"reader":"test","writer":"test"}}')
os.environ.setdefault("OIDC_ISSUER", "http://localhost:9000/")
os.environ.setdefault("OIDC_AUDIENCE", "test-audience")

from app.main import app
from app.security import User


@pytest.fixture
def client(mock_user):
    """Create test client with overridden dependencies."""
    from app.security import get_current_user
    
    def override_get_current_user():
        return mock_user
    
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def mock_user():
    """Create mock user."""
    return User(sub="alice@acme.com", tenant="acme", teams=["finance"])


@pytest.fixture
def mock_jwt_token():
    """Create mock JWT token."""
    return "mock.jwt.token"


@pytest.fixture(autouse=True)
def mock_jwks():
    """Mock JWKS fetching for all tests."""
    with patch('app.security.get_jwks') as mock:
        mock.return_value = {
            "keys": [{
                "kty": "RSA",
                "kid": "test-key",
                "use": "sig",
                "n": "test",
                "e": "AQAB"
            }]
        }
        yield mock


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@patch("app.main.astra_insert")
def test_ingest_success(mock_astra_insert, client, mock_user):
    """Test successful document ingestion."""
    mock_astra_insert.return_value = {"status": "inserted", "documentId": "test-123"}
    
    payload = {
        "tenant_id": "acme",
        "doc_id": "test-doc-1",
        "text": "Test document content",
        "visibility": "public"
    }
    
    response = client.post(
        "/ingest",
        json=payload,
        headers={"Authorization": "Bearer mock.jwt.token"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["doc_id"] == "test-doc-1"
    mock_astra_insert.assert_called_once()


def test_ingest_tenant_mismatch(client, mock_user):
    """Test that ingestion fails when user tenant doesn't match request."""
    
    payload = {
        "tenant_id": "zen",  # Different tenant
        "doc_id": "test-doc-1",
        "text": "Test document content",
        "visibility": "public"
    }
    
    response = client.post(
        "/ingest",
        json=payload,
        headers={"Authorization": "Bearer mock.jwt.token"}
    )
    
    assert response.status_code == 403
    assert "does not match" in response.json()["detail"]


@patch("app.main.astra_find")
def test_query_success(mock_astra_find, client, mock_user):
    """Test successful query with security trimming."""
    
    # Mock Astra DB response
    mock_astra_find.return_value = {
        "data": {
            "documents": [
                {
                    "doc_id": "doc-1",
                    "text": "Document 1 content",
                    "visibility": "public"
                },
                {
                    "doc_id": "doc-2",
                    "text": "Document 2 content",
                    "visibility": "internal"
                }
            ]
        }
    }
    
    payload = {
        "question": "What is the product?"
    }
    
    response = client.post(
        "/query",
        json=payload,
        headers={"Authorization": "Bearer mock.jwt.token"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "matches" in data
    assert "prompt_context" in data
    assert len(data["matches"]) == 2
    assert len(data["prompt_context"]) == 2
    assert data["matches"][0]["doc_id"] == "doc-1"
    assert data["prompt_context"][0]["doc_id"] == "doc-1"
    assert data["prompt_context"][0]["text"] == "Document 1 content"
    
    # Verify astra_find was called with ACL filter
    mock_astra_find.assert_called_once()
    call_args = mock_astra_find.call_args
    filter_dict = call_args.kwargs["filter_dict"]
    assert "$and" in filter_dict


@patch("app.main.astra_find")
def test_query_empty_results(mock_astra_find, client, mock_user):
    """Test query with no matching results."""
    mock_astra_find.return_value = {
        "data": {
            "documents": []
        }
    }
    
    payload = {
        "question": "What is the product?"
    }
    
    response = client.post(
        "/query",
        json=payload,
        headers={"Authorization": "Bearer mock.jwt.token"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data["matches"]) == 0
    assert len(data["prompt_context"]) == 0


def test_ingest_requires_auth():
    """Test that /ingest requires authentication."""
    # Create a client without dependency override
    test_client = TestClient(app)
    payload = {
        "tenant_id": "acme",
        "doc_id": "test-doc-1",
        "text": "Test document content",
        "visibility": "public"
    }
    
    response = test_client.post("/ingest", json=payload)
    assert response.status_code == 403  # FastAPI returns 403 for missing auth


def test_query_requires_auth():
    """Test that /query requires authentication."""
    # Create a client without dependency override
    test_client = TestClient(app)
    payload = {
        "question": "What is the product?"
    }
    
    response = test_client.post("/query", json=payload)
    assert response.status_code == 403  # FastAPI returns 403 for missing auth

