import os,tempfile
from pathlib import Path
# Database must be selected before any app/core import.
_test=tempfile.TemporaryDirectory()
os.environ['DATABASE_URL']='sqlite:///'+str(Path(_test.name)/'test.db')
os.environ['INFERENCE_API_KEY']='test-inference-secret'
os.environ['ADMIN_API_KEY']='test-admin-secret'
