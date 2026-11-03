# Capability Analysis — Modernization Recommendations

## Purpose

Modernize the existing student capability-analysis application while preserving the original project and its files. The intended product should estimate capability based on the complexity and difficulty of questions answered, place new students on a comparable capability scale, identify similar students, and provide useful learning recommendations.

## What the existing application does

The legacy Tkinter application calculates a weighted score (beginner = 1, intermediate = 2, expert = 3), normalizes it by the weighted maximum, and displays results by topic. It also provides topic recommendations, uses KMeans to group students by percentage, and compares nearby students. See the legacy implementation in [capability_all_final_code.py](../capability%20analysis%20final%20code/capability_all_final_code.py).

The weighted score is a useful transparent baseline: it does not directly reward answering more questions, because the total is normalized by the weighted maximum. However, the score assumes the three complexity levels are equally spaced and that assigned complexity accurately reflects question difficulty.

## Recommendations

### 1. Establish a reliable baseline and validate the data

- Preserve the current weighted score as a baseline for comparison.
- Confirm the meaning and quality of question complexity, correct-answer keys, attempt timestamps, and question identifiers.
- Check that repeated attempts are handled consistently and that a test session is not inadvertently defined only by calendar date.
- Compare scores across students who received different questions or different numbers of questions.
- Document missing data, duplicate records, and any assumptions used in scoring.

### 2. Improve the capability estimate

- Treat complexity-weighted scoring as an initial estimate, not a fully calibrated measure of ability.
- Explore Item Response Theory (IRT), such as a Rasch or 2-parameter logistic model, to estimate both student ability and item difficulty from response history. Consider a more complex model only if the response volume supports it.
- Retain the weighted score as a fallback until there is enough response data to estimate stable item parameters.
- Report uncertainty or confidence alongside a student's estimate, particularly for a new student with only a few answers.
- If IRT is not yet viable, define and validate transparent score bands using historical cohorts and anchor questions.

### 3. Place new students on a stable peer scale

- Compare students using calibrated ability estimates where available, rather than relying only on a fresh KMeans fit to one percentage feature.
- Provide an interpretable cohort band or percentile and a short list of similar students, subject to appropriate privacy controls.
- If clustering is retained, fit it on historical data, document the features and cluster meanings, and persist/version the model and preprocessing. Avoid allowing cluster labels to change unpredictably on each analysis.
- Re-estimate placement as the student answers more questions, and make clear that early placement is provisional.

### 4. Make recommendations transparent and measurable

- Start with explainable recommendations: topics or chapters where the student has demonstrated gaps, relevant prerequisites, and the next appropriate level of difficulty.
- Treat collaborative-filtering or matrix-factorization recommendations as an additional signal, not as the sole basis for advice.
- Evaluate recommendations on held-out historical data, preferably with a time-aware split that reflects the order in which students took tests.
- Compare machine-learning recommendations with simple baselines and track ranking quality and usefulness. Do not present predictions as validated until they have been tested.
- Avoid recommending topics with too little supporting data, or label such recommendations as low confidence.

### 5. Improve application performance and maintainability

- Separate data preparation, scoring, model training, recommendation logic, and user interface code.
- Precompute reusable student/topic summaries and train/load models outside GUI button handlers.
- Cache or persist fitted models and preprocessing artifacts with a version and training-data timestamp.
- Replace machine-specific absolute paths with configuration and paths relative to the application or a selected data directory.
- Add input validation, clear error messages for missing or incompatible data, and automated tests for scoring and recommendation logic.
- Keep the legacy project unchanged; implement and test the modernization in this new folder.

## Suggested delivery phases

1. **Audit:** Document data schemas, scoring assumptions, and current outputs; establish test cases from known examples.
2. **Baseline:** Implement a clean, testable weighted-scoring module and compare its output with the legacy application.
3. **Capability calibration:** Assess whether the response data supports IRT; prototype and validate it against the baseline.
4. **Peer placement and recommendations:** Add stable cohort comparisons and transparent recommendations, then evaluate optional ML approaches offline.
5. **Application modernization:** Build the new interface and data/model pipeline around the validated analysis modules; package configuration and tests.

## Key principle

Use machine learning where it improves measurement or recommendations and can be evaluated. A newer algorithm alone does not make the result more accurate or fair; the scoring scale, response data, validation, and explanation to students are equally important.
