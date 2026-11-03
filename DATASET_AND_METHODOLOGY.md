# Dataset and methodology guide

This guide explains the rebuilt application from source CSV to dashboard, including which file is used, which columns are read, what is generated, and how to interpret the results. It is written for someone who is new to the project.

## 1. Source dataset selection

### Selected input

The preparation script defaults to:

- `../Final/final_revised.csv` from the project directory (the workspace file is `Final/final_revised.csv`, approximately 1.2 GB).
- This is the richest available attempt-level export: it contains student/test identifiers, topics, question identifiers, question type and complexity, selected choice IDs, correct-choice fields, chapters, and answer timestamps.
- It is read-only. The script does not copy or alter the original file.
- Student email-to-ID and display-name mapping comes separately from `../tables_chosen/tbl_users_1.csv` (`id`, `first_name`, `last_name`, `email`). Password hashes and other profile fields are ignored.

The default can be changed with `CAPABILITY_RAW_DATA`.
The user table can be changed with `CAPABILITY_USERS_DATA`.

### Other available files checked

These are not inputs to this full-topic application:

- `Final/MS_SQL.csv` is a smaller MS-SQL-specific export. It may be useful for a one-topic smoke test after its schema is adapted, but it does not represent every topic.
- `Final/cluster.csv`, `Final/performance.csv`, and `Final/app_performance.csv` are older derived summaries. They do not provide the response-level topic/date/item data required for the new pipeline, and some are single-topic outputs.
- Workspace-root `final_revised.csv` is a different 312 MB layout with duplicate/legacy column names and no `Inserted_Date_Time` in its header; it is not the selected input.
- `Final/question_revised.csv` is question metadata, not learner response history on its own.
- The standalone `tbl_answers*.csv` and `tbl_questionchoices.csv` files are database-table extracts that would require additional joins. The selected enriched export already contains the fields used for this initial build.

The raw export is large, so it is intentionally referenced rather than duplicated inside this project. Generated files are ignored by Git because they contain derived student-level information.

## 2. Raw columns used

`backend/scripts/prepare_dataset.py` reads these columns from `Final/final_revised.csv`:

| Source column | Purpose |
| --- | --- |
| `user_id` | Student identifier; records with ID zero or invalid IDs are excluded. Names and email addresses are not exported. |
| `test_id` | Distinguishes named test forms when counting tests. |
| `Question_Topic` | Groups topic-level scores, cohort comparisons, and recommendations. |
| `Question_Type` | Distinguishes single-choice (SCQ) and multiple-choice (MCQ) questions. |
| `questiontype_id` | Included in the source, but this initial pipeline classifies from `Question_Type` labels. |
| `questioncomplexity_id` | Numeric weight: 1 beginner, 2 intermediate, 3 expert. |
| `Question_complexity` | Text fallback for the weight if the numeric complexity field is absent. |
| `question_id` | Identifies the question and prevents repeated choice rows from becoming multiple attempts. |
| `chapter_name` | Retained for question-level detail and later chapter analysis; blank labels become `General`. |
| `user_choice_id` | The student's selected choice ID(s), collected across duplicate choice rows. |
| `Inserted_Date_Time` | Establishes answer ordering and test date; latest answer for a question within a student's test/day is retained. |
| `SCQ_choice_id` | Correct answer ID for a single-choice question. |
| `MCQ_choice1`–`MCQ_choice4` | Correct answer IDs for multiple-choice questions; compared with selected IDs as a set. |

Raw `email`, `password`, `user_answer`, `user_query`, and full question text are deliberately excluded from generated outputs and the dashboard. The preprocessor writes `student_email_lookup.csv` with user IDs, full names for account disambiguation/peer labels, and keyed HMAC-SHA256 digests of normalized addresses—not plain email addresses. The secret is configured by `CAPABILITY_EMAIL_LOOKUP_SECRET`; use the same secret during preparation and API runtime, and replace the development default before any deployment.

## 3. Preparation sequence

1. **Validate the input file.** The script checks required column names before reading a multi-gigabyte file.
2. **Read with DuckDB.** The query selects only analysis fields, tolerates blank cells, and uses temporary disk space to avoid loading the entire CSV into Python memory.
3. **Normalize records.** Invalid student/question IDs, missing timestamps, unsupported question types, and complexity outside 1–3 are skipped. Blank topics become `Uncategorized`, blank chapters become `General`.
4. **Collapse choice-row duplication.** Rows are grouped by student, test, topic, question, date, and exact answer timestamp. Distinct selected and correct choice IDs are collected.
5. **Keep the latest answer.** For a student/test/topic/question on a calendar day, only the latest timestamp is kept. This avoids counting each choice-row or revision as a separate question.
6. **Score each question.** A single-choice response is correct when its selected choices contain the correct SCQ ID. A multiple-choice response is correct when the non-empty selected ID set exactly equals the non-empty correct ID set.
7. **Write compact outputs.** Assessment summaries retain student IDs and metrics; raw emails, passwords, answers-as-text, and free-text queries are not included.
8. **Build the email index.** Read ID, first name, last name, and email from the selected users table, normalize email case/whitespace, and write the user ID, display name, and keyed email digest. The raw email is not written to the index or returned by an API.
9. **Summarize latest-test chapters.** For each student and topic, select the latest available calendar test date and aggregate weighted scores by chapter for the chapter-level advice.

The exact response encoding in the historical export must be checked before interpreting results. In particular, if `user_choice_id` encodes multiple selections in a format other than repeated scalar choice IDs, the parsing/grouping rule must be adapted and tested against known examples.

## 4. Generated data and columns

### `backend/data/processed/question_attempts.csv`

One row per retained question response:

| Output column | Meaning |
| --- | --- |
| `user_id` | Student identifier. |
| `test_id` | Test form identifier. |
| `test_date` | Calendar date derived from `Inserted_Date_Time`. |
| `topic` | Normalized topic. |
| `chapter_name` | Chapter label, or `General`. |
| `question_id` | Item identifier. |
| `question_type` | `scq` or `mcq`. |
| `complexity_id` | Complexity weight from 1 to 3. |
| `is_correct` | 1 for an exact correct response; otherwise 0. |

This file is useful for audit and future item-difficulty/IRT work. It is sensitive because it includes student-level responses.

### `backend/data/processed/student_email_lookup.csv`

| Output column | Meaning |
| --- | --- |
| `user_id` | Student account ID used to connect a lookup to analysis results. |
| `full_name` | First and last name from the users table; shown when selecting accounts for shared email addresses and for similar peers. |
| `email_hmac` | HMAC-SHA256 of the normalized email, using the configured lookup secret. It is used only for matching an entered email and is not reversible without guessing addresses and knowing the key. |

This index is generated from `tables_chosen/tbl_users_1.csv`, is ignored by Git, and is not exposed as a general list endpoint. Some source email addresses are associated with more than one student ID; the API returns candidate names/IDs and the UI asks the operator to select the right account rather than selecting arbitrarily.

### `backend/data/processed/student_topic_summary.csv`

One row per student, topic, and test date:

| Output column | Meaning |
| --- | --- |
| `user_id` | Student identifier. |
| `topic` | Topic label. |
| `test_date` | Test date. |
| `tests_attempted` | Distinct test IDs on that topic/date. |
| `total_questions` | Retained question responses. |
| `total_correct` | Correct retained responses. |
| `weighted_score` | Sum of complexity weights for correct responses. |
| `max_score` | Sum of complexity weights for all retained questions. |
| `score_pct` | `100 × weighted_score / max_score`. |

The FastAPI process reads this compact file, not the original 1.2 GB export. It aggregates date rows at request time to show all-time per-topic summaries.

### `backend/data/processed/student_latest_chapter_summary.csv`

One row per student, topic, and chapter in the latest available test date for that topic. It contains `user_id`, `topic`, `test_date`, `chapter_name`, `tests_attempted`, `total_questions`, `total_correct`, `weighted_score`, `max_score`, and `score_pct`. It supports chapter recommendations without loading the raw attempt export for each API request.

## 5. Scoring and capability placement

For response $i$, let $c_i$ be its complexity weight (1, 2, or 3), and let $r_i$ be 1 when correct and 0 otherwise:

$$
\text{Weighted score} = \sum_i r_i c_i, \qquad
\text{Maximum score} = \sum_i c_i, \qquad
\text{Score percentage} = 100 \times \frac{\sum_i r_i c_i}{\sum_i c_i}.
$$

This normalizes for the maximum available points, so the percentage is not a raw question count. It assumes the assigned complexity categories are meaningful and that weights 1:2:3 are appropriate. The app labels evidence as **early** (<10 questions), **developing** (10–29), or **established** (30+). Those thresholds describe sample size only; they are not statistical confidence intervals.

Topic placement is computed by sorting students' topic percentages and calculating the share of the cohort at or below the student's score. Similar peers are the closest topic percentages. The implementation uses this descriptive cohort method rather than fitting KMeans on every request: it is simpler to interpret and avoids cluster labels/boundaries shifting on each button click. It is not a causal or psychometric classification.

In the similar-student list, `VS YOU` is the peer's topic score minus the selected student's score, in **percentage points** (not percent change). For example, `+5.00 pp` means the peer scored five percentage points higher; `-5.00 pp` means five points lower; `0.00 pp` means the displayed percentages are equal.

## 6. Recommendations

- **Next topics (user-based collaborative filtering):** compare two students' topic-score profiles only over topics both have attempted. Similarity combines score-vector cosine similarity with score-distance and discounts sparse overlap. Up to 50 nearest positive-similarity students contribute votes for topics the selected student has not attempted. Topics are ranked by accumulated similarity support, then the similarity-weighted peer average score.
- **At least five when possible:** if similar students produce fewer than five candidates, unattempted topics are filled from general popularity (how many other students have results), explicitly labeled as fallback. The list can be shorter only when fewer than five topics remain available.
- **Chapter focus:** for the selected topic, show chapters below 60% on the latest available test date. If none are below threshold, the UI says so.
- These recommendations use historical associations, not causal evidence or validated future-score predictions. This is a simple neighborhood recommender; it is not a trained latent-factor model and has not yet been evaluated on held-out data.

### Why no IRT model is claimed in this release

IRT can estimate student ability and item difficulty jointly, but it should only be used after verifying response encoding, enough observations per item, model identifiability, coverage across cohorts, and held-out predictive performance. The source export and generated attempt file create a path toward that analysis; this version does not claim that IRT or the old SVD recommender has been trained or validated. A future IRT experiment should be compared against the complexity-weighted baseline and report uncertainty, especially for new students.

## 7. API and frontend flow

1. Run the one-time preparation script.
2. FastAPI loads the compact summary on its first analytics request and exposes health, overview, student profile, placement, and recommendations.
3. The user enters an email address. Next.js sends it to the API's lookup route; FastAPI HMACs the normalized value, resolves a unique user ID, and returns the same score-only profile.
4. The dashboard displays student IDs, scores, cohort position, topic breakdown, and recommendations. It does not retrieve or display a student's raw email, name, query text, or question content.

API routes:

- `GET /api/health`
- `GET /api/overview`
- `GET /api/students?q=<partial-id>`
- `GET /api/students/lookup?email=<email>`
- `GET /api/students/{user_id}`
- `GET /api/students/{user_id}/placement?topic=<topic>`
- `GET /api/students/{user_id}/recommendations?limit=5&topic=<topic>` returns collaborative topic recommendations and, when `topic` is provided, weak chapters from the latest available test date for that topic.

## 8. Data governance and validation checklist

Before using this for real student decisions:

- Confirm correct-answer key columns and selected-choice encoding using manually verified SCQ and MCQ examples.
- Confirm which timestamp represents a completed response and whether date is an acceptable test-session boundary.
- Check duplication, missingness, complexity labels, and question-version changes.
- Ensure small or sparse cohorts are not used to make high-stakes comparisons.
- Add authentication, role-based authorization, audit logging, retention rules, and HTTPS before deployment.
- The email lookup endpoint is not authentication: protect all student-level endpoints with authorization before deployment. An email address alone must not grant access to educational records.
- Validate against a time-based held-out cohort. Compare weighted scoring and any future IRT/recommendation model using suitable accuracy/calibration and ranking metrics.
- Obtain appropriate institutional/privacy approval; student IDs and answer histories are personal data.
