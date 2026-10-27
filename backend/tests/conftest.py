import secrets

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import models  # noqa: F401
from app.db.base import Base
from app.main import create_app
from app.services.company import Mca21Provider
from app.services.ml import MlService
from app.services.pipeline import Detector
from app.services.types import DetectionPath


class FakePredictor:
    name, version, max_points = "tfidf", "fake:1", 20

    def __init__(self, prob=0.5, fail=False):
        self.prob, self.fail = prob, fail

    def predict(self, text):
        if self.fail:
            raise RuntimeError("boom")
        return self.prob


def make_settings(**kw) -> Settings:
    base = dict(database_url="sqlite://", cors_origins="http://localhost:5173", rate_limit_per_minute=1000, mca_api_key="")
    base.update(kw)
    # Tests must not inherit developer credentials from backend/.env or make live requests.
    return Settings(**base, _env_file=None)


def make_detector(predictors=None, registry=None, settings=None) -> Detector:
    settings = settings or make_settings()
    preds = [FakePredictor()] if predictors is None else predictors
    ml = MlService(preds, [DetectionPath("distilbert", "not_configured", "test")])
    return Detector(ml=ml, registry=registry or Mca21Provider(settings))


def make_client(settings=None, detector=None) -> TestClient:
    settings = settings or make_settings()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    app = create_app(settings, detector or make_detector(settings=settings), engine)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client():
    return make_client()


@pytest.fixture
def token():
    return secrets.token_urlsafe(32)


@pytest.fixture
def auth(token):
    return {"X-Session-Token": token}


SCAM_TEXT = ("Urgent hiring! Work from home data entry job. Earn Rs 45000 per month. No experience needed. Only 3 seats left. "
             "Pay Rs 999 registration fee before joining. Daily payment via UPI. Work timing 24/7 you can work anytime. "
             "Contact: hr.nexgen2024@gmail.com")
REAL_TEXT = ("Infosys hiring Software Engineers for Bangalore office. 0-2 years Java and Spring Boot experience required. "
             "CTC 4.5 LPA. Apply at careers.infosys.com. Contact: hr@infosys.com. No fee charged at any stage.")
