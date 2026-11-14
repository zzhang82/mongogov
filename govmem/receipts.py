"""Hash-chained receipts in the runs collection: the audit log and the resume source.

Genesis rule: the first receipt of a run has prev_hash = sha256("govmem:genesis:" + run_id).
hash = sha256(prev_hash + canonical JSON of the receipt body).
kind is "tool" (counts as a tool call) or "event" (a governance decision such as a veto).
"""
import datetime
import hashlib
import json

from . import db

BODY_FIELDS = ("run_id", "seq", "kind", "tool", "inputs", "result", "actor", "ts")


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def genesis(run_id):
    return hashlib.sha256(("govmem:genesis:" + run_id).encode()).hexdigest()


def compute_hash(prev_hash, body):
    return hashlib.sha256((prev_hash + canonical({k: body[k] for k in BODY_FIELDS})).encode()).hexdigest()


def digest(kind, tool, inputs, result):
    """Run-independent digest of a step: no run id, no time. Used to compare two runs."""
    return hashlib.sha256(canonical([kind, tool, inputs, result]).encode()).hexdigest()[:16]


def load(run_id):
    return list(db.runs().find({"run_id": run_id}).sort("seq", 1))


def append(run_id, kind, tool, inputs, result, actor="agent"):
    """Write the next receipt of a run. Returns the stored document.

    The unique index on (run_id, seq) and the _id refuse a second receipt for one step.
    """
    last = db.runs().find_one({"run_id": run_id}, sort=[("seq", -1)])
    seq = last["seq"] + 1 if last else 1
    prev_hash = last["hash"] if last else genesis(run_id)
    body = {"run_id": run_id, "seq": seq, "kind": kind, "tool": tool, "inputs": inputs, "result": result,
            "actor": actor, "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")}
    doc = dict(body, _id="%s:%04d" % (run_id, seq), prev_hash=prev_hash, hash=compute_hash(prev_hash, body),
               digest=digest(kind, tool, inputs, result))
    db.runs().insert_one(doc)
    return doc


def verify_chain(receipts, run_id):
    """Recompute every hash. Returns (ok, message). Nothing stored is trusted."""
    prev = genesis(run_id)
    for position, doc in enumerate(receipts, start=1):
        if doc["seq"] != position:
            return False, "sequence gap: expected %d, found %d" % (position, doc["seq"])
        if doc["prev_hash"] != prev:
            return False, "seq %d: prev_hash does not match the receipt before it" % position
        if compute_hash(prev, doc) != doc["hash"]:
            return False, "seq %d: stored hash does not match its content" % position
        prev = doc["hash"]
    return True, "%d receipts, chain verifies" % len(receipts)


def tail_state(receipts):
    if not receipts:
        return "empty"
    if receipts[-1].get("tool") == "final":
        return "complete"
    return "open"


def verify(run_id, expect_final=False):
    docs = load(run_id)
    ok, message = verify_chain(docs, run_id)
    if not ok:
        return False, message
    if expect_final:
        state = tail_state(docs)
        if state != "complete":
            return False, "run not complete: tail state is %s" % state
    return True, message
