# Legacy Streamlit app

The original single-file Streamlit prototype, kept unchanged for reference (`streamlit_app.py`, `test_legacy_patterns.py`).
It is superseded by `backend/` + `frontend/`. Known defects it contains are listed in the root README ("Audit findings").
Note: it looked for model files in `model/`, but the repository shipped them in the root, so it ran in pattern-only mode.
