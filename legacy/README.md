# Legacy Streamlit prototype

`streamlit_app.py` is the original single-file prototype. The current application is the FastAPI backend and React frontend in `backend/` and `frontend/`.

The legacy app looks for its model at the relative paths `model/scam_model.pkl` and `model/vectorizer.pkl`. The model artifacts currently used by the main application are in `backend/ml/artifacts/`, so the legacy app may run without its model unless those files are copied into the expected `model/` directory.

This folder is retained for reference and is not used by the current application.
