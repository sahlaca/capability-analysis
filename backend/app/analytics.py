from __future__ import annotations

import csv
import hashlib
import hmac
import math
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


SUMMARY_PATH = Path(
    os.getenv(
        "CAPABILITY_SUMMARY_PATH",
        Path(__file__).resolve().parents[1] / "data" / "processed" / "student_topic_summary.csv",
    )
)
EMAIL_LOOKUP_PATH = Path(
    os.getenv(
        "CAPABILITY_EMAIL_LOOKUP_PATH",
        Path(__file__).resolve().parents[1] / "data" / "processed" / "student_email_lookup.csv",
    )
)
EMAIL_LOOKUP_SECRET = os.getenv("CAPABILITY_EMAIL_LOOKUP_SECRET", "local-development-only-change-me")
CHAPTER_SUMMARY_PATH = Path(
    os.getenv(
        "CAPABILITY_CHAPTER_SUMMARY_PATH",
        Path(__file__).resolve().parents[1] / "data" / "processed" / "student_latest_chapter_summary.csv",
    )
)


@dataclass(frozen=True)
class TopicScore:
    user_id: int
    topic: str
    tests_attempted: int
    total_questions: int
    total_correct: int
    weighted_score: float
    max_score: float

    @property
    def score_pct(self) -> float:
        return round(100 * self.weighted_score / self.max_score, 2) if self.max_score else 0.0

    @property
    def confidence(self) -> str:
        if self.total_questions < 10:
            return "early"
        if self.total_questions < 30:
            return "developing"
        return "established"

    @property
    def level(self) -> str:
        if self.score_pct >= 80:
            return "Strong"
        if self.score_pct >= 60:
            return "Capable"
        if self.score_pct >= 40:
            return "Developing"
        return "Needs support"

    def as_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "tests_attempted": self.tests_attempted,
            "total_questions": self.total_questions,
            "total_correct": self.total_correct,
            "weighted_score": round(self.weighted_score, 2),
            "max_score": round(self.max_score, 2),
            "score_pct": self.score_pct,
            "level": self.level,
            "confidence": self.confidence,
        }


class DatasetUnavailable(RuntimeError):
    pass


class AnalyticsService:
    """Loads the compact, pre-aggregated summary; never reads the raw export in a request."""

    REQUIRED_COLUMNS = {
        "user_id", "topic", "test_date", "tests_attempted", "total_questions",
        "total_correct", "weighted_score", "max_score",
    }

    def __init__(self, path: Path = SUMMARY_PATH) -> None:
        self.path = path
        self.scores: dict[tuple[int, str], TopicScore] = {}
        self.topics: set[str] = set()
        self.email_to_ids: dict[str, set[int]] = defaultdict(set)
        self.student_names: dict[int, str] = {}
        self.latest_chapters: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            raise DatasetUnavailable(
                f"Processed dataset not found at {self.path}. Run the data preparation script first."
            )
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = set(reader.fieldnames or [])
            missing = self.REQUIRED_COLUMNS - headers
            if missing:
                raise DatasetUnavailable(f"Processed dataset is missing columns: {', '.join(sorted(missing))}")

            totals: dict[tuple[int, str], dict[str, float]] = defaultdict(
                lambda: {"tests": 0, "questions": 0, "correct": 0, "weighted": 0.0, "maximum": 0.0}
            )
            test_dates: dict[tuple[int, str], set[tuple[str, str]]] = defaultdict(set)
            for row in reader:
                try:
                    user_id = int(float(row["user_id"]))
                    if user_id <= 0:
                        continue
                    topic = (row["topic"] or "").strip()
                    if not topic:
                        continue
                    key = (user_id, topic)
                    totals[key]["questions"] += int(float(row["total_questions"] or 0))
                    totals[key]["correct"] += int(float(row["total_correct"] or 0))
                    totals[key]["weighted"] += float(row["weighted_score"] or 0)
                    totals[key]["maximum"] += float(row["max_score"] or 0)
                    test_dates[key].add((row.get("test_date", ""), str(row.get("tests_attempted", ""))))
                except (TypeError, ValueError):
                    continue

        for key, values in totals.items():
            test_count = sum(int(float(date_count or 0)) for _, date_count in test_dates[key])
            self.scores[key] = TopicScore(
                user_id=key[0], topic=key[1], tests_attempted=test_count,
                total_questions=int(values["questions"]), total_correct=int(values["correct"]),
                weighted_score=values["weighted"], max_score=values["maximum"],
            )
        self.topics = {topic for _, topic in self.scores}

        if EMAIL_LOOKUP_PATH.exists():
            with EMAIL_LOOKUP_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if not {"user_id", "full_name", "email_hmac"}.issubset(reader.fieldnames or []):
                    raise DatasetUnavailable("Email lookup index has an invalid schema; rerun data preparation.")
                for row in reader:
                    try:
                        user_id = int(row["user_id"])
                        digest = row["email_hmac"]
                    except (TypeError, ValueError):
                        continue
                    self.email_to_ids[digest].add(user_id)
                    full_name = (row.get("full_name") or "").strip()
                    if full_name:
                        self.student_names.setdefault(user_id, full_name)

        if CHAPTER_SUMMARY_PATH.exists():
            with CHAPTER_SUMMARY_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                required = {"user_id", "topic", "test_date", "chapter_name", "total_questions", "score_pct"}
                if not required.issubset(reader.fieldnames or []):
                    raise DatasetUnavailable("Latest chapter summary has an invalid schema; rerun data preparation.")
                for row in reader:
                    try:
                        key = (int(row["user_id"]), row["topic"].strip())
                        self.latest_chapters[key].append({
                            "chapter": row["chapter_name"].strip() or "General",
                            "test_date": row["test_date"],
                            "total_questions": int(float(row["total_questions"] or 0)),
                            "score_pct": round(float(row["score_pct"] or 0), 2),
                        })
                    except (TypeError, ValueError):
                        continue

    @property
    def student_ids(self) -> list[int]:
        return sorted({user_id for user_id, _ in self.scores})

    def overview(self) -> dict[str, Any]:
        return {
            "students": len(self.student_ids),
            "topics": len(self.topics),
            "topic_names": sorted(self.topics),
            "summary_file": self.path.name,
        }

    def find_students_by_email(self, email: str) -> list[int]:
        if not EMAIL_LOOKUP_PATH.exists():
            raise DatasetUnavailable("Email lookup index is missing. Run the data preparation script first.")
        normalized = email.strip().casefold()
        digest = hmac.new(EMAIL_LOOKUP_SECRET.encode("utf-8"), normalized.encode("utf-8"), hashlib.sha256).hexdigest()
        return sorted(self.email_to_ids.get(digest, set()))

    def account_choices(self, user_ids: list[int]) -> list[dict[str, Any]]:
        return [
            {"user_id": user_id, "full_name": self.student_names.get(user_id) or f"Student {user_id}"}
            for user_id in user_ids
            if self.student_profile(user_id) is not None
        ]

    def student_profile(self, user_id: int) -> Optional[dict[str, Any]]:
        scores = [score for (candidate_id, _), score in self.scores.items() if candidate_id == user_id]
        if not scores:
            return None
        combined_max = sum(score.max_score for score in scores)
        combined_weighted = sum(score.weighted_score for score in scores)
        combined_questions = sum(score.total_questions for score in scores)
        overall_pct = round(100 * combined_weighted / combined_max, 2) if combined_max else 0.0
        return {
            "user_id": user_id,
            "overall_score_pct": overall_pct,
            "overall_level": self._level(overall_pct),
            "confidence": self._confidence(combined_questions),
            "questions_seen": combined_questions,
            "topics": [score.as_dict() for score in sorted(scores, key=lambda item: item.topic.lower())],
        }

    def peers(self, user_id: int, topic: str, limit: int = 5) -> dict[str, Any]:
        subject = self.scores.get((user_id, topic))
        if subject is None:
            return {"topic": topic, "student_score_pct": None, "percentile": None, "peers": []}
        cohort = [score for (candidate_id, candidate_topic), score in self.scores.items() if candidate_topic == topic]
        cohort.sort(key=lambda score: (score.score_pct, score.user_id))
        percentile = round(100 * sum(score.score_pct <= subject.score_pct for score in cohort) / len(cohort), 1)
        neighbors = sorted(
            (score for score in cohort if score.user_id != user_id),
            key=lambda score: (abs(score.score_pct - subject.score_pct), score.user_id),
        )[:limit]
        return {
            "topic": topic,
            "student_score_pct": subject.score_pct,
            "percentile": percentile,
            "cohort_size": len(cohort),
            "placement_label": self._level(subject.score_pct),
            "peers": [
                {
                    "user_id": score.user_id,
                    "full_name": self.student_names.get(score.user_id) or f"Student {score.user_id}",
                    "score_pct": score.score_pct,
                    "difference": round(score.score_pct - subject.score_pct, 2),
                }
                for score in neighbors
            ],
        }

    def recommendations(self, user_id: int, limit: int = 5, topic: Optional[str] = None) -> dict[str, Any]:
        """Use neighborhood collaborative filtering for topics and latest-test chapter gaps."""
        taken = {subject for (candidate_id, subject) in self.scores if candidate_id == user_id}
        user_scores = {subject: score.score_pct for (candidate_id, subject), score in self.scores.items()
                       if candidate_id == user_id}

        # User-based collaborative filtering. Compare score profiles only on topics
        # both users attempted; shrink sparse overlaps so a single shared topic does
        # not make two students appear perfectly similar.
        neighbors: list[tuple[int, float]] = []
        for other_id in self.student_ids:
            if other_id == user_id:
                continue
            other_scores = {subject: score.score_pct for (candidate_id, subject), score in self.scores.items()
                            if candidate_id == other_id}
            shared = sorted(set(user_scores) & set(other_scores))
            if not shared:
                continue
            left = [user_scores[subject] for subject in shared]
            right = [other_scores[subject] for subject in shared]
            left_norm = math.sqrt(sum(value * value for value in left))
            right_norm = math.sqrt(sum(value * value for value in right))
            if not left_norm or not right_norm:
                continue
            cosine = sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)
            mean_gap = sum(abs(a - b) for a, b in zip(left, right)) / len(shared)
            similarity = max(0.0, cosine * (1 - mean_gap / 100) * len(shared) / (len(shared) + 2))
            if similarity > 0:
                neighbors.append((other_id, similarity))
        neighbors.sort(key=lambda item: (-item[1], item[0]))
        neighbors = neighbors[:50]

        topic_votes: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for neighbor_id, similarity in neighbors:
            for (candidate_id, candidate_topic), score in self.scores.items():
                if candidate_id == neighbor_id and candidate_topic not in taken:
                    topic_votes[candidate_topic].append((similarity, score.score_pct))

        collaborative: list[dict[str, Any]] = []
        for candidate_topic, votes in topic_votes.items():
            weight = sum(similarity for similarity, _ in votes)
            if not weight:
                continue
            peer_average = round(sum(similarity * score for similarity, score in votes) / weight, 2)
            collaborative.append({
                "topic": candidate_topic,
                "kind": "similar_students",
                "similar_students_count": len(votes),
                "similarity_weight": round(weight, 3),
                "peer_average_pct": peer_average,
                "reason": f"Taken by {len(votes)} similar student(s); ranked by similarity and their results.",
            })
        collaborative.sort(
            key=lambda item: (-item["similarity_weight"], -item["peer_average_pct"], item["topic"].casefold())
        )

        selected = collaborative[:limit]
        selected_topics = {item["topic"] for item in selected}
        if len(selected) < limit:
            population: dict[str, list[float]] = defaultdict(list)
            for (candidate_id, candidate_topic), score in self.scores.items():
                if candidate_id != user_id and candidate_topic not in taken and candidate_topic not in selected_topics:
                    population[candidate_topic].append(score.score_pct)
            fallback = []
            for candidate_topic, scores in population.items():
                fallback.append({
                    "topic": candidate_topic,
                    "kind": "popular_fallback",
                    "students_count": len(scores),
                    "peer_average_pct": round(sum(scores) / len(scores), 2),
                    "reason": "General fallback: commonly taken by other students; not enough similar-peer evidence.",
                })
            fallback.sort(key=lambda item: (-item["students_count"], -item["peer_average_pct"], item["topic"].casefold()))
            selected.extend(fallback[:limit - len(selected)])

        chapters = []
        latest_test_date = None
        if topic:
            topic_chapters = self.latest_chapters.get((user_id, topic), [])
            if topic_chapters:
                latest_test_date = max(item["test_date"] for item in topic_chapters)
                chapters = [
                    {**item, "kind": "chapter_focus",
                     "reason": "Below 60% in the latest available test for this topic; review this chapter."}
                    for item in topic_chapters
                    if item["test_date"] == latest_test_date and item["score_pct"] < 60
                ]
                chapters.sort(key=lambda item: (item["score_pct"], item["chapter"].casefold()))

        return {
            "topic_recommendations": selected,
            "recommendation_basis": "similar students" if collaborative else "general popularity fallback",
            "similar_students_used": len(neighbors),
            "chapter_recommendations": chapters,
            "chapter_test_date": latest_test_date,
            "chapter_message": (
                "No chapters below 60% in the latest available test for this topic."
                if topic and not chapters and latest_test_date else
                "No latest-test chapter data is available for this topic." if topic and not latest_test_date else None
            ),
        }

    @staticmethod
    def _level(value: float) -> str:
        if value >= 80:
            return "Strong"
        if value >= 60:
            return "Capable"
        if value >= 40:
            return "Developing"
        return "Needs support"

    @staticmethod
    def _confidence(question_count: int) -> str:
        if question_count < 10:
            return "early"
        if question_count < 30:
            return "developing"
        return "established"
