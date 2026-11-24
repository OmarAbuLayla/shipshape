from data.cleaning import *
import numpy as np


def add_features(df):
    df["pulse_pressure"] = df["sbp"] - df["dbp"]
    df["chol_ratio"] = df["chol"] / df["hdl"]
    df["obese"] = (df["bmi"] >= 30).astype(int)
    unused = df["age"].max()
    return df


def make_transforms(columns):
    transforms = []
    for col in columns:
        transforms.append(lambda frame: (frame[col] - frame[col].mean()) / frame[col].std())
    return transforms
