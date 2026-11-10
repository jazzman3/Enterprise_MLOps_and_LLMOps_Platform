from fastapi.testclient import TestClient
from app.main import app
from app import core
import pytest

@pytest.fixture
def client():
    with TestClient(app) as c:
        with core.Session.begin() as db:
            db.execute(__import__('sqlalchemy').text('DELETE FROM prompt_aliases'))
            db.execute(__import__('sqlalchemy').text('DELETE FROM prompt_versions'))
        yield c

def admin():return {'X-Admin-Key':'test-admin-secret'}
def user():return {'X-API-Key':'test-inference-secret'}
def payload(template='Summary: {topic}'):
    return {'name':'summarizer','template':template,'cases':[{'context':{'topic':'energy'},'must_contain':['Summary:','energy']} ]}

def test_prompt_version_creation(client):
    assert client.post('/v1/prompts/register',headers=admin(),json=payload()).json()['version']==1
    assert client.post('/v1/prompts/register',headers=admin(),json=payload()).json()['version']==2

def test_prompt_access_control(client):
    assert client.post('/v1/prompts/register',json=payload()).status_code==401

def test_prompt_promotion(client):
    client.post('/v1/prompts/register',headers=admin(),json=payload())
    result=client.post('/v1/prompts/promote',headers=admin(),json={'name':'summarizer','version':1})
    assert result.status_code==200

def test_prompt_quality_gate(client):
    r=client.post('/v1/prompts/register',headers=admin(),json=payload('No topic'))
    assert r.json()['format_eval']==0
    assert client.post('/v1/prompts/promote',headers=admin(),json={'name':'summarizer','version':1}).status_code==422

def test_no_fake_llm_response_without_provider(client):
    client.post('/v1/prompts/register',headers=admin(),json=payload())
    client.post('/v1/prompts/promote',headers=admin(),json={'name':'summarizer','version':1})
    r=client.post('/v1/llm/run',headers=user(),json={'name':'summarizer','context':{'topic':'energy'}})
    assert r.status_code==503 and 'not configured' in r.text

def test_template_missing_context(client):
    client.post('/v1/prompts/register',headers=admin(),json=payload())
    client.post('/v1/prompts/promote',headers=admin(),json={'name':'summarizer','version':1})
    r=client.post('/v1/llm/run',headers=user(),json={'name':'summarizer','context':{}})
    assert r.status_code==422
