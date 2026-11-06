"""In-container health and data-stats checks (no host published ports needed)."""
import json
from urllib.request import urlopen
for path in ('/health','/model/data-stats'):
    with urlopen('http://localhost:8001'+path,timeout=10) as r:
        data=json.load(r)
    print(path, '=>', json.dumps(data,ensure_ascii=False)[:1100])
