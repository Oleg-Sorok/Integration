import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.model import Predictor
from app.schemas import PredictRequest, PredictResponse

MODEL_VERSION = os.getenv("MODEL_VERSION", "v0.1.0")
state: dict = {"predictor": None}


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        state["predictor"] = Predictor()
    except Exception as exc:  # model missing/corrupt -> service starts but is "unhealthy"
        print(f"[forecast] cannot load model: {exc}")
    yield


app = FastAPI(title="Forecast API", lifespan=lifespan)


@app.get("/health")
def health():
    if state["predictor"] is None:
        raise HTTPException(503, "model is not loaded")
    return {"status": "ok", "model_version": MODEL_VERSION}


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    predictor = state["predictor"]
    if predictor is None:
        raise HTTPException(503, "model is not loaded")
    t0 = time.perf_counter()
    price = predictor.predict(req.model_dump())
    return PredictResponse(
        predicted_price=round(price, 2),
        model_version=MODEL_VERSION,
        latency_ms=round((time.perf_counter() - t0) * 1000, 2),
    )
