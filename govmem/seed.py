"""Seed today's synthetic data. Rerunnable: the same input always gives the same stored state."""
import json
import time
from pathlib import Path

from . import config, db, memory, receipts
from .embed import embed, ticket_text

SEED = Path(__file__).resolve().parent.parent / "seed"


def load(name):
    return json.loads((SEED / (name + ".json")).read_text())


def catalog():
    return {fix["fix_id"]: fix for fix in load("catalog")}


def seed(reset=False):
    db.ensure_collections()
    if reset:
        for coll in (db.memories(), db.reviews(), db.tickets()):
            coll.delete_many({})
    fixes = catalog()
    tickets = load("training_tickets")
    vectors = embed([ticket_text(t) for t in tickets])  # one batch call
    for ticket, vec in zip(tickets, vectors):
        memory_id = "mem-" + ticket["id"]
        doc = memory.build(memory_id, ticket["team"], ticket_text(ticket), fixes[ticket["fix_id"]],
                           actor=ticket["resolved_by"], source_ticket=ticket["id"], lifecycle="active",
                           evidence=ticket["evidence"], approved_by=ticket["approved_by"],
                           note=ticket.get("note"), embedding=vec)
        doc["created_at"] = doc["updated_at"] = doc["approved_at"] = "seed"
        db.memories().replace_one({"_id": doc["_id"]}, doc, upsert=True)
        db.tickets().replace_one({"_id": ticket["id"]}, dict(ticket, _id=ticket["id"], status="resolved"),
                                 upsert=True)
        existing_receipt = db.runs().find_one({"tool": "seed_import", "inputs.memory": memory_id})
        if not existing_receipt:
            receipts.append(
                memory.GOV_RUN,
                "event",
                "seed_import",
                {"memory": memory_id, "source_ticket": ticket["id"]},
                {"lifecycle": "active", "evidence": ticket["evidence"]},
                ticket["approved_by"],
            )
    return len(tickets)


def wait_synced(timeout=180):
    """Wait until $vectorSearch sees every active memory. Measuring before this gives false misses."""
    db.wait_index_ready()
    want = {}
    for doc in db.memories().find({"lifecycle": "active"}, {"namespace": 1}):
        want.setdefault(doc["namespace"], set()).add(doc["_id"])
    probe = [0.01] * config.EMBED_DIMS
    start = time.time()
    while True:
        seen = {ns: {d["_id"] for d in db.memories().aggregate(memory.recall_pipeline(ns, probe, 50))}
                for ns in want}
        if seen == want:
            return time.time() - start, {ns: len(ids) for ns, ids in want.items()}
        if time.time() - start > timeout:
            raise SystemExit("index not in sync after %ss: want %r, see %r" % (timeout, want, seen))
        time.sleep(2)
