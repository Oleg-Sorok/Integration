"""Start MLflow without storing DB credentials in compose or shell command text."""
import subprocess
from pathlib import Path
from sqlalchemy.engine import URL

password = Path('/run/secrets/db_password').read_text().strip()
if not password:
    raise RuntimeError('db_password secret is empty')
uri = URL.create('postgresql+psycopg2', username='orders', password=password,
                 host='postgres', port=5432, database='mlflow').render_as_string(hide_password=False)
# CLI argument still briefly contains the password in process metadata; secrets remain
# absent from Compose/env/images. In production use an external secret manager/DB auth.
subprocess.run(['mlflow', 'server', '--host', '0.0.0.0', '--port', '5000',
                '--backend-store-uri', uri, '--serve-artifacts',
                '--artifacts-destination', '/mlartifacts'], check=True)
