import hmac, json, os, time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Header, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from . import core, llm

REQUESTS=Counter('mlops_inferences_total','Inference requests', ['model','status'])
LATENCY=Histogram('mlops_inference_seconds','Inference latency seconds',['model'])

def authorize(x_api_key: str|None=Header(default=None)):
    configured=os.getenv('INFERENCE_API_KEY','local-inference-key-change-me')
    if not x_api_key or not hmac.compare_digest(x_api_key,configured): raise HTTPException(401,'Invalid inference API key')

def admin(x_admin_key: str|None=Header(default=None)):
    configured=os.getenv('ADMIN_API_KEY','local-admin-key-change-me')
    if not x_admin_key or not hmac.compare_digest(x_admin_key,configured): raise HTTPException(401,'Invalid admin API key')

@asynccontextmanager
async def lifespan(app):
    if os.getenv('APP_ENV','development') == 'production':
        for variable, default in [('ADMIN_API_KEY','local-admin-key-change-me'),('INFERENCE_API_KEY','local-inference-key-change-me')]:
            value=os.getenv(variable,'')
            if len(value)<24 or value==default: raise RuntimeError(f'Production requires a strong {variable}')
    core.init()
    if os.getenv("ENABLE_METRICS_SERVER","0")=="1":
        from prometheus_client import start_http_server
        start_http_server(9101)
    yield
app=FastAPI(title='Enterprise MLOps & LLMOps Control Plane', version='1.0.0', lifespan=lifespan)

class Artifact(BaseModel):
    kind:str
    bias:float
    weights:dict[str,float]
    labels:list[str]
class Register(BaseModel):
    model:str
    artifact:Artifact
    accuracy:float=Field(ge=0,le=1)
class Promotion(BaseModel):
    model:str
    version:int=Field(gt=0)
    alias:str='champion'
class Predict(BaseModel):
    model:str='sentiment'
    text:str=Field(min_length=1,max_length=10000)
    alias:str='champion'

@app.get('/healthz')
def healthz(): return {'status':'ok'}
@app.get('/readyz')
def readyz():
    try:
        core.init()
        with core.Session() as db: db.execute(__import__('sqlalchemy').text('SELECT 1'))
        return {'status':'ready'}
    except Exception: raise HTTPException(503,'Database unavailable')
@app.get('/metrics')
def metrics(_:None=Depends(admin)):
    return Response(content=generate_latest(),media_type=CONTENT_TYPE_LATEST)
@app.post('/v1/models/register')
def register(req:Register,_:None=Depends(admin)):
    try:
        from scripts.train import HOLDOUT
        payload=req.artifact.model_dump()
        verified=sum(core.infer(payload,text)['label']==label for text,label in HOLDOUT)/len(HOLDOUT)
        return core.register(req.model,payload,verified)
    except ValueError as exc: raise HTTPException(422,str(exc))
@app.post('/v1/deployments/promote')
def promote(req:Promotion,_:None=Depends(admin)):
    try: return core.move_alias(req.model,req.alias,req.version,min_accuracy=float(os.getenv('MIN_ACCURACY','0.75')))
    except LookupError as exc: raise HTTPException(404,str(exc))
    except ValueError as exc: raise HTTPException(422,str(exc))
@app.post('/v1/deployments/rollback')
def rollback(req:Promotion,_:None=Depends(admin)):
    # Explicit chosen version, never blindly assume a version is safe.
    try:
        result=core.move_alias(req.model,'champion',req.version,min_accuracy=float(os.getenv('MIN_ACCURACY','0.75')))
        with core.Session.begin() as db: db.add(core.Audit(event='rollback',actor='admin',model=req.model,version=req.version,detail=json.dumps(result)))
        return result
    except LookupError as exc: raise HTTPException(404,str(exc))
    except ValueError as exc: raise HTTPException(422,str(exc))
@app.get('/v1/models')
def models(_:None=Depends(authorize)): return core.list_models()
@app.get('/v1/audit')
def audit(_:None=Depends(admin)): return core.audits()
@app.post('/v1/predict')
def predict(req:Predict,_:None=Depends(authorize)):
    start=time.perf_counter()
    if req.alias not in ('champion','candidate'): raise HTTPException(422,'Unsupported alias')
    status='ok'
    try:
        version,artifact=core.deployed(req.model,req.alias)
        result=core.infer(artifact,req.text)
        return {'model':req.model,'version':version,'alias':req.alias,**result}
    except LookupError as exc:
        status='missing'
        raise HTTPException(404,str(exc))
    finally:
        REQUESTS.labels(req.model,status).inc()
        LATENCY.labels(req.model).observe(time.perf_counter()-start)
@app.get('/',response_class=HTMLResponse)
def home(): return Path(__file__).with_name('dashboard.html').read_text(encoding='utf8')

class PromptRegister(BaseModel):
    name:str
    template:str
    cases:list[dict]
class PromptPromotion(BaseModel):
    name:str
    version:int=Field(gt=0)
class LLMRun(BaseModel):
    name:str
    context:dict[str,str]

@app.post('/v1/prompts/register')
def prompt_register(req:PromptRegister,_:None=Depends(admin)):
    try:
        score=llm.eval_prompt(req.template,req.cases)
        return llm.register_prompt(req.name,req.template,score)
    except (ValueError,KeyError,TypeError) as exc:raise HTTPException(422,str(exc))

@app.post('/v1/prompts/promote')
def prompt_promote(req:PromptPromotion,_:None=Depends(admin)):
    try:return llm.promote_prompt(req.name,req.version)
    except LookupError as exc:raise HTTPException(404,str(exc))
    except ValueError as exc:raise HTTPException(422,str(exc))

@app.post('/v1/llm/run')
def llm_run(req:LLMRun,_:None=Depends(authorize)):
    try:
        version,template=llm.deployed_prompt(req.name)
        prompt=llm.render(template,req.context)
        result=llm.openai_completion(prompt)
        return {'name':req.name,'prompt_version':version,**result}
    except LookupError as exc:raise HTTPException(404,str(exc))
    except ValueError as exc:raise HTTPException(422,str(exc))
    except RuntimeError as exc:raise HTTPException(503,str(exc))
