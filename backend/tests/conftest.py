import os
import tempfile
from pathlib import Path

test_root = Path(tempfile.gettempdir()) / "autode-auth-pytest"
test_root.mkdir(parents=True, exist_ok=True)
os.environ["JWT_SECRET"] = "autode-test-signing-value-is-long-enough-0123456789"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["AUTODE_DATA_DIR"] = str(test_root)
os.environ["DATABASE_URL"] = f"sqlite:///{test_root / 'test.db'}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import Base, app, engine, reset_rate_limits  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    reset_rate_limits()
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def register_user(client: TestClient, email: str, password: str = "long-test-password-123", org_name: str = "Test Org") -> dict:
    response = client.post("/auth/register", json={"email": email, "password": password, "organization_name": org_name})
    assert response.status_code == 201, response.text
    return response.json()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
