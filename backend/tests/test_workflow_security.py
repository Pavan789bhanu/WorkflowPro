"""Security-focused tests for workflow credential handling and ownership."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import Base, get_db
from app.models.models import User as UserModel, Workflow as WorkflowModel
from app.core.security import get_password_hash
from app.core.encryption import decrypt_password, resolve_stored_password

import os
import tempfile

# Keep the test DB in a temp dir — avoids littering the repo and works on
# network-mounted filesystems where SQLite locking can fail.
_TEST_DB = os.path.join(tempfile.mkdtemp(prefix='workflowpro_test_'), 'test_workflow_security.db')
SQLALCHEMY_DATABASE_URL = f"sqlite:///{_TEST_DB}"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _create_user(db, username: str, email: str, password: str = "pass123") -> UserModel:
    user = UserModel(
        email=email,
        username=username,
        hashed_password=get_password_hash(password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_headers(client: TestClient, username: str, password: str = "pass123") -> dict:
    response = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestWorkflowCredentialSecurity:
    def test_create_workflow_encrypts_password_at_rest(self, client, db):
        user = _create_user(db, "owner", "owner@example.com")
        headers = _auth_headers(client, "owner")

        response = client.post(
            "/api/workflows",
            headers=headers,
            json={
                "name": "Secure Workflow",
                "description": "Credential test",
                "app_name": "Test",
                "start_url": "https://example.com",
                "login_email": "user@example.com",
                "login_password": "super-secret",
            },
        )
        assert response.status_code == 200

        stored = db.query(WorkflowModel).filter(WorkflowModel.owner_id == user.id).first()
        assert stored is not None
        assert stored.login_password_encrypted != "super-secret"
        assert decrypt_password(stored.login_password_encrypted) == "super-secret"
        assert resolve_stored_password(stored.login_password_encrypted) == "super-secret"

    def test_workflow_api_never_returns_stored_password(self, client, db):
        _create_user(db, "owner", "owner@example.com")
        headers = _auth_headers(client, "owner")

        create_response = client.post(
            "/api/workflows",
            headers=headers,
            json={
                "name": "Masked Workflow",
                "app_name": "Test",
                "start_url": "https://example.com",
                "login_password": "hidden-value",
            },
        )
        workflow_id = create_response.json()["id"]

        get_response = client.get(f"/api/workflows/{workflow_id}", headers=headers)
        assert get_response.status_code == 200
        assert get_response.json()["login_password"] is None

        list_response = client.get("/api/workflows", headers=headers)
        assert list_response.status_code == 200
        assert list_response.json()[0]["login_password"] is None


class TestWorkflowOwnership:
    def test_user_cannot_delete_another_users_workflow(self, client, db):
        user1 = _create_user(db, "user1", "user1@example.com")
        _create_user(db, "user2", "user2@example.com")

        workflow = WorkflowModel(
            name="User 2 Workflow",
            description="Protected",
            app_name="Test",
            start_url="https://example.com",
            owner_id=user1.id,
        )
        db.add(workflow)
        db.commit()
        db.refresh(workflow)

        user2_headers = _auth_headers(client, "user2")
        response = client.delete(f"/api/workflows/{workflow.id}", headers=user2_headers)
        assert response.status_code == 404

        remaining = db.query(WorkflowModel).filter(WorkflowModel.id == workflow.id).first()
        assert remaining is not None
