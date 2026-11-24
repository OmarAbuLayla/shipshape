import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier

import train


def build(kind="logreg"):
    if kind == "logreg":
        return LogisticRegression(max_iter=train.MAX_ITER)
    if kind == "forest":
        return RandomForestClassifier(n_estimators=300)
    return XGBClassifier(n_estimators=400, learning_rate=0.05)
