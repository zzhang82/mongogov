"""Governed memory. The only module that writes the memories and reviews collections."""
import datetime

from . import config, db, receipts
from .embed import cosine, embed

GOV_RUN = "governance"  # receipt chain for human governance actions

# G1: legal lifecycle moves. Anything else raises.
ALLOWED = {
    "candidate": {"active", "retired"},
    "active": {"superseded", "retired"},
    "superseded": set(),
    "retired": set(),
}
REQUIRED = ("namespace", "lifecycle", "actor", "evidence", "symptom", "fix_steps", "source_ticket")


class GovernanceError(Exception):
    pass


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def check_transition(old, new):
    if new not in ALLOWED.get(old, set()):
        raise GovernanceError("illegal lifecycle move: %s -> %s" % (old, new))


def validate(doc):
    for field in REQUIRED:
        if doc.get(field) in (None, "", []):
            raise GovernanceError("memory needs %s" % field)
    if doc["lifecycle"] not in config.LIFECYCLES:
        raise GovernanceError("unknown lifecycle %r" % doc["lifecycle"])
    if not 0.0 <= float(doc["evidence"]) <= 1.0:
        raise GovernanceError("evidence must be between 0 and 1")
    if doc["lifecycle"] == "active":
        if not doc.get("approved_by"):
            raise GovernanceError("an active memory needs approved_by")
        if doc["approved_by"] == doc["actor"]:
            raise GovernanceError("the approver must differ from the actor who proposed the fix")
    if len(doc.get("embedding") or []) != config.EMBED_DIMS:
        raise GovernanceError("memory needs a %d-dim embedding" % config.EMBED_DIMS)


def build(memory_id, namespace, symptom, fix, actor, source_ticket, lifecycle="candidate",
          evidence=config.CANDIDATE_EVIDENCE, approved_by=None, supersedes=None, lineage=None, note=None,
          embedding=None):
    doc = {
        "_id": memory_id, "namespace": namespace, "lifecycle": lifecycle, "symptom": symptom,
        "cause": fix["cause"], "fix_id": fix["fix_id"], "fix_title": fix["title"], "fix_steps": list(fix["steps"]),
        "evidence": float(evidence), "actor": actor, "approved_by": approved_by,
        "approved_at": _now() if approved_by else None, "supersedes": supersedes, "superseded_by": None,
        "lineage": lineage or memory_id, "source_ticket": source_ticket, "note": note,
        "created_at": _now(), "updated_at": _now(),
        "embedding": embedding if embedding is not None else embed([symptom])[0],
    }
    validate(doc)
    return doc


# ---------- learning: candidate first, never active on arrival ----------

def propose(namespace, symptom, fix, actor, source_ticket, supersedes=None, lineage=None, memory_id=None):
    """Store a learned fix as a CANDIDATE and queue it for human review. Idempotent per id."""
    memory_id = memory_id or "mem-" + source_ticket
    existing = db.memories().find_one({"_id": memory_id}, {"embedding": 0})
    if existing:
        return existing
    doc = build(memory_id, namespace, symptom, fix, actor, source_ticket, supersedes=supersedes, lineage=lineage)
    db.memories().insert_one(doc)
    db.reviews().insert_one({
        "_id": "rev-" + memory_id, "kind": "candidate", "memory_id": memory_id, "namespace": namespace, "status": "pending",
        "source_ticket": source_ticket, "proposed_by": actor, "supersedes": supersedes,
        "decided_by": None, "decided_at": None, "reason": None, "created_at": _now()})
    receipts.append(GOV_RUN, "event", "propose", {"memory": memory_id, "namespace": namespace,
                    "source_ticket": source_ticket, "supersedes": supersedes}, {"lifecycle": "candidate"}, actor)
    return doc


def open_hold(ticket_id, namespace, run_id, fix_id, confidence):
    """Queue a held ticket for a human. Idempotent per run."""
    review_id = "hold-" + run_id
    db.reviews().update_one({"_id": review_id}, {"$setOnInsert": {
        "kind": "hold", "memory_id": None, "namespace": namespace, "status": "pending",
        "source_ticket": ticket_id, "proposed_by": "agent", "fix_id": fix_id, "confidence": confidence,
        "decided_by": None, "decided_at": None, "reason": None, "created_at": _now()}}, upsert=True)
    return review_id


def _close_ticket(ticket_id, status, by):
    db.tickets().update_one({"_id": ticket_id}, {"$set": {"status": status, "closed_by": by}})


def _pending(review_id):
    review = db.reviews().find_one({"_id": review_id})
    if not review:
        raise GovernanceError("no review %s" % review_id)
    if review["status"] != "pending":
        raise GovernanceError("review %s is already %s" % (review_id, review["status"]))
    mem = db.memories().find_one({"_id": review["memory_id"]}) if review.get("memory_id") else None
    return review, mem


def promote(review_id, approver):
    """Human approval: candidate -> active. A successor supersedes its parent in the same step."""
    review, mem = _pending(review_id)
    if approver in ("agent", review["proposed_by"]):
        raise GovernanceError("%s requested this review and cannot also approve it" % approver)
    if mem is None:  # a held ticket with no new memory: the human approves the answer
        db.reviews().update_one({"_id": review_id}, {"$set": {"status": "approved", "decided_by": approver,
                                                              "decided_at": _now()}})
        _close_ticket(review["source_ticket"], "resolved", approver)
        receipts.append(GOV_RUN, "event", "approve_hold", {"review": review_id, "ticket": review["source_ticket"]},
                        {"ticket": "resolved"}, approver)
        return None
    check_transition(mem["lifecycle"], "active")
    if approver == mem["actor"]:
        raise GovernanceError("%s proposed this fix and cannot also approve it" % approver)
    old = db.memories().find_one({"_id": mem["supersedes"]}) if mem.get("supersedes") else None
    if old:
        check_transition(old["lifecycle"], "superseded")
    with db.db().client.start_session() as session:
        with session.start_transaction():
            if old:
                db.memories().update_one({"_id": old["_id"], "lifecycle": "active"},
                                         {"$set": {"lifecycle": "superseded", "superseded_by": mem["_id"],
                                                   "updated_at": _now()}}, session=session)
            db.memories().update_one({"_id": mem["_id"], "lifecycle": "candidate"},
                                     {"$set": {"lifecycle": "active", "approved_by": approver,
                                               "approved_at": _now(), "evidence": config.PROMOTED_EVIDENCE,
                                               "updated_at": _now()}}, session=session)
            db.reviews().update_one({"_id": review_id}, {"$set": {"status": "approved", "decided_by": approver,
                                                                  "decided_at": _now()}}, session=session)
    if not old:
        _close_ticket(review["source_ticket"], "resolved", approver)
    receipts.append(GOV_RUN, "event", "promote", {"memory": mem["_id"], "review": review_id},
                    {"lifecycle": "active", "evidence": config.PROMOTED_EVIDENCE,
                     "superseded": old["_id"] if old else None}, approver)
    return db.memories().find_one({"_id": mem["_id"]}, {"embedding": 0})


def reject(review_id, approver, reason):
    review, mem = _pending(review_id)
    if approver in ("agent", review["proposed_by"]):
        raise GovernanceError("%s requested this review and cannot also decide it" % approver)
    if mem is not None:
        check_transition(mem["lifecycle"], "retired")
        db.memories().update_one({"_id": mem["_id"]}, {"$set": {"lifecycle": "retired", "updated_at": _now()}})
    _close_ticket(review["source_ticket"], "escalated", approver)
    db.reviews().update_one({"_id": review_id}, {"$set": {"status": "rejected", "decided_by": approver,
                                                          "decided_at": _now(), "reason": reason}})
    receipts.append(GOV_RUN, "event", "reject", {"memory": mem["_id"] if mem else None, "review": review_id, "reason": reason},
                    {"lifecycle": "retired"}, approver)


# ---------- G5: correction and forgetting ----------

def revise(memory_id, new_steps, actor, note=None):
    """Propose a corrected version. The old one stays active until a human promotes the successor."""
    old = db.memories().find_one({"_id": memory_id})
    if not old or old["lifecycle"] != "active":
        raise GovernanceError("only an active memory can be revised")
    version = db.memories().count_documents({"lineage": old["lineage"]}) + 1
    fix = {"cause": old["cause"], "fix_id": old["fix_id"], "title": note or old["fix_title"], "steps": new_steps}
    return propose(old["namespace"], old["symptom"], fix, actor, old["source_ticket"], supersedes=old["_id"],
                   lineage=old["lineage"], memory_id="%s-v%d" % (old["lineage"], version))


def forget(memory_id, actor, reason):
    mem = db.memories().find_one({"_id": memory_id})
    if not mem:
        raise GovernanceError("no memory %s" % memory_id)
    check_transition(mem["lifecycle"], "retired")
    db.memories().update_one({"_id": memory_id}, {"$set": {"lifecycle": "retired", "updated_at": _now()}})
    receipts.append(GOV_RUN, "event", "forget", {"memory": memory_id, "reason": reason},
                    {"lifecycle": "retired"}, actor)


def resolve(memory_id):
    """Follow superseded_by links to the current version of a fix."""
    doc = db.memories().find_one({"_id": memory_id}, {"embedding": 0})
    while doc and doc.get("superseded_by"):
        doc = db.memories().find_one({"_id": doc["superseded_by"]}, {"embedding": 0})
    return doc


# ---------- recall: the one query builder (G1 + G2 live here and nowhere else) ----------

def recall_pipeline(namespace, query_vector, limit=5):
    if not namespace:
        raise GovernanceError("recall needs a team namespace")
    return [
        {"$vectorSearch": {"index": config.VECTOR_INDEX, "path": "embedding", "queryVector": query_vector,
                           "numCandidates": 100, "limit": limit,
                           "filter": {"namespace": namespace, "lifecycle": "active"}}},
        {"$set": {"search_score": {"$meta": "vectorSearchScore"}}},
    ]


def recall(namespace, query_vector, limit=5):
    """Active memories of one team, re-scored by exact cosine. Order: cosine down, then id."""
    hits = []
    for doc in db.memories().aggregate(recall_pipeline(namespace, query_vector, limit)):
        if doc["namespace"] != namespace or doc["lifecycle"] != "active":
            raise GovernanceError("recall returned a record outside its filter: %s" % doc["_id"])
        doc["similarity"] = round(cosine(query_vector, doc.pop("embedding")), 4)
        hits.append(doc)
    hits.sort(key=lambda d: (-d["similarity"], d["_id"]))
    return hits
