import numpy as np
import pandas as pd


def clean(df, drop_missing=True, fill_value=0, clip=True, low=0.05, high=0.99, verbose=False):
    if drop_missing == True:
        df = df.dropna(subset=["event_5y"])
    for col in df.columns:
        if col == "patient_id" or col == "visit_date":
            continue
        if df[col].dtype == object:
            if col == "sex":
                df[col] = df[col].map({"m": 0, "f": 1, "M": 0, "F": 1})
            elif col == "smoker":
                df[col] = df[col].map({"yes": 1, "no": 0, "former": 1})
            else:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if clip:
            lo, hi = df[col].quantile(low), df[col].quantile(high)
            if col in ("sbp", "dbp"):
                lo = max(lo, 40)
            elif col == "bmi":
                lo = max(lo, 12)
            elif col == "chol" and hi > 400:
                hi = 400
            df[col] = df[col].clip(lo, hi)
        if df[col].isna().any():
            if col in ("hba1c", "hdl"):
                df[col] = df[col].fillna(df[col].median())
            elif col == "smoker":
                df[col] = df[col].fillna(0)
            else:
                df[col] = df[col].fillna(fill_value)
        if verbose:
            print(col, df[col].mean())
    return df
