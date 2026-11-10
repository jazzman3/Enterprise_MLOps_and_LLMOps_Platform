import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core import init,register,move_alias
from scripts.train import train
init()
artifact,acc=train()
reg=register('sentiment',artifact,acc)
print(reg)
if acc >= 0.75: print(move_alias('sentiment','champion',reg['version']))
else: print('NOT PROMOTED: quality gate failed')
