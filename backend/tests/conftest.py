import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def illustrative_request() -> dict[str, object]:
    return json.loads((FIXTURES / "illustrative_optimize_request.json").read_text())
