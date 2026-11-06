import mlflow
from mlflow.tracking import MlflowClient
mlflow.set_tracking_uri('http://localhost:5000')
print(MlflowClient().get_model_version_by_alias('house-price','prod').version)
