#!/bin/sh
set -eu

SUMMARY="${CAPABILITY_SUMMARY_PATH:-/app/data/processed/student_topic_summary.csv}"
EMAIL_INDEX="${CAPABILITY_EMAIL_LOOKUP_PATH:-/app/data/processed/student_email_lookup.csv}"
CHAPTER_SUMMARY="${CAPABILITY_CHAPTER_SUMMARY_PATH:-/app/data/processed/student_latest_chapter_summary.csv}"

if [ ! -s "$SUMMARY" ] || [ ! -s "$EMAIL_INDEX" ] || [ ! -s "$CHAPTER_SUMMARY" ]; then
    echo "Prepared datasets missing; running the one-time DuckDB preparation step..."
    python /app/scripts/prepare_dataset.py
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
