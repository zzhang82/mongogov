"""The simulated support environment. These are the agent's tools.

Nothing here is a real product API. Accounts and their faults come from seed/accounts.json,
written today. The tools are deterministic: same input, same output.
"""
import re

from . import memory, seed
from .embed import embed

_accounts = None


def accounts():
    global _accounts
    if _accounts is None:
        _accounts = seed.load("accounts")
    return _accounts


def recall_memory(team, text):
    hits = memory.recall(team, embed([text])[0])
    return {"hits": [{"memory": h["_id"], "similarity": h["similarity"], "evidence": h["evidence"],
                      "fix_id": h["fix_id"], "cause": h["cause"]} for h in hits]}


def get_account(account):
    info = accounts().get(account)
    if not info:
        return {"found": False}
    return {"found": True, "plan": info["plan"], "region": info["region"]}


def check_service_status(region):
    return {"region": region, "incident": None}


def fetch_logs(account):
    info = accounts().get(account)
    if not info:
        return {"line": None, "cause": None}
    found = re.search(r"code=(\w+)", info["log"])
    return {"line": info["log"], "cause": found.group(1) if found else None}


def lookup_catalog(cause):
    for fix in seed.catalog().values():
        if fix["cause"] == cause:
            return {"fix_id": fix["fix_id"], "title": fix["title"]}
    return {"fix_id": None, "title": None}


def apply_fix(account, fix_id):
    return {"applied": fix_id in seed.catalog() and account in accounts(), "fix_id": fix_id}


def verify_fix(account, fix_id):
    """True only when the applied fix addresses the account's real fault."""
    info = accounts().get(account)
    fix = seed.catalog().get(fix_id)
    cause = fetch_logs(account)["cause"] if info else None
    return {"resolved": bool(fix and cause and fix["cause"] == cause)}
