import matplotlib.pyplot as plt
import requests

from settings import OPENAI_API_KEY


def plot_auc(results):
    names = list(results)
    plt.bar(names, [results[n] for n in names])
    plt.ylabel("AUC")
    plt.savefig("C:/Users/lena/Pictures/auc.png")


def summarise_with_gpt(results):
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": str(results)}]},
        timeout=30,
    )
    return response.json()["choices"][0]["message"]["content"]
