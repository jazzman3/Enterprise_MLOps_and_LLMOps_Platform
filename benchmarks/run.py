"""Benchmark local inference throughput and held-out accuracy (not a cloud load test)."""
import json,statistics,time,sys,platform
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.train import train,HOLDOUT
from app.core import infer
artifact,acc=train()
N=5000
samples=[HOLDOUT[i%len(HOLDOUT)][0] for i in range(N)]
lat=[];start=time.perf_counter()
for sample in samples:
    t=time.perf_counter();infer(artifact,sample);lat.append((time.perf_counter()-t)*1000)
secs=time.perf_counter()-start
lat.sort()
result={'benchmark':'local in-process classifier inference','runtime':'Python','python':platform.python_version(),'cases':len(HOLDOUT),'holdout_accuracy':acc,'requests':N,'throughput_rps':round(N/secs,1),'p50_ms':round(lat[int(N*0.5)],5),'p95_ms':round(lat[int(N*0.95)],5),'p99_ms':round(lat[int(N*0.99)],5),'scope':'in-process inference only; excludes HTTP/network/database/cloud latency; tiny synthetic holdout data','model_kind':artifact['kind']}
Path(__file__).with_name('results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
