"""Reproducible small text classifier training; self-contained and safe JSON model format."""
import argparse,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from app.core import infer

TRAIN=[('service excellent fast reliable','positive'),('helpful responsive support','positive'),('accurate useful results','positive'),('fantastic quality and speed','positive'),('good product trustworthy','positive'),('happy satisfied with service','positive'),('system stable performance','positive'),('very convenient delightful','positive'),('awful broken slow service','negative'),('terrible buggy unreliable','negative'),('frustrating errors and crashes','negative'),('bad product low quality','negative'),('unhelpful support problems','negative'),('incorrect disappointing response','negative'),('unstable outage failure','negative'),('poor performance confusing','negative')]
HOLDOUT=[('excellent reliable system','positive'),('very helpful support','positive'),('accurate and fast','positive'),('stable quality good','positive'),('terrible errors crashes','negative'),('slow poor service','negative'),('unreliable frustrating product','negative'),('bad and incorrect results','negative')]
def train(c=1.0):
    x,y=zip(*TRAIN)
    vec=CountVectorizer(lowercase=True,token_pattern=r'(?u)\b\w+\b',binary=False)
    X=vec.fit_transform(x)
    mod=LogisticRegression(random_state=7,C=c,max_iter=1000).fit(X,[int(v=='positive') for v in y])
    artifact={'kind':'bag-of-words-logistic-v1','bias':float(mod.intercept_[0]),'weights':{w:float(mod.coef_[0][i]) for w,i in vec.vocabulary_.items()},'labels':['negative','positive']}
    pred=[infer(artifact,text)['label'] for text,_ in HOLDOUT]
    accuracy=float(accuracy_score([v for _,v in HOLDOUT],pred))
    return artifact,accuracy
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--output',default='data/trained-model.json');a.add_argument('--regularization',type=float,default=1.0)
    args=a.parse_args();artifact,accuracy=train(args.regularization)
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps({'model':'sentiment','accuracy':accuracy,'artifact':artifact},indent=2)+'\n')
    print(json.dumps({'output':str(output),'holdout_accuracy':accuracy,'holdout_n':len(HOLDOUT)}))
