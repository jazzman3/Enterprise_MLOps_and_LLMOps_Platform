"""LLMOps prompt versioning and evaluation. Real provider opt-in; no fabricated LLM response."""
import json, os, re, urllib.request, urllib.error
from sqlalchemy import Column, Integer, String, Text, Float, ForeignKey, UniqueConstraint
from .core import Base, Session, Audit

class PromptVersion(Base):
    __tablename__='prompt_versions'
    id=Column(Integer,primary_key=True)
    name=Column(String(128),nullable=False)
    version=Column(Integer,nullable=False)
    template=Column(Text,nullable=False)
    evaluation_score=Column(Float,nullable=False)
    __table_args__=(UniqueConstraint('name','version'),)

class PromptAlias(Base):
    __tablename__='prompt_aliases'
    name=Column(String(128),primary_key=True)
    alias=Column(String(64),primary_key=True)
    version=Column(Integer,nullable=False)

def render(template,context):
    if len(template)>20000: raise ValueError('Template too long')
    keys=set(re.findall(r'\{([a-z][a-z0-9_]*)\}',template))
    if len(keys)>20: raise ValueError('Too many placeholders')
    if any(k not in context for k in keys): raise ValueError('Missing template variables')
    rendered=template
    for k in keys:rendered=rendered.replace('{'+k+'}',str(context[k])[:5000])
    return rendered

def eval_prompt(template,cases):
    # Explicit deterministic formatting evaluation, not LLM judged quality.
    if not cases: raise ValueError('At least one case required')
    return sum(all(str(token) in render(template,c['context']) for token in c['must_contain']) for c in cases)/len(cases)

def register_prompt(name,template,score):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{1,63}',name):raise ValueError('Invalid name')
    if not 0<=score<=1:raise ValueError('Score out of range')
    render(template,{k:'test' for k in re.findall(r'\{([a-z][a-z0-9_]*)\}',template)})
    with Session.begin() as db:
        last=db.query(PromptVersion).filter_by(name=name).order_by(PromptVersion.version.desc()).first()
        v=1 if not last else last.version+1
        db.add(PromptVersion(name=name,version=v,template=template,evaluation_score=score))
        db.add(Audit(event='prompt_register',actor='admin',model=name,version=v,detail=json.dumps({'format_eval':score})))
    return {'name':name,'version':v,'format_eval':score}

def promote_prompt(name,version,threshold=0.8):
    with Session.begin() as db:
        p=db.query(PromptVersion).filter_by(name=name,version=version).one_or_none()
        if p is None:raise LookupError('Prompt version not found')
        if p.evaluation_score<threshold:raise ValueError('Prompt quality gate failed')
        alias=db.get(PromptAlias,(name,'champion'))
        old=alias.version if alias else None
        if alias: alias.version=version
        else:db.add(PromptAlias(name=name,alias='champion',version=version))
        db.add(Audit(event='prompt_promote',actor='admin',model=name,version=version,detail=json.dumps({'previous':old})))
    return {'name':name,'previous_version':old,'version':version}

def deployed_prompt(name):
    with Session() as db:
        alias=db.get(PromptAlias,(name,'champion'))
        if not alias: raise LookupError('Prompt not deployed')
        p=db.query(PromptVersion).filter_by(name=name,version=alias.version).one()
        return p.version,p.template

def openai_completion(prompt):
    key=os.environ.get('OPENAI_API_KEY')
    if not key: raise RuntimeError('OPENAI_API_KEY not configured; real LLM inference unavailable')
    body=json.dumps({'model':os.getenv('OPENAI_MODEL','gpt-4.1-mini'),'input':prompt,'max_output_tokens':300}).encode()
    request=urllib.request.Request('https://api.openai.com/v1/responses',data=body,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(request,timeout=30) as response: result=json.load(response)
    text=''.join(chunk.get('text','') for item in result.get('output',[]) for chunk in item.get('content',[]) if chunk.get('type')=='output_text')
    return {'output':text,'provider':'openai','model':result.get('model'),'usage':result.get('usage',{})}
