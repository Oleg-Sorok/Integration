"""Offline structural tests. Requires PyYAML; does not claim Docker or MLflow ran."""
from pathlib import Path
import ast
import sys
import yaml
R=Path(__file__).resolve().parent.parent
compose=yaml.safe_load((R/'docker-compose.yaml').read_text())
s=compose['services']
for key in ('postgres','mlflow-db-init','mlflow','redis','orders-api','orders-worker','forecast-api','trainer'):
    assert key in s,key
assert s['trainer']['profiles']==['train']
assert not s['redis'].get('ports') and not s['forecast-api'].get('ports')
assert 'mlartifacts:/mlartifacts' in s['mlflow']['volumes']
for name,service in s.items():
    if name!='mlflow': assert not any('mlartifacts:' in v for v in service.get('volumes',[]) if isinstance(v,str))
assert 'python -m app.train' not in (R/'forecast-service/Dockerfile').read_text()
assert 'ames_train.csv' not in (R/'forecast-service/Dockerfile').read_text()
assert not (R/'forecast-service/app/train.py').exists()
assert 'model_version' in (R/'orders-service/app/models.py').read_text()
assert 'get_model_version_by_alias' in (R/'forecast-service/app/main.py').read_text()
assert 'N_TRIALS<20' in (R/'training_service/app/train.py').read_text()
for d in ('orders-service','forecast-service','training_service'):
    for p in (R/d/'app').rglob('*.py'):
        ast.parse(p.read_text(), filename=str(p))
print('PASS: Compose architecture, model/dataset isolation, model-version traceability, scripts syntax')
