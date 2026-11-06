"""Shared constants + model loading."""
import os
from pathlib import Path

import joblib
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent  # forecast-service/ (or /app in Docker)
DATA_PATH = Path(os.getenv("DATA_PATH", BASE_DIR / "data" / "ames_train.csv"))
ARTIFACT_PATH = Path(os.getenv("MODEL_PATH", BASE_DIR / "artifacts" / "model.pkl"))
METRICS_PATH = ARTIFACT_PATH.with_name("metrics.json")

NUMERIC = ["GrLivArea", "TotalBsmtSF", "GarageArea", "YearBuilt", "OverallQual"]
CATEGORICAL = ["MSZoning"]
FEATURES = NUMERIC + CATEGORICAL
TARGET = "SalePrice"

# API (snake_case) -> dataset column (Ames)
API_TO_COLUMN = {
    "gr_liv_area": "GrLivArea",
    "total_bsmt_sf": "TotalBsmtSF",
    "garage_area": "GarageArea",
    "year_built": "YearBuilt",
    "overall_qual": "OverallQual",
    "ms_zoning": "MSZoning",
}


class Predictor:
    def __init__(self, path: Path = ARTIFACT_PATH):
        self.pipeline = joblib.load(path)

    def predict(self, payload: dict) -> float:
        row = {col: payload[api] for api, col in API_TO_COLUMN.items()}
        frame = pd.DataFrame([row], columns=FEATURES)
        return float(self.pipeline.predict(frame)[0])
