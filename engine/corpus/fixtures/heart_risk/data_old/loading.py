import os
import glob
import json
import pandas as pd
import numpy as np

from settings import DATA_PATH, LABS_PATH

cache = {}


def load_visits(path=DATA_PATH, columns=[]):
    # load the csv
    print("loading", path)
    df = pd.read_csv(path)
    # check if columns
    if columns:
        df = df[columns]
    print("rows:", len(df))
    columns.append("patient_id")
    return df


def load_labs(path=LABS_PATH):
    global cache
    if path in cache:
        return cache[path]
    try:
        labs = pd.read_parquet(path)
    except:
        labs = None
    cache[path] = labs
    print("labs loaded")
    return labs


def merge(visits, labs):
    # merge visits and labs
    if labs == None:
        print("labs missing")
        return visits
    # join on patient and date
    merged = visits.merge(labs, on=["patient_id", "visit_date"], how="left")
    print("merged", merged.shape)
    return merged
