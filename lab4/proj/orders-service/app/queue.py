"""Redis/RQ durable queue; only order identifiers are enqueued, not credentials."""
import os
from redis import Redis
from rq import Queue

_redis = Redis.from_url(os.getenv('REDIS_URL','redis://redis:6379/0'))
pricing_queue = Queue('pricing', connection=_redis, default_timeout=120)

def enqueue_prediction(order_id:int, revision:int):
    return pricing_queue.enqueue('app.tasks.run_prediction', order_id, revision,
                                 job_timeout=120, result_ttl=3600)
