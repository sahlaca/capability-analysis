from __future__ import annotations

from functools import lru_cache
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .analytics import AnalyticsService, DatasetUnavailable

app = FastAPI(
    title="Capability Analysis API",
    version="1.0.0",
    description="Complexity-weighted student capability, cohort placement, and transparent recommendations.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8080", "http://127.0.0.1:8080"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def get_analytics() -> AnalyticsService:
    try:
        return AnalyticsService()
    except DatasetUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/health")
def health() -> dict:
    try:
        service = get_analytics()
        return {"status": "ok", "data_ready": True, "students": len(service.student_ids)}
    except HTTPException as exc:
        return {"status": "needs_data", "data_ready": False, "detail": str(exc.detail)}


@app.get("/api/overview")
def overview() -> dict:
    return get_analytics().overview()


@app.get("/api/students")
def search_students(q: str = Query(default="", max_length=30), limit: int = Query(default=20, ge=1, le=100)) -> dict:
    service = get_analytics()
    matches = [student_id for student_id in service.student_ids if q in str(student_id)][:limit]
    return {"student_ids": matches, "count": len(matches)}


@app.get("/api/students/lookup")
def student_profile_by_email(email: str = Query(min_length=3, max_length=254)) -> dict:
    service = get_analytics()
    user_ids = service.find_students_by_email(email)
    if not user_ids:
        raise HTTPException(status_code=404, detail="No student was found for that email address.")
    accounts = service.account_choices(user_ids)
    if len(accounts) > 1:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "This email is associated with multiple student accounts. Select the correct student account.",
                "accounts": accounts,
            },
        )
    if not accounts:
        raise HTTPException(status_code=404, detail="No capability results were found for that email address.")
    profile = service.student_profile(accounts[0]["user_id"])
    if profile is None:
        raise HTTPException(status_code=404, detail="No capability results were found for that email address.")
    return profile


@app.get("/api/students/{user_id}")
def student_profile(user_id: int) -> dict:
    profile = get_analytics().student_profile(user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Student not found in the processed dataset.")
    return profile


@app.get("/api/students/{user_id}/placement")
def placement(user_id: int, topic: str = Query(min_length=1, max_length=100)) -> dict:
    result = get_analytics().peers(user_id, topic)
    if result["student_score_pct"] is None:
        raise HTTPException(status_code=404, detail="No result for this student and topic.")
    return result


@app.get("/api/students/{user_id}/recommendations")
def recommendations(
    user_id: int,
    limit: int = Query(default=5, ge=1, le=20),
    topic: Optional[str] = Query(default=None, min_length=1, max_length=100),
) -> dict:
    service = get_analytics()
    if service.student_profile(user_id) is None:
        raise HTTPException(status_code=404, detail="Student not found in the processed dataset.")
    return service.recommendations(user_id, limit, topic)
