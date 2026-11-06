"""Offline structural checks (not a substitute for Docker E2E tests)."""
import ast
from pathlib import Path
import re
root=Path(__file__).resolve().parents[1]
a=root/'orders-service'/'app'
for path in a.glob('*.py'):
    ast.parse(path.read_text(encoding='utf-8'),filename=str(path))
main=(a/'main.py').read_text()
assert main.index("@app.post('/orders/batch')") < main.index("@app.get('/orders/{oid}',")
for text in ("asyncio.gather", 'httpx.AsyncClient', 'BackgroundTasks', "response.headers['Location']", "status_code=202"):
    assert text in main, text
assert 'prediction_revision' in (a/'models.py').read_text()
assert 'prediction_revision' in (a/'tasks.py').read_text()
assert 'IF NOT EXISTS status' in (a/'migrations.py').read_text()
compose=(root/'docker-compose.yaml').read_text()
forecast=compose.split('  forecast-api:',1)[1].split('  orders-api:',1)[0]
assert '\n    ports:' not in forecast
assert 'jwt_secret_key' in compose and 'db_password' in compose
print('STRUCTURE CHECKS PASSED (not a Docker test)')
