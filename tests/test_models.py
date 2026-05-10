import os

import pytest
from google import genai

# We skip these tests if credentials are not available
# or if we don't want to hit the API during normal test runs.
pytestmark = pytest.mark.skipif(not os.environ.get("GCP_PROJECT_ID"), reason="GCP_PROJECT_ID not set, skipping API tests")


@pytest.fixture(scope="module")
def client():
    project = os.environ.get("GCP_PROJECT_ID", "gen-ai-exposure")
    location = os.environ.get("GCP_LOCATION", "us-central1")
    return genai.Client(vertexai=True, project=project, location=location)


models_to_test = [
    "gemini-1.5-flash-001",
    "gemini-1.5-flash-002",
    "gemini-1.5-flash",
    "gemini-3.0-flash",
    "gemini-3-flash-001",
    "gemini-pro",
]


@pytest.mark.parametrize("model_name", models_to_test)
def test_model_availability(client, model_name):
    """Test if the specified model is available and can generate content."""
    try:
        response = client.models.generate_content(model=model_name, contents="x")
        assert response is not None
        assert response.text is not None
    except Exception as e:
        pytest.fail(f"Model {model_name} failed: {str(e)}")
