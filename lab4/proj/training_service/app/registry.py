"""Operator CLI: inspect and reassign @prod; model is loaded after forecast restart."""
import argparse
import os
import mlflow
from mlflow.tracking import MlflowClient

def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=['list','promote','alias'])
    p.add_argument('version',nargs='?')
    a=p.parse_args()
    mlflow.set_tracking_uri(os.getenv('MLFLOW_TRACKING_URI','http://mlflow:5000'))
    client=MlflowClient()
    name=os.getenv('MODEL_NAME','house-price')
    if a.action=='list':
        for m in client.search_model_versions(f"name='{name}'"):
            print(f'version={m.version} run={m.run_id} status={m.status}')
        for alias in ['prod','baseline']:
            try: print(f'alias @{alias}: v{client.get_model_version_by_alias(name,alias).version}')
            except Exception as exc: print(f'alias @{alias}: missing ({type(exc).__name__})')
    elif a.action=='alias':
        if not a.version: p.error('alias requires prod or baseline')
        print(client.get_model_version_by_alias(name,a.version).version)
    else:
        if not a.version: p.error('promote requires a version number')
        client.set_registered_model_alias(name,'prod',str(int(a.version)))
        print(f'alias {name}@prod now resolves to version {a.version}; restart forecast-api')
if __name__=='__main__': main()
