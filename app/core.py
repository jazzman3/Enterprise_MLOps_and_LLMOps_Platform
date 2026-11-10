import hashlib, hmac, json, os, re, time
from datetime import datetime, timezone
from contextlib import contextmanager
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Float, Text, UniqueConstraint, select
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./data/platform.db')
kwargs = {'connect_args': {'check_same_thread': False, 'timeout': 30}} if DATABASE_URL.startswith('sqlite') else {'pool_pre_ping': True}
engine = create_engine(DATABASE_URL, **kwargs)
Session = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()
def utcnow(): return datetime.now(timezone.utc)

class Version(Base):
    __tablename__='model_versions'
    id=Column(Integer,primary_key=True)
    model=Column(String(128), nullable=False)
    version=Column(Integer, nullable=False)
    artifact=Column(Text, nullable=False)
    sha256=Column(String(64),nullable=False)
    accuracy=Column(Float,nullable=False)
    created=Column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('model','version'),)

class Alias(Base):
    __tablename__='model_aliases'
    model=Column(String(128),primary_key=True)
    alias=Column(String(64),primary_key=True)
    version=Column(Integer,nullable=False)

class Audit(Base):
    __tablename__='audit_log'
    id=Column(Integer,primary_key=True)
    event=Column(String(64),nullable=False)
    actor=Column(String(128),nullable=False)
    model=Column(String(128),nullable=False)
    version=Column(Integer)
    detail=Column(Text,nullable=False)
    created=Column(DateTime(timezone=True),default=utcnow)

def init(): Base.metadata.create_all(engine)

def checksum(payload): return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def tokens(text): return re.findall(r'[a-z0-9]+',text.lower())

def infer(artifact,text):
    words=tokens(text)
    score=float(artifact['bias'])+sum(float(artifact['weights'].get(word,0)) for word in words)
    # avoid overflow
    from math import exp
    probability=1/(1+exp(-max(-30,min(30,score))))
    return {'label':artifact['labels'][1] if probability>=0.5 else artifact['labels'][0], 'positive_probability':round(probability,6)}

def register(model, artifact, accuracy, actor='admin'):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{1,63}',model): raise ValueError('Invalid model name')
    if not 0<=accuracy<=1: raise ValueError('accuracy must be in [0,1]')
    if artifact.get('kind')!='bag-of-words-logistic-v1' or not isinstance(artifact.get('weights'),dict) or len(artifact['weights'])>100000 or not isinstance(artifact.get('labels'),list) or len(artifact['labels'])!=2: raise ValueError('Unsupported model artifact')
    serialized=json.dumps(artifact,sort_keys=True)
    sha=checksum(artifact)
    with Session.begin() as db:
        prev=db.query(Version).filter(Version.model==model).order_by(Version.version.desc()).first()
        version=prev.version+1 if prev else 1
        db.add(Version(model=model,version=version,artifact=serialized,sha256=sha,accuracy=accuracy))
        db.add(Audit(event='register',actor=actor,model=model,version=version,detail=sha))
    return {'model':model,'version':version,'sha256':sha,'accuracy':accuracy}

def move_alias(model,alias,version, actor='admin', min_accuracy=0.75):
    if alias not in ('champion','candidate'): raise ValueError('Unsupported alias')
    with Session.begin() as db:
        v=db.query(Version).filter_by(model=model,version=version).one_or_none()
        if v is None: raise LookupError('Model version missing')
        if alias=='champion' and v.accuracy<min_accuracy: raise ValueError('Version does not meet quality gate')
        obj=db.get(Alias,(model,alias))
        prior=obj.version if obj else None
        if obj: obj.version=version
        else: db.add(Alias(model=model,alias=alias,version=version))
        db.add(Audit(event='promote' if alias=='champion' else 'alias',actor=actor,model=model,version=version,detail=json.dumps({'alias':alias,'previous':prior})))
    return {'model':model,'alias':alias,'previous_version':prior,'version':version}

def deployed(model,alias='champion'):
    with Session() as db:
        a=db.get(Alias,(model,alias))
        if not a: raise LookupError('No active deployment')
        v=db.query(Version).filter_by(model=model,version=a.version).one()
        artifact=json.loads(v.artifact)
        if checksum(artifact)!=v.sha256: raise RuntimeError('Artifact checksum mismatch')
        return v.version,artifact

def list_models():
    with Session() as db:
        versions=db.query(Version).order_by(Version.model,Version.version).all()
        aliases=db.query(Alias).all()
        return {'versions':[{'model':v.model,'version':v.version,'accuracy':v.accuracy,'sha256':v.sha256,'created':str(v.created)} for v in versions], 'aliases':[{'model':a.model,'alias':a.alias,'version':a.version} for a in aliases]}

def audits(limit=50):
    with Session() as db:
        events=db.query(Audit).order_by(Audit.id.desc()).limit(limit).all()
        return [{'event':a.event,'actor':a.actor,'model':a.model,'version':a.version,'detail':a.detail,'created':str(a.created)} for a in events]
