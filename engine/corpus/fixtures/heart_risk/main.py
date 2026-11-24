from report import plot_auc
from train import run

if __name__ == "__main__":
    results = {kind: run(kind) for kind in ("logreg", "forest", "xgb")}
    print(results)
    plot_auc(results)
