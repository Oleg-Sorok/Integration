"""Practice 4: reproducible Ridge vs XGBoost (Optuna) and registry promotion.

One trainer invocation logs Ridge baseline, 20 nested Optuna trial runs, final
XGBoost run, dataset digest, artifacts, two registered versions and prod alias.
"""
import hashlib
import json
import os
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import mlflow
import mlflow.data
import mlflow.sklearn
import numpy as np
import optuna
import pandas as pd
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import TransformedTargetRegressor
from xgboost import XGBRegressor

SEED=42
NUMERIC=['GrLivArea','TotalBsmtSF','GarageArea','YearBuilt','OverallQual']
CATEGORICAL=['MSZoning']
FEATURES=NUMERIC+CATEGORICAL
TARGET='SalePrice'
DATA_PATH=Path(os.getenv('DATA_PATH','/app/data/ames_train.csv'))
MODEL_NAME=os.getenv('MODEL_NAME','house-price')
EXPERIMENT=os.getenv('MLFLOW_EXPERIMENT_NAME','house-price')
N_TRIALS=int(os.getenv('N_TRIALS','20'))
if N_TRIALS<20:
    raise ValueError('The methodical requirements demand N_TRIALS >= 20')


def pipeline_ridge():
    return Pipeline([
        ('prep', ColumnTransformer([
            ('num',Pipeline([('impute',SimpleImputer(strategy='median')),
                             ('scale',StandardScaler())]),NUMERIC),
            ('cat',OneHotEncoder(handle_unknown='ignore'),CATEGORICAL)])),
        ('model',Ridge(alpha=1.0))])


def build_model(params):
    prep=ColumnTransformer([
        ('num',SimpleImputer(strategy='median'),NUMERIC),
        ('cat',OneHotEncoder(handle_unknown='ignore'),CATEGORICAL)])
    return Pipeline([
        ('prep',prep),
        ('model',TransformedTargetRegressor(
            regressor=XGBRegressor(**params,random_state=SEED,n_jobs=1,objective='reg:squarederror',tree_method='hist'),
            func=np.log1p,inverse_func=np.expm1))])


def metrics(model,X,y):
    p=model.predict(X)
    return {'holdout_r2':float(r2_score(y,p)),
            'holdout_mae':float(mean_absolute_error(y,p)),
            'holdout_rmse':float(np.sqrt(mean_squared_error(y,p))),
            'holdout_mape':float(100*mean_absolute_percentage_error(y,p))}


def stats_for(df):
    y=df[TARGET].astype(float)
    return {'rows':int(len(df)), 'features':FEATURES, 'target':TARGET,
            'sha256':hashlib.sha256(DATA_PATH.read_bytes()).hexdigest(),
            'missing_fraction':{k:float(df[k].isna().mean()) for k in FEATURES+[TARGET]},
            'target_skew_before':float(y.skew()),
            'target_skew_after_log1p':float(np.log1p(y).skew()),
            'target_quantiles':{str(q):float(y.quantile(q)) for q in [0,0.25,0.5,0.75,1]},
            'numeric_feature_stats':{
                k:{'mean':float(df[k].mean()),'median':float(df[k].median()),
                   'std':float(df[k].std())} for k in NUMERIC},
            'categorical_counts':{k:{str(a):int(b) for a,b in df[k].value_counts(dropna=False).items()}
                                  for k in CATEGORICAL}}


def log_context(df, X_train, y_train, stats):
    dataset=mlflow.data.from_pandas(df,source=str(DATA_PATH),targets=TARGET,name='ames-housing-training')
    mlflow.log_input(dataset,context='train')
    mlflow.set_tag('data_sha256',stats['sha256'])
    mlflow.log_dict(stats,'data_stats.json')
    mlflow.log_metrics({'row_count':float(stats['rows']),
                        'target_skew_before':stats['target_skew_before'],
                        'target_skew_after':stats['target_skew_after_log1p']})
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    axes[0].hist(df[TARGET],bins=30)
    axes[0].set(xlabel='SalePrice (USD)',ylabel='Count',title='Before transformation')
    axes[1].hist(np.log1p(df[TARGET]),bins=30)
    axes[1].set(xlabel='log1p(SalePrice)',ylabel='Count',title='After transformation')
    fig.tight_layout()
    mlflow.log_figure(fig,'target_distributions.png')
    plt.close(fig)
    ref_path=Path('/tmp/reference_data.parquet')
    X_train.to_parquet(ref_path,index=False)
    mlflow.log_artifact(str(ref_path))


def register(model,X_train,run_name,description):
    sig=infer_signature(X_train.head(5),model.predict(X_train.head(5)))
    info=mlflow.sklearn.log_model(model,name='model',signature=sig,input_example=X_train.head(2))
    mv=mlflow.register_model(info.model_uri,MODEL_NAME,await_registration_for=120)
    mlflow.set_tag('registered_version',str(mv.version))
    mlflow.set_tag('registered_role',description)
    MlflowClient().set_model_version_tag(MODEL_NAME, mv.version, 'stats_run_id', mlflow.active_run().info.run_id)
    print(f'[trainer] {run_name}: registered version={mv.version} run={mlflow.active_run().info.run_id}',flush=True)
    return mv


def main():
    mlflow.set_tracking_uri(os.getenv('MLFLOW_TRACKING_URI','http://mlflow:5000'))
    mlflow.set_experiment(EXPERIMENT)
    df=pd.read_csv(DATA_PATH)[FEATURES+[TARGET]].dropna(subset=[TARGET])
    X,y=df[FEATURES],df[TARGET].astype(float)
    Xtr,Xte,ytr,yte=train_test_split(X,y,test_size=.2,random_state=SEED)
    stats=stats_for(df)
    print('[trainer] data rows=',len(df),' sha256=',stats['sha256'],flush=True)
    with mlflow.start_run(run_name='ridge-baseline'):
        baseline=pipeline_ridge().fit(Xtr,ytr)
        mlflow.log_params({'model_type':'Ridge','ridge_alpha':1.,'random_state':SEED,'test_size':.2})
        b_metrics=metrics(baseline,Xte,yte)
        mlflow.log_metrics(b_metrics)
        log_context(df,Xtr,ytr,stats)
        baseline_mv=register(baseline,Xtr,'ridge-baseline','baseline')
    client=MlflowClient()
    client.set_registered_model_alias(MODEL_NAME,'baseline',baseline_mv.version)

    cv=KFold(n_splits=5,shuffle=True,random_state=SEED)
    study=optuna.create_study(direction='maximize',sampler=optuna.samplers.TPESampler(seed=SEED))
    with mlflow.start_run(run_name='xgboost-search') as parent:
        mlflow.log_params({'algorithm':'XGBoost+Optuna','n_trials':N_TRIALS,'cv_folds':5,'seed':SEED})
        def objective(trial):
            params={
                'n_estimators':trial.suggest_int('n_estimators',200,1000),
                'max_depth':trial.suggest_int('max_depth',2,8),
                'learning_rate':trial.suggest_float('learning_rate',.01,.3,log=True),
                'subsample':trial.suggest_float('subsample',.6,1.0),
                'colsample_bytree':trial.suggest_float('colsample_bytree',.6,1.0),
                'reg_lambda':trial.suggest_float('reg_lambda',0.,10.)}
            with mlflow.start_run(run_name=f'optuna-trial-{trial.number:02d}',nested=True):
                mlflow.log_params(params)
                values=cross_val_score(build_model(params),Xtr,ytr,cv=cv,scoring='r2',n_jobs=1)
                mean=float(values.mean())
                mlflow.log_metrics({'cv_r2':mean,'cv_r2_std':float(values.std())})
                mlflow.set_tag('trial_number',str(trial.number))
            return mean
        study.optimize(objective,n_trials=N_TRIALS)
        mlflow.log_metric('best_cv_r2',float(study.best_value))
        mlflow.log_params({'best_'+k:v for k,v in study.best_params.items()})
        mlflow.set_tag('best_trial',str(study.best_trial.number))
    with mlflow.start_run(run_name='xgboost-final') as run:
        final_model=build_model(study.best_params).fit(Xtr,ytr)
        f_metrics=metrics(final_model,Xte,yte)
        mlflow.log_params({'model_type':'XGBoost','random_state':SEED,'test_size':.2,**study.best_params})
        mlflow.log_metrics({**f_metrics,'cv_r2':float(study.best_value)})
        log_context(df,Xtr,ytr,stats)
        final_mv=register(final_model,Xtr,'xgboost-final','final')
    client.set_registered_model_alias(MODEL_NAME,'prod',final_mv.version)
    print('[trainer] BASELINE',json.dumps(b_metrics,sort_keys=True))
    print('[trainer] XGBOOST ',json.dumps(f_metrics,sort_keys=True))
    print(f'[trainer] registered versions: baseline={baseline_mv.version}; prod={final_mv.version}',flush=True)
    print('[trainer] completed; restart forecast-api to load @prod',flush=True)

if __name__=='__main__':
    main()
