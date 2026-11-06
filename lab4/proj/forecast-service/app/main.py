"""Model is fetched from the MLflow registry on each service start."""
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import mlflow
from mlflow.tracking import MlflowClient
from fastapi import FastAPI
from app.model import to_dataframe
from app.schemas import PredictRequest, PredictResponse

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('forecast')
MODEL_NAME = os.getenv('MODEL_NAME', 'house-price')
MODEL_ALIAS = os.getenv('MODEL_ALIAS', 'prod')
mlflow.set_tracking_uri(os.getenv('MLFLOW_TRACKING_URI', 'http://mlflow:5000'))

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        client = MlflowClient()
        mv = client.get_model_version_by_alias(MODEL_NAME, MODEL_ALIAS)
        model = mlflow.pyfunc.load_model(f'models:/{MODEL_NAME}@{MODEL_ALIAS}')
        stats_run_id = mv.tags.get('stats_run_id') or mv.run_id
        if not stats_run_id:
            raise RuntimeError('Registry model version has no stats_run_id / run_id provenance')
        stats_file = mlflow.artifacts.download_artifacts(run_id=stats_run_id, artifact_path='data_stats.json')
        stats = json.loads(Path(stats_file).read_text(encoding='utf-8'))
    except Exception as exc:
        log.exception('FAIL-FAST: registry alias %s@%s unavailable', MODEL_NAME, MODEL_ALIAS)
        raise RuntimeError(f'Cannot resolve registry alias {MODEL_NAME}@{MODEL_ALIAS}: {exc}') from exc
    app.state.model = model
    app.state.model_version = str(mv.version)
    app.state.data_stats = stats
    log.info('Loaded model %s@%s resolved version=%s', MODEL_NAME, MODEL_ALIAS, mv.version)
    yield

app = FastAPI(title='Forecast API: MLflow registry', lifespan=lifespan)

@app.get('/health')
def health():
    return {'status':'ok', 'model_name':MODEL_NAME, 'model_alias':MODEL_ALIAS,
            'model_version':app.state.model_version}

@app.get('/model/data-stats')
def data_stats():
    return app.state.data_stats

@app.post('/predict', response_model=PredictResponse)
def predict(req: PredictRequest):
    t0=time.perf_counter()
    result=float(app.state.model.predict(to_dataframe(req.model_dump()))[0])
    return PredictResponse(predicted_price=round(result,2), currency='USD',
                           model_version=app.state.model_version,
                           latency_ms=round((time.perf_counter()-t0)*1000,2))
