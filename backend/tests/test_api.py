import csv
import hashlib
import hmac
from pathlib import Path

from fastapi.testclient import TestClient

import app.analytics as analytics
import app.main as api
from app.analytics import AnalyticsService


def test_student_profile_and_health_routes(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "summary.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "user_id", "topic", "test_date", "tests_attempted", "total_questions",
            "total_correct", "weighted_score", "max_score", "score_pct",
        ])
        writer.writeheader()
        writer.writerow({"user_id": 7, "topic": "SQL", "test_date": "2025-01-01",
                         "tests_attempted": 1, "total_questions": 12, "total_correct": 9,
                         "weighted_score": 18, "max_score": 24, "score_pct": 75})
    lookup = tmp_path / "lookup.csv"
    secret = "api-test-secret"
    digest = hmac.new(secret.encode(), b"student@example.com", hashlib.sha256).hexdigest()
    with lookup.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["user_id", "full_name", "email_hmac"])
        writer.writeheader()
        writer.writerow({"user_id": 7, "full_name": "Student Seven", "email_hmac": digest})
    monkeypatch.setattr(analytics, "EMAIL_LOOKUP_PATH", lookup)
    monkeypatch.setattr(analytics, "EMAIL_LOOKUP_SECRET", secret)
    monkeypatch.setattr(analytics, "CHAPTER_SUMMARY_PATH", tmp_path / "no-chapter-data.csv")
    monkeypatch.setattr(api, "get_analytics", lambda: AnalyticsService(path))

    with TestClient(api.app) as client:
        health = client.get("/api/health")
        student = client.get("/api/students/7")
        student_by_email = client.get("/api/students/lookup", params={"email": "STUDENT@example.com"})
        recommendations = client.get("/api/students/7/recommendations", params={"topic": "SQL"})
        not_found = client.get("/api/students/99")

    assert health.status_code == 200
    assert health.json()["data_ready"] is True
    assert student.status_code == 200
    assert student.json()["topics"][0]["score_pct"] == 75.0
    assert student_by_email.status_code == 200
    assert student_by_email.json()["user_id"] == 7
    assert recommendations.status_code == 200
    assert "topic_recommendations" in recommendations.json()
    assert recommendations.json()["chapter_message"] == "No latest-test chapter data is available for this topic."
    assert not_found.status_code == 404


def test_email_lookup_returns_account_choices_for_shared_address(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "summary.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "user_id", "topic", "test_date", "tests_attempted", "total_questions",
            "total_correct", "weighted_score", "max_score",
        ])
        writer.writeheader()
        for user_id in (7, 8):
            writer.writerow({"user_id": user_id, "topic": "SQL", "test_date": "2025-01-01",
                             "tests_attempted": 1, "total_questions": 12, "total_correct": 9,
                             "weighted_score": 18, "max_score": 24})
    lookup = tmp_path / "lookup.csv"
    secret = "shared-email-test"
    digest = hmac.new(secret.encode(), b"shared@example.com", hashlib.sha256).hexdigest()
    with lookup.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["user_id", "full_name", "email_hmac"])
        writer.writeheader()
        writer.writerows([
            {"user_id": 7, "full_name": "Alex One", "email_hmac": digest},
            {"user_id": 8, "full_name": "Alex Two", "email_hmac": digest},
        ])
    monkeypatch.setattr(analytics, "EMAIL_LOOKUP_PATH", lookup)
    monkeypatch.setattr(analytics, "EMAIL_LOOKUP_SECRET", secret)
    monkeypatch.setattr(api, "get_analytics", lambda: AnalyticsService(path))

    with TestClient(api.app) as client:
        response = client.get("/api/students/lookup", params={"email": "shared@example.com"})

    assert response.status_code == 409
    assert response.json()["detail"]["accounts"] == [
        {"user_id": 7, "full_name": "Alex One"},
        {"user_id": 8, "full_name": "Alex Two"},
    ]
