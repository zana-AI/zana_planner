import asyncio

import httpx
from fastapi import FastAPI

from services.learning_pipeline.embedding_service import VectorStoreUnavailableError
from webapp.dependencies import get_current_user
from webapp.routers import content as content_router


class _ASGITestClient:
    """Sync wrapper around httpx.AsyncClient + ASGITransport (works with httpx 0.28+)."""

    def __init__(self, app, base_url: str = "http://testserver"):
        self._app = app
        self._base_url = base_url

    def _request(self, method: str, url: str, **kwargs):
        async def _run():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self._app),
                base_url=self._base_url,
            ) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(_run())

    def get(self, url: str, **kwargs):
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self._request("POST", url, **kwargs)

    def patch(self, url: str, **kwargs):
        return self._request("PATCH", url, **kwargs)


def TestClient(app, base_url: str = "http://testserver"):
    return _ASGITestClient(app, base_url)


class FakeLearningService:
    def __init__(self):
        self.last_submit_kwargs = {}

    def enqueue_analysis(self, user_id, content_id, force_rebuild=False):
        return {"job_id": "job-1", "status": "pending", "stage": "queued", "progress_pct": 0}

    def get_job_status(self, job_id, user_id):
        return {"job_id": job_id, "status": "running", "stage": "fetch", "progress_pct": 20}

    def get_summary(self, content_id, user_id, level):
        return {"level": level, "summary": {"summary": "ok"}, "model_name": "heuristic", "created_at": "now"}

    def ask(self, content_id, user_id, question):
        return {"answer": "answer", "citations": [], "confidence": 0.5, "model_name": "heuristic"}

    def create_quiz(self, content_id, user_id, difficulty="medium", question_count=8):
        return {
            "quiz_set_id": "quiz-1",
            "questions": [{"question_id": "q1", "prompt": "p", "options": ["a"]}],
            "difficulty": difficulty,
        }

    def submit_quiz(self, user_id, quiz_set_id, answers, idempotency_key=None):
        self.last_submit_kwargs = {
            "user_id": user_id,
            "quiz_set_id": quiz_set_id,
            "answers": answers,
            "idempotency_key": idempotency_key,
        }
        return {
            "attempt_id": "attempt-1",
            "score": 1.0,
            "max_score": 1.0,
            "per_question_feedback": [],
            "mastery_updates": [],
        }

    def get_concepts(self, content_id, user_id):
        return {"nodes": [], "edges": []}


def _build_app(fake_service: FakeLearningService, with_auth_override: bool = True) -> FastAPI:
    app = FastAPI()
    app.include_router(content_router.router)
    if with_auth_override:
        app.dependency_overrides[get_current_user] = lambda: 12345
    content_router.get_learning_service = lambda: fake_service
    app.state.bot_token = "test-bot-token"
    return app


def test_analyze_and_job_status_endpoints_contract():
    fake_service = FakeLearningService()
    app = _build_app(fake_service)
    client = TestClient(app)

    analyze_response = client.post("/api/content/content-1/analyze", json={"force_rebuild": True})
    assert analyze_response.status_code == 200
    payload = analyze_response.json()
    assert payload["job_id"] == "job-1"
    assert payload["status"] == "pending"

    job_response = client.get("/api/content/jobs/job-1")
    assert job_response.status_code == 200
    assert job_response.json()["stage"] == "fetch"


def test_submit_quiz_passes_idempotency_key():
    fake_service = FakeLearningService()
    app = _build_app(fake_service)
    client = TestClient(app)

    response = client.post(
        "/api/quiz/quiz-1/submit",
        headers={"Idempotency-Key": "idem-1"},
        json={"answers": [{"question_id": "q1", "answer": "a"}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["attempt_id"] == "attempt-1"
    assert fake_service.last_submit_kwargs["idempotency_key"] == "idem-1"
    assert fake_service.last_submit_kwargs["answers"][0]["question_id"] == "q1"


def test_ask_endpoint_rejects_empty_question():
    fake_service = FakeLearningService()
    app = _build_app(fake_service)
    client = TestClient(app)

    response = client.post("/api/content/content-1/ask", json={"question": ""})
    assert response.status_code == 422


def test_create_quiz_rejects_invalid_difficulty():
    fake_service = FakeLearningService()
    app = _build_app(fake_service)
    client = TestClient(app)

    response = client.post(
        "/api/content/content-1/quiz",
        json={"difficulty": "extreme", "question_count": 5},
    )
    assert response.status_code == 422


def test_analyze_returns_503_when_pipeline_disabled():
    class DisabledService(FakeLearningService):
        def enqueue_analysis(self, user_id, content_id, force_rebuild=False):
            raise RuntimeError("Content learning pipeline is disabled")

    app = _build_app(DisabledService())
    client = TestClient(app)

    response = client.post("/api/content/content-1/analyze", json={"force_rebuild": False})
    assert response.status_code == 503


def test_ask_returns_503_when_vector_store_unavailable():
    class VectorDownService(FakeLearningService):
        def ask(self, content_id, user_id, question):
            raise VectorStoreUnavailableError("Qdrant unavailable")

    app = _build_app(VectorDownService())
    client = TestClient(app)

    response = client.post("/api/content/content-1/ask", json={"question": "What is this about?"})
    assert response.status_code == 503
    body = response.json()
    assert body["detail"]["retryable"] is True


def test_ask_endpoint_passes_user_id():
    class CapturingService(FakeLearningService):
        def __init__(self):
            super().__init__()
            self.last_user_id = None

        def ask(self, content_id, user_id, question):
            self.last_user_id = user_id
            return super().ask(content_id, user_id, question)

    service = CapturingService()
    app = _build_app(service)
    client = TestClient(app)

    response = client.post("/api/content/content-1/ask", json={"question": "What is this about?"})
    assert response.status_code == 200
    assert service.last_user_id == 12345


def test_ask_returns_404_when_user_content_missing():
    class MissingContentService(FakeLearningService):
        def ask(self, content_id, user_id, question):
            raise ValueError("User content not found")

    app = _build_app(MissingContentService())
    client = TestClient(app)

    response = client.post("/api/content/content-1/ask", json={"question": "What is this about?"})
    assert response.status_code == 404


def test_auth_required_when_not_overridden():
    fake_service = FakeLearningService()
    app = _build_app(fake_service, with_auth_override=False)
    client = TestClient(app)

    response = client.post("/api/content/content-1/analyze", json={"force_rebuild": False})
    assert response.status_code == 401
