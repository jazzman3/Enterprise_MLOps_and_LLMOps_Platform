"""Repeatable HTTP benchmark: live API+database. Assumes seeded local server running."""
import json,os,statistics,time,urllib.request,concurrent.futures,platform
from pathlib import Path
URL=os.getenv('BASE_URL','http://127.0.0.1:8000').rstrip('/')+'/v1/predict'
KEY=os.getenv('INFERENCE_API_KEY','local-inference-key-change-me')
N=int(os.getenv('BENCH_REQUESTS','200'))
WORKERS=int(os.getenv('BENCH_WORKERS','5'))
def one(index):
    data=json.dumps({'model':'sentiment','text':('excellent reliable service' if index%2 else 'terrible slow failure')}).encode()
    req=urllib.request.Request(URL,data=data,headers={'X-API-Key':KEY,'Content-Type':'application/json'},method='POST')
    t=time.perf_counter()
    with urllib.request.urlopen(req,timeout=30) as r:
        result=json.load(r)
    return (time.perf_counter()-t)*1000, result['label']
for i in range(5):one(i)
t=time.perf_counter()
with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as executor:
    vals=list(executor.map(one,range(N)))
duration=time.perf_counter()-t
lat=sorted(v[0] for v in vals)
result={'benchmark':'HTTP API + SQLAlchemy database lookup','requests':N,'concurrency':WORKERS,'throughput_rps':round(N/duration,2),'p50_ms':round(lat[int(.5*(N-1))],3),'p95_ms':round(lat[int(.95*(N-1))],3),'p99_ms':round(lat[int(.99*(N-1))],3),'errors':0,'python':platform.python_version(),'scope':'local host HTTP; synthetic input; includes DB request and HTTP; NOT public cloud, LLM call, or representative enterprise scale'}
Path(__file__).with_name('http_results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
