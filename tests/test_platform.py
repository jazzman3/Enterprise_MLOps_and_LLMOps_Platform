import copy,json,pytest
from fastapi.testclient import TestClient
from app.main import app
from app import core
from scripts.train import train

@pytest.fixture
def client():
    with TestClient(app) as c:
        with core.Session.begin() as db:
            db.query(core.Audit).delete();db.query(core.Alias).delete();db.query(core.Version).delete()
        yield c

def admin():return {'X-Admin-Key':'test-admin-secret'}
def user():return {'X-API-Key':'test-inference-secret'}
def fixture_model(client,name='sentiment'):
    artifact,accuracy=train()
    out=client.post('/v1/models/register',headers=admin(),json={'model':name,'artifact':artifact,'accuracy':accuracy})
    assert out.status_code==200,out.text
    return out.json(),artifact

def test_health(client):assert client.get('/healthz').json()=={'status':'ok'}
def test_ready(client):assert client.get('/readyz').status_code==200
def test_requires_user_auth(client):assert client.get('/v1/models').status_code==401
def test_requires_admin_auth(client):assert client.post('/v1/deployments/promote',json={}).status_code==401
def test_incorrect_admin_key(client):assert client.get('/v1/audit',headers={'X-Admin-Key':'invalid'}).status_code==401
def test_registration_and_versioning(client):
    a,_=fixture_model(client);b,_=fixture_model(client)
    assert (a['version'],b['version'])==(1,2)
def test_artifact_checksum(client):
    registered,_=fixture_model(client)
    assert len(registered['sha256'])==64
def test_bad_artifact_rejected(client):
    r=client.post('/v1/models/register',headers=admin(),json={'model':'test','accuracy':0.95,'artifact':{'kind':'unsafe-pickle','bias':0,'weights':{},'labels':['n','p']}})
    assert r.status_code==422
def test_bad_model_name(client):
    _,art=fixture_model(client)
    assert client.post('/v1/models/register',headers=admin(),json={'model':'../bad','accuracy':0.95,'artifact':art}).status_code==422
def test_missing_deployment(client):assert client.post('/v1/predict',headers=user(),json={'model':'missing','text':'hello'}).status_code==404
def test_promote_and_infer(client):
    v,_=fixture_model(client)
    r=client.post('/v1/deployments/promote',headers=admin(),json={'model':'sentiment','version':v['version']})
    assert r.status_code==200,r.text
    p=client.post('/v1/predict',headers=user(),json={'model':'sentiment','text':'excellent helpful service'})
    assert p.status_code==200 and p.json()['version']==1

def test_quality_gate(client):
    artifact,_=train()
    artifact['weights']={}
    artifact['bias']=0
    r=client.post('/v1/models/register',headers=admin(),json={'model':'lowquality','artifact':artifact,'accuracy':0.99})
    assert r.status_code==200
    p=client.post('/v1/deployments/promote',headers=admin(),json={'model':'lowquality','version':1})
    assert p.status_code==422

def test_canary_alias(client):
    fixture_model(client)
    assert client.post('/v1/deployments/promote',headers=admin(),json={'model':'sentiment','version':1,'alias':'candidate'}).status_code==200
    assert client.post('/v1/predict',headers=user(),json={'model':'sentiment','alias':'candidate','text':'bad'}).status_code==200

def test_rollback(client):
    first,_=fixture_model(client)
    second,_=fixture_model(client)
    for v in (1,2):assert client.post('/v1/deployments/promote',headers=admin(),json={'model':'sentiment','version':v}).status_code==200
    assert client.post('/v1/deployments/rollback',headers=admin(),json={'model':'sentiment','version':1}).status_code==200
    assert core.deployed('sentiment')[0]==1
    assert any(a['event']=='rollback' for a in client.get('/v1/audit',headers=admin()).json())
def test_invalid_alias(client):
    fixture_model(client)
    assert client.post('/v1/deployments/promote',headers=admin(),json={'model':'sentiment','version':1,'alias':'other'}).status_code==422
def test_model_registry_endpoint(client):
    fixture_model(client)
    assert len(client.get('/v1/models',headers=user()).json()['versions'])==1
def test_metrics_private(client):
    assert client.get('/metrics').status_code==401
    assert client.get('/metrics',headers=admin()).status_code==200
def test_artifact_integrity(client):
    fixture_model(client)
    client.post('/v1/deployments/promote',headers=admin(),json={'model':'sentiment','version':1})
    with core.Session.begin() as db:
        v=db.query(core.Version).filter_by(model='sentiment',version=1).one()
        v.sha256='0'*64
    with pytest.raises(RuntimeError,match='checksum'):core.deployed('sentiment')
def test_empty_text_rejected(client):
    assert client.post('/v1/predict',headers=user(),json={'text':''}).status_code==422
def test_audit_history(client):
    fixture_model(client)
    assert client.get('/v1/audit',headers=admin()).json()[0]['event']=='register'
