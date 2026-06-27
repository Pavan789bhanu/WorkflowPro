"""Integration tests for UI Capture System.

Tests critical security, authentication, and API functionality.
Run with: pytest tests/test_integration.py -v
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.core.database import Base, get_db
from app.models.models import User as UserModel
from app.core.config import settings
from app.core.security import get_password_hash

# Test database setup
import os
import tempfile

# Keep the test DB in a temp dir — avoids littering the repo and works on
# network-mounted filesystems where SQLite locking can fail.
_TEST_DB = os.path.join(tempfile.mkdtemp(prefix='workflowpro_test_'), 'test.db')
SQLALCHEMY_DATABASE_URL = f"sqlite:///{_TEST_DB}"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    """Create test database."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db):
    """Create test client with test database."""
    def override_get_db():
        try:
            yield db
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db):
    """Create test user."""
    user = UserModel(
        email="test@example.com",
        username="testuser",
        hashed_password=get_password_hash("testpassword123"),
        is_active=True,
        is_superuser=False
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def auth_headers(client, test_user):
    """Get authentication headers."""
    response = client.post(
        "/api/auth/login",
        data={"username": test_user.username, "password": "testpassword123"}
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestSecurity:
    """Test security features from Phase 1."""
    
    def test_secret_key_required(self):
        """Test that SECRET_KEY is required (Phase 1 Fix 1)."""
        assert settings.SECRET_KEY, "SECRET_KEY must be set in environment"
        assert len(settings.SECRET_KEY) >= 32, "SECRET_KEY must be at least 32 characters"
    
    def test_authentication_required(self, client):
        """Test that endpoints require authentication (Phase 1 Fix 2)."""
        # Test workflows endpoint
        response = client.get("/api/workflows")
        assert response.status_code == 401, "Workflows endpoint should require auth"
        
        # Test executions endpoint
        response = client.get("/api/executions")
        assert response.status_code == 401, "Executions endpoint should require auth"
        
        # Test analytics endpoint
        response = client.get("/api/analytics/overview")
        assert response.status_code == 401, "Analytics endpoint should require auth"
    
    def test_password_encryption(self):
        """Test password encryption utilities (Phase 1 Fix 3)."""
        from app.core.encryption import encrypt_password, decrypt_password
        
        test_password = "test_password_123"
        encrypted = encrypt_password(test_password)
        
        assert encrypted != test_password, "Password should be encrypted"
        assert len(encrypted) > 0, "Encrypted password should not be empty"
        
        decrypted = decrypt_password(encrypted)
        assert decrypted == test_password, "Decrypted password should match original"
    
    def test_rate_limiting_configured(self):
        """Test rate limiting is configured (Phase 1 Fix 5)."""
        assert hasattr(settings, 'RATE_LIMIT_PER_MINUTE'), "Rate limit config should exist"
        assert settings.RATE_LIMIT_PER_MINUTE > 0, "Rate limit should be positive"
    
    def test_cors_configuration(self):
        """Test CORS is environment-aware (Phase 1 Fix 4)."""
        # In development, CORS should allow all origins
        # In production, CORS should be restricted
        assert hasattr(settings, 'ENVIRONMENT'), "Environment setting should exist"
        assert hasattr(settings, 'ALLOWED_ORIGINS'), "CORS origins should be configured"


class TestAuthentication:
    """Test authentication flow."""
    
    def test_login_success(self, client, test_user):
        """Test successful login."""
        response = client.post(
            "/api/auth/login",
            data={"username": test_user.username, "password": "testpassword123"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
    
    def test_login_with_email_address(self, client, test_user):
        """Login should accept email as well as username."""
        response = client.post(
            "/api/auth/login",
            data={"username": test_user.email, "password": "testpassword123"},
        )
        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_login_invalid_credentials(self, client, test_user):
        """Test login with invalid credentials."""
        response = client.post(
            "/api/auth/login",
            data={"username": test_user.username, "password": "wrongpassword"}
        )
        assert response.status_code == 401
    
    def test_protected_endpoint_with_token(self, client, auth_headers):
        """Test accessing protected endpoint with valid token."""
        response = client.get("/api/workflows", headers=auth_headers)
        assert response.status_code == 200


class TestSSRFProtection:
    """Test SSRF protection from Phase 2."""
    
    def test_ssrf_protector_blocks_localhost(self):
        """Test that SSRFProtector blocks localhost."""
        from app.utils.ssrf_protector import SSRFProtector
        
        protector = SSRFProtector()
        
        # Test localhost variations
        is_valid, error = protector.validate_url("http://localhost:8000")
        assert not is_valid, "Should block localhost"
        assert "localhost" in error.lower()
        
        is_valid, error = protector.validate_url("http://127.0.0.1:8000")
        assert not is_valid, "Should block 127.0.0.1"
    
    def test_ssrf_protector_blocks_private_ips(self):
        """Test that SSRFProtector blocks private IPs."""
        from app.utils.ssrf_protector import SSRFProtector
        
        protector = SSRFProtector()
        
        # Test private IP ranges
        is_valid, error = protector.validate_url("http://192.168.1.1")
        assert not is_valid, "Should block private IP 192.168.x.x"
        
        is_valid, error = protector.validate_url("http://10.0.0.1")
        assert not is_valid, "Should block private IP 10.x.x.x"
        
        is_valid, error = protector.validate_url("http://172.16.0.1")
        assert not is_valid, "Should block private IP 172.16.x.x"
    
    def test_ssrf_protector_blocks_dangerous_schemes(self):
        """Test that SSRFProtector blocks dangerous URL schemes."""
        from app.utils.ssrf_protector import SSRFProtector
        
        protector = SSRFProtector()
        
        # Test blocked schemes
        is_valid, error = protector.validate_url("file:///etc/passwd")
        assert not is_valid, "Should block file:// scheme"
        
        is_valid, error = protector.validate_url("ftp://example.com")
        assert not is_valid, "Should block ftp:// scheme"
    
    def test_ssrf_protector_allows_valid_urls(self):
        """Test that SSRFProtector allows valid public URLs."""
        from app.utils.ssrf_protector import SSRFProtector
        
        protector = SSRFProtector()
        
        is_valid, error = protector.validate_url("https://www.google.com")
        assert is_valid, "Should allow public HTTPS URL"
        assert error is None
        
        is_valid, error = protector.validate_url("http://example.com")
        assert is_valid, "Should allow public HTTP URL"
        assert error is None
    
    def test_workflow_creation_validates_url(self, client, auth_headers):
        """Test that workflow creation validates URLs against SSRF."""
        # Try to create workflow with localhost URL
        response = client.post(
            "/api/workflows",
            headers=auth_headers,
            json={
                "name": "Test Workflow",
                "description": "Test",
                "app_name": "Test",
                "start_url": "http://localhost:8000"
            }
        )
        assert response.status_code == 400, "Should reject localhost URL"
        assert "Invalid start_url" in response.json()["detail"]

    def test_workflow_auto_populates_start_url_from_app_name(self, client, auth_headers):
        """Known app names should resolve to default URLs without manual start_url."""
        response = client.post(
            "/api/workflows",
            headers=auth_headers,
            json={
                "name": "GitHub Workflow",
                "description": "Test auto URL mapping",
                "app_name": "github",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["start_url"] == "https://github.com"


class TestPagination:
    """Test pagination from Phase 2."""
    
    def test_workflows_pagination(self, client, auth_headers, test_user, db):
        """Test workflows endpoint pagination."""
        from app.models.models import Workflow as WorkflowModel
        
        # Create multiple workflows
        for i in range(15):
            workflow = WorkflowModel(
                name=f"Test Workflow {i}",
                description=f"Test {i}",
                app_name="Test",
                start_url="https://example.com",
                owner_id=test_user.id
            )
            db.add(workflow)
        db.commit()
        
        # Test default pagination
        response = client.get("/api/workflows", headers=auth_headers)
        assert response.status_code == 200
        workflows = response.json()
        assert len(workflows) == 15, "Should return all workflows (under page limit)"
        
        # Test page size limit
        response = client.get("/api/workflows?page=1&page_size=5", headers=auth_headers)
        assert response.status_code == 200
        workflows = response.json()
        assert len(workflows) == 5, "Should respect page_size parameter"
        
        # Test second page
        response = client.get("/api/workflows?page=2&page_size=5", headers=auth_headers)
        assert response.status_code == 200
        workflows = response.json()
        assert len(workflows) == 5, "Should return second page"
    
    def test_executions_pagination(self, client, auth_headers):
        """Test executions endpoint pagination."""
        # Test with query parameters
        response = client.get("/api/executions?page=1&page_size=10", headers=auth_headers)
        assert response.status_code == 200
        
        # Test invalid page number
        response = client.get("/api/executions?page=0&page_size=10", headers=auth_headers)
        assert response.status_code == 422, "Should reject invalid page number"


class TestUserDataIsolation:
    """Test that users can only access their own data."""
    
    def test_users_see_only_own_workflows(self, client, db):
        """Test workflow data isolation."""
        # Create two users
        user1 = UserModel(
            email="user1@example.com",
            username="user1",
            hashed_password=get_password_hash("pass123"),
            is_active=True
        )
        user2 = UserModel(
            email="user2@example.com",
            username="user2",
            hashed_password=get_password_hash("pass123"),
            is_active=True
        )
        db.add(user1)
        db.add(user2)
        db.commit()
        db.refresh(user1)
        db.refresh(user2)
        
        # Create workflows for each user
        from app.models.models import Workflow as WorkflowModel
        
        workflow1 = WorkflowModel(
            name="User 1 Workflow",
            description="Test",
            app_name="Test",
            start_url="https://example.com",
            owner_id=user1.id
        )
        workflow2 = WorkflowModel(
            name="User 2 Workflow",
            description="Test",
            app_name="Test",
            start_url="https://example.com",
            owner_id=user2.id
        )
        db.add(workflow1)
        db.add(workflow2)
        db.commit()
        
        # Login as user1
        response = client.post(
            "/api/auth/login",
            data={"username": "user1", "password": "pass123"}
        )
        user1_token = response.json()["access_token"]
        user1_headers = {"Authorization": f"Bearer {user1_token}"}
        
        # User1 should only see their workflow
        response = client.get("/api/workflows", headers=user1_headers)
        workflows = response.json()
        assert len(workflows) == 1
        assert workflows[0]["name"] == "User 1 Workflow"
        
        # User1 should not be able to access user2's workflow
        response = client.get(f"/api/workflows/{workflow2.id}", headers=user1_headers)
        assert response.status_code == 404


class TestModularArchitecture:
    """Test modular components from Phase 2."""
    
    def test_loop_detector_exists(self):
        """Test that LoopDetector was extracted."""
        from app.automation.workflow.loop_detector import LoopDetector
        
        detector = LoopDetector(window_size=6)
        assert detector.window_size == 6
    
    def test_completion_checker_exists(self):
        """Test that CompletionChecker was extracted."""
        from app.automation.workflow.completion_checker import CompletionChecker
        
        checker = CompletionChecker()
        assert checker is not None
    
    def test_loop_detector_functionality(self):
        """Test LoopDetector detects loops."""
        from app.automation.workflow.loop_detector import LoopDetector
        
        detector = LoopDetector(window_size=4)
        
        # Create repetitive action history
        actions = [
            {"type": "click", "target_text": "Submit", "url": "http://example.com", "page_changed": False},
            {"type": "click", "target_text": "Submit", "url": "http://example.com", "page_changed": False},
            {"type": "click", "target_text": "Submit", "url": "http://example.com", "page_changed": False},
            {"type": "click", "target_text": "Submit", "url": "http://example.com", "page_changed": False},
        ]
        
        is_loop, reason = detector.detect_loop(actions)
        assert is_loop, "Should detect repetitive clicking"
        assert "same element" in reason.lower()


class TestHealthEndpoints:
    """Smoke tests for public health endpoints."""

    def test_root_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_api_health_includes_database(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] in ("healthy", "unavailable")


class TestConfiguration:
    """Test configuration management from Phase 2."""
    
    def test_workflow_constants_configured(self):
        """Test that hardcoded constants are now in config."""
        assert hasattr(settings, 'LOOP_DETECTION_WINDOW')
        assert hasattr(settings, 'MAX_INACTIVITY_SECONDS')
        assert hasattr(settings, 'MAX_ADAPTIVE_CYCLES')
        
        assert settings.LOOP_DETECTION_WINDOW == 6
        # Default raised 30s -> 90s: a single LLM decision can take 20-30s,
        # so 30s caused spurious inactivity timeouts mid-run.
        assert settings.MAX_INACTIVITY_SECONDS >= 30
        assert settings.MAX_ADAPTIVE_CYCLES == 6
        # New agent settings
        assert settings.AGENT_MAX_STEPS >= 1
        assert settings.active_llm_provider in ("openai", "anthropic", "none")
    
    def test_ssrf_configuration(self):
        """Test SSRF protection configuration."""
        assert hasattr(settings, 'BLOCKED_IP_RANGES')
        assert hasattr(settings, 'BLOCKED_URL_SCHEMES')
        assert hasattr(settings, 'ALLOWED_URL_SCHEMES')
        
        assert len(settings.BLOCKED_IP_RANGES) > 0
        assert "file" in settings.BLOCKED_URL_SCHEMES
        assert "http" in settings.ALLOWED_URL_SCHEMES


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])


class TestExecutionFeedback:
    """User feedback on executions feeds the learning system."""

    def test_feedback_recorded_on_execution(self, client, auth_headers, db, test_user):
        from app.models.models import Workflow as WF, Execution as EX, ExecutionStatus
        import json as _json

        wf = WF(name="fb-wf", app_name="example", description="task",
                owner_id=test_user.id, start_url="https://example.com")
        db.add(wf)
        db.commit()
        db.refresh(wf)
        ex = EX(workflow_id=wf.id, status=ExecutionStatus.SUCCESS,
                result=_json.dumps({"task": "task", "final_url": "https://example.com/x"}))
        db.add(ex)
        db.commit()
        db.refresh(ex)

        r = client.post(f"/api/executions/{ex.id}/feedback",
                        json={"rating": "negative", "notes": "missed the banner"},
                        headers=auth_headers)
        assert r.status_code == 200, r.text
        assert r.json()["rating"] == "negative"

        db.refresh(ex)
        stored = _json.loads(ex.result)
        assert stored["user_feedback"]["rating"] == "negative"
        assert stored["user_feedback"]["notes"] == "missed the banner"

    def test_feedback_requires_auth_and_validates(self, client, auth_headers):
        r = client.post("/api/executions/999/feedback", json={"rating": "positive"})
        assert r.status_code == 401
        r = client.post("/api/executions/999/feedback",
                        json={"rating": "meh"}, headers=auth_headers)
        assert r.status_code == 422  # invalid rating value
