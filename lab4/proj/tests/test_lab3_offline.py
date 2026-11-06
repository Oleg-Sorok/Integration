"""Offline integration tests for Lab 3 using a SQLite test DB and mocked Forecast HTTP.

Run from proj: python -m unittest discover -s tests -v
Does not require Docker, secrets, internet, or the Ames CSV.
"""
import asyncio
import json
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'orders-service'))

fake_db = types.ModuleType('app.database')
class Base(DeclarativeBase):
    pass
fake_db.Base = Base
engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
fake_db.engine = engine
fake_db.SessionLocal = sessionmaker(engine, expire_on_commit=False)
def get_db():
    with fake_db.SessionLocal() as sess:
        yield sess
fake_db.get_db = get_db
sys.modules['app.database'] = fake_db

fake_mig = types.ModuleType('app.migrations')
fake_mig.migrate_orders = lambda: None
sys.modules['app.migrations'] = fake_mig
fake_sec = types.ModuleType('app.security')
def get_current_user(authorization: str | None = Header(default=None)):
    if authorization != 'Bearer test':
        raise HTTPException(status_code=401, detail='Auth required', headers={'WWW-Authenticate': 'Bearer'})
    return SimpleNamespace(id=1, username='test')
fake_sec.get_current_user = get_current_user
fake_sec.hash_password = lambda _: 'test-hash'
fake_sec.make_token = lambda _: 'test'
fake_sec.verify_password = lambda p, h: p == 'test-pass' and h == 'test-hash'
sys.modules['app.security'] = fake_sec
fake_fc = types.ModuleType('app.forecast_client')
fake_fc.FORECAST_URL = 'http://forecast-api:8001'
fake_fc.FORECAST_TIMEOUT = 2.0
sys.modules['app.forecast_client'] = fake_fc

from app import crud, models, tasks, main  # noqa: E402


class StubResponse:
    def raise_for_status(self):
        return None
    def json(self):
        return {'predicted_price': 177777.0}


class StubForecastClient:
    def __init__(self, *args, fail=False, **kwargs):
        self.fail = fail
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return None
    def post(self, url, json):
        if self.fail:
            raise httpx.ConnectError('simulated outage')
        return StubResponse()


ORDER = {
    'client_name':'Offline Test House', 'gr_liv_area':1800.0,
    'total_bsmt_sf':1000.0, 'garage_area':500.0, 'year_built':2005,
    'overall_qual':7, 'ms_zoning':'RL'
}
HEADERS = {'Authorization': 'Bearer test'}


class Lab3Tests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)

    def test_background_success_and_idempotence(self):
        with fake_db.SessionLocal() as db:
            order = crud.create_pending(db, main.OrderCreate(**ORDER))
            oid = order.id
        with patch.object(tasks.httpx, 'Client', lambda **_: StubForecastClient()):
            tasks.run_prediction(oid, 0)
            tasks.run_prediction(oid, 0)
        with fake_db.SessionLocal() as db:
            rows = db.scalars(select(models.Order)).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].status, 'priced')
            self.assertEqual(rows[0].predicted_price, 177777.0)

    def test_background_failure_deleted_and_stale_revision(self):
        with fake_db.SessionLocal() as db:
            order = crud.create_pending(db, main.OrderCreate(**ORDER))
            oid = order.id
        with patch.object(tasks.httpx, 'Client', lambda **_: StubForecastClient(fail=True)):
            tasks.run_prediction(oid, 0)
        with fake_db.SessionLocal() as db:
            order = db.get(models.Order, oid)
            self.assertEqual(order.status, 'failed')
            self.assertIsNone(order.predicted_price)
            order, enq = crud.prepare_retry(db, order)
            self.assertTrue(enq)
            self.assertEqual(order.prediction_revision, 1)
        with patch.object(tasks.httpx, 'Client', lambda **_: StubForecastClient()):
            tasks.run_prediction(oid, 0)  # stale: skipped
            with fake_db.SessionLocal() as db:
                self.assertEqual(db.get(models.Order, oid).status, 'pending')
            tasks.run_prediction(oid, 1)
        with fake_db.SessionLocal() as db:
            order = db.get(models.Order, oid)
            self.assertEqual(order.status, 'priced')
            crud.delete_order(db, order)
        tasks.run_prediction(oid, 1)  # deleted: skipped
        with fake_db.SessionLocal() as db:
            self.assertIsNone(db.get(models.Order, oid))

    def test_http_contract_and_batch_concurrency(self):
        with TestClient(main.app) as api:
            self.assertEqual(api.get('/orders').status_code, 401)
            self.assertEqual(api.get('/health').json(), {'status':'ok'})
            with patch.object(tasks.httpx, 'Client', lambda **_: StubForecastClient()):
                created = api.post('/orders', json=ORDER, headers=HEADERS)
                self.assertEqual(created.status_code, 202)
                doc = created.json()
                self.assertEqual(doc['status'], 'pending')
                self.assertIsNone(doc['predicted_price'])
                self.assertEqual(created.headers.get('location'), f"/orders/{doc['id']}")
                self.assertEqual(api.get(f"/orders/{doc['id']}", headers=HEADERS).json()['status'], 'priced')
                id_ = doc['id']
                name_only = api.patch(f'/orders/{id_}', headers=HEADERS, json={'client_name':'New Name'})
                self.assertEqual(name_only.json()['status'], 'priced')
                reprice = api.patch(f'/orders/{id_}', headers=HEADERS, json={'overall_qual':9})
                self.assertEqual(reprice.status_code, 200)
                self.assertEqual(reprice.json()['status'], 'pending')
                self.assertEqual(api.get(f'/orders/{id_}', headers=HEADERS).json()['status'], 'priced')
                rerun = api.post(f'/orders/{id_}/retry', headers=HEADERS)
                self.assertEqual(rerun.status_code, 200)
                self.assertEqual(rerun.json()['id'], id_)
            max_concurrent = [0]
            active = [0]
            async def predictor(request):
                active[0] += 1
                max_concurrent[0] = max(max_concurrent[0], active[0])
                await asyncio.sleep(0.02)
                active[0] -= 1
                return httpx.Response(200, json={'predicted_price': 123123.0})
            # Lifespan started a shared client. Replace with mock transport.
            actual = main.app.state.forecast_client
            mock_client = httpx.AsyncClient(transport=httpx.MockTransport(predictor))
            main.app.state.forecast_client = mock_client
            try:
                rsp = api.post('/orders/batch', headers=HEADERS, json=[ORDER] * 4)
                self.assertEqual(rsp.status_code, 200, rsp.text)
                self.assertEqual(rsp.json()['total'], 4)
                self.assertTrue(all(x['status'] == 'priced' for x in rsp.json()['results']))
                self.assertGreater(max_concurrent[0], 1, 'Expected overlapping asynchronous requests')
                self.assertEqual(api.post('/orders/batch', headers=HEADERS, json=[ORDER]*51).status_code, 422)
                self.assertEqual(api.post('/orders/batch', json=[ORDER]).status_code, 401)
            finally:
                # Teardown of the outer lifespan closes this client's transport.
                main.app.state.forecast_client = actual
                asyncio.run(mock_client.aclose())


if __name__ == '__main__':
    unittest.main()
