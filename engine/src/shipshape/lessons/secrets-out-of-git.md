---
concept: Keeping secrets out of git
summary: API keys and passwords belong in environment variables or a git-ignored .env file, never in code or in a committed file.
---

## The idea

Anything committed to git stays in its history, even after you delete it in a later commit. Push it to GitHub and automated scanners can find a key within minutes. So credentials (API keys, tokens, database passwords) never go into source code. The usual pattern: the code reads them from environment variables, and on your own machine a `.env` file sets those variables. That `.env` file is listed in `.gitignore`, and a `.env.example` with empty values documents what is needed.

If a real key was ever committed, deleting it is not enough: revoke it at the provider and create a new one.

## Before and after

```python
# Before
WANDB_API_KEY = "a3f9c2e81b7d4..."
```

```python
# After: the key comes from the environment (or a git-ignored .env file)
import os

WANDB_API_KEY = os.environ["WANDB_API_KEY"]
```

```text
# .gitignore
.env
```

## Why engineers care

Leaked keys cost money (someone else runs jobs on your account), leak data and can get accounts suspended. It is also one of the easiest problems to avoid, so reviewers treat it as a basic signal of care.

## How Shipshape spots it

Two checks. One asks git whether a `.env` file would be committed (it never reads the file). The other looks for known key formats and for variables with credential-like names (`api_key`, `token`, `password`, `secret`) assigned key-like strings; the value is always redacted in the report. Values found only in test files are reported as minor, because tests often need fake keys: mark a fake one with `# shipshape: ignore[security.hardcoded-secret]`. It cannot tell a real key from a convincing fake, and it does not scan git history.

## Read more

- [git: gitignore](https://git-scm.com/docs/gitignore)
- [python-dotenv: load a .env file](https://pypi.org/project/python-dotenv/)
- [The Twelve-Factor App: config](https://12factor.net/config)
