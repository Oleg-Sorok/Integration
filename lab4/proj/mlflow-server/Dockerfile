FROM ghcr.io/mlflow/mlflow:v3.1.0
# psycopg2 avoids PostgreSQL integer-versus-VARCHAR comparisons triggered by
# the psycopg 3 dialect in this pinned MLflow version.
RUN pip install --no-cache-dir "psycopg2-binary==2.9.10"
COPY mlflow-server/serve.py /opt/serve.py
COPY mlflow-server/alias_check.py /opt/alias_check.py
ENTRYPOINT ["python", "/opt/serve.py"]
