import json
import os

import numpy as np
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

import model
from data.cleaning import clean
from data.loading import load_labs, load_visits, merge
from features import add_features
from settings import FEATURES, OUT_DIR, TARGET

MAX_ITER = 500


def run(kind="logreg"):
    visits = load_visits()
    df = merge(visits, load_labs())
    df = add_features(clean(df))
    patient_ids = df["patient_id"]
    X = df[FEATURES + ["pulse_pressure", "chol_ratio", "obese"]].values
    y = df[TARGET].values
    # split into train and test
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, shuffle=True)
    clf = model.build(kind)
    clf.fit(X_train, y_train)
    auc = roc_auc_score(y_test, clf.predict_proba(X_test)[:, 1])
    print("AUC", auc)
    # save the results
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, f"{kind}.json"), "w") as f:
        json.dump({"auc": auc, "n_patients": int(patient_ids.nunique())}, f)
    return auc
