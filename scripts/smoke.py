import os,sys,json,urllib.request
base=os.getenv('BASE_URL','http://localhost:8000').rstrip('/')
key=os.getenv('INFERENCE_API_KEY','local-inference-key-change-me')
def request(path,payload=None):
    data=None if payload is None else json.dumps(payload).encode()
    req=urllib.request.Request(base+path,data=data,headers={'X-API-Key':key,'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=10) as r:return json.load(r)
assert request('/healthz')['status']=='ok'
assert request('/readyz')['status']=='ready'
r=request('/v1/predict',{'model':'sentiment','text':'excellent reliable and accurate'})
assert r['label'] in ('positive','negative') and r['version']>0
print(json.dumps({'status':'passed','inference':r},indent=2))
