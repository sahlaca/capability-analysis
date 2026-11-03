# Backend

See the project [README](../README.md) for setup and [dataset guide](../DATASET_AND_METHODOLOGY.md) for input requirements and processing details.

From this directory, install `requirements.txt`, run `python scripts/prepare_dataset.py`, then start `uvicorn app.main:app --reload`. Analytics requests use the generated `data/processed/student_topic_summary.csv` only.
