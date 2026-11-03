import csv
import hashlib
import hmac
from pathlib import Path

import app.analytics as analytics
from app.analytics import AnalyticsService, DatasetUnavailable


def write_summary(path: Path) -> None:
    rows = [
        {"user_id": 10, "topic": "SQL", "test_date": "2025-01-01", "tests_attempted": 1,
         "total_questions": 10, "total_correct": 8, "weighted_score": 16, "max_score": 20, "score_pct": 80},
        {"user_id": 10, "topic": "SQL", "test_date": "2025-02-01", "tests_attempted": 1,
         "total_questions": 10, "total_correct": 6, "weighted_score": 12, "max_score": 20, "score_pct": 60},
        {"user_id": 20, "topic": "SQL", "test_date": "2025-01-01", "tests_attempted": 1,
         "total_questions": 20, "total_correct": 12, "weighted_score": 24, "max_score": 40, "score_pct": 60},
        {"user_id": 20, "topic": "Python", "test_date": "2025-01-01", "tests_attempted": 1,
         "total_questions": 10, "total_correct": 9, "weighted_score": 27, "max_score": 30, "score_pct": 90},
        {"user_id": 30, "topic": "Python", "test_date": "2025-01-01", "tests_attempted": 1,
         "total_questions": 15, "total_correct": 12, "weighted_score": 24, "max_score": 30, "score_pct": 80},
        {"user_id": 31, "topic": "Python", "test_date": "2025-01-01", "tests_attempted": 1,
         "total_questions": 10, "total_correct": 7, "weighted_score": 21, "max_score": 30, "score_pct": 70},
        {"user_id": 32, "topic": "Python", "test_date": "2025-01-01", "tests_attempted": 1,
         "total_questions": 10, "total_correct": 6, "weighted_score": 18, "max_score": 30, "score_pct": 60},
        {"user_id": 33, "topic": "Python", "test_date": "2025-01-01", "tests_attempted": 1,
         "total_questions": 10, "total_correct": 5, "weighted_score": 15, "max_score": 30, "score_pct": 50},
        {"user_id": 34, "topic": "Python", "test_date": "2025-01-01", "tests_attempted": 1,
         "total_questions": 10, "total_correct": 4, "weighted_score": 12, "max_score": 30, "score_pct": 40},
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def test_profile_aggregates_weighted_scores_and_attempts(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "summary.csv"
    write_summary(path)
    monkeypatch.setattr(analytics, "EMAIL_LOOKUP_PATH", tmp_path / "not-generated.csv")
    monkeypatch.setattr(analytics, "CHAPTER_SUMMARY_PATH", tmp_path / "no-chapters.csv")
    service = AnalyticsService(path)

    profile = service.student_profile(10)

    assert profile is not None
    assert profile["overall_score_pct"] == 70.0
    assert profile["questions_seen"] == 20
    sql_topic = next(topic for topic in profile["topics"] if topic["topic"] == "SQL")
    assert sql_topic["tests_attempted"] == 2
    assert profile["topics"][0]["confidence"] == "developing"


def test_peer_placement_and_similar_students(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "summary.csv"
    write_summary(path)
    monkeypatch.setattr(analytics, "EMAIL_LOOKUP_PATH", tmp_path / "not-generated.csv")
    monkeypatch.setattr(analytics, "CHAPTER_SUMMARY_PATH", tmp_path / "no-chapters.csv")
    service = AnalyticsService(path)

    result = service.peers(10, "SQL")

    assert result["student_score_pct"] == 70.0
    assert result["percentile"] == 100.0
    assert result["peers"][0]["user_id"] == 20


def test_recommendations_separate_focus_and_explore(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "summary.csv"
    write_summary(path)
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "user_id", "topic", "test_date", "tests_attempted", "total_questions",
            "total_correct", "weighted_score", "max_score", "score_pct",
        ])
        for topic, score in [("Java", 75), ("R", 70), ("Data", 65), ("Fallback", 60)]:
            user_id = 20 if topic != "Fallback" else 40
            writer.writerow({"user_id": user_id, "topic": topic, "test_date": "2025-01-01",
                             "tests_attempted": 1, "total_questions": 10, "total_correct": 7,
                             "weighted_score": score * 0.3, "max_score": 30, "score_pct": score})
    monkeypatch.setattr(analytics, "EMAIL_LOOKUP_PATH", tmp_path / "not-generated.csv")
    monkeypatch.setattr(analytics, "CHAPTER_SUMMARY_PATH", tmp_path / "no-chapters.csv")
    service = AnalyticsService(path)

    suggestions = service.recommendations(10)

    assert suggestions["topic_recommendations"][0]["kind"] == "similar_students"
    assert suggestions["topic_recommendations"][0]["topic"] == "Python"
    assert suggestions["topic_recommendations"][0]["similar_students_count"] == 1
    assert len(suggestions["topic_recommendations"]) == 5
    assert any(item["kind"] == "popular_fallback" for item in suggestions["topic_recommendations"])


def test_latest_test_chapter_focus_is_scoped_to_selected_topic(tmp_path: Path, monkeypatch) -> None:
    summary = tmp_path / "summary.csv"
    write_summary(summary)
    chapter_path = tmp_path / "chapters.csv"
    rows = [
        {"user_id": 10, "topic": "SQL", "test_date": "2025-02-01", "chapter_name": "Joins",
         "tests_attempted": 1, "total_questions": 5, "total_correct": 2, "weighted_score": 2,
         "max_score": 5, "score_pct": 40},
        {"user_id": 10, "topic": "SQL", "test_date": "2025-02-01", "chapter_name": "Indexes",
         "tests_attempted": 1, "total_questions": 5, "total_correct": 4, "weighted_score": 4,
         "max_score": 5, "score_pct": 80},
        {"user_id": 10, "topic": "SQL", "test_date": "2025-01-01", "chapter_name": "Old chapter",
         "tests_attempted": 1, "total_questions": 5, "total_correct": 0, "weighted_score": 0,
         "max_score": 5, "score_pct": 0},
    ]
    with chapter_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    monkeypatch.setattr(analytics, "EMAIL_LOOKUP_PATH", tmp_path / "not-generated.csv")
    monkeypatch.setattr(analytics, "CHAPTER_SUMMARY_PATH", chapter_path)
    service = AnalyticsService(summary)

    result = service.recommendations(10, topic="SQL")

    assert result["chapter_test_date"] == "2025-02-01"
    assert [item["chapter"] for item in result["chapter_recommendations"]] == ["Joins"]
    assert result["chapter_recommendations"][0]["score_pct"] == 40.0


def test_missing_prepared_dataset_is_actionable(tmp_path: Path) -> None:
    try:
        AnalyticsService(tmp_path / "missing.csv")
    except DatasetUnavailable as exc:
        assert "Run the data preparation script" in str(exc)
    else:
        raise AssertionError("Expected DatasetUnavailable")


def test_email_lookup_is_case_insensitive_and_reports_shared_addresses(tmp_path: Path, monkeypatch) -> None:
    summary = tmp_path / "summary.csv"
    write_summary(summary)
    lookup = tmp_path / "lookup.csv"
    secret = "test-secret"
    digest = hmac.new(secret.encode(), b"same@example.com", hashlib.sha256).hexdigest()
    with lookup.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["user_id", "full_name", "email_hmac"])
        writer.writeheader()
        writer.writerows([
            {"user_id": 10, "full_name": "Student Ten", "email_hmac": digest},
            {"user_id": 20, "full_name": "Student Twenty", "email_hmac": digest},
        ])
    monkeypatch.setattr(analytics, "EMAIL_LOOKUP_PATH", lookup)
    monkeypatch.setattr(analytics, "EMAIL_LOOKUP_SECRET", secret)
    service = AnalyticsService(summary)

    assert service.find_students_by_email(" SAME@Example.com ") == [10, 20]
    assert service.account_choices([10, 20]) == [
        {"user_id": 10, "full_name": "Student Ten"},
        {"user_id": 20, "full_name": "Student Twenty"},
    ]
    similar = service.peers(10, "SQL")["peers"][0]
    assert similar["full_name"] == "Student Twenty"
    assert similar["difference"] == -10.0
    assert service.find_students_by_email("missing@example.com") == []
