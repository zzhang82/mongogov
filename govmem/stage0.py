"""Stage 0 sandbox check: connect, create collections and index, prove it with a live query."""
import datetime
import time

from . import config, db


def main():
    now = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    d = db.db()
    info = d.client.server_info()
    print("%s connected: server %s, database %r" % (now(), info["version"], d.name))
    try:
        status = d.client.admin.command("connectionStatus")
        roles = [r["role"] + "@" + r["db"] for r in status["authInfo"]["authenticatedUserRoles"]]
        print("roles:", roles)
    except Exception as exc:  # report, do not hide
        print("roles: could not read (%s)" % type(exc).__name__)
    db.ensure_collections()
    print("collections:", sorted(d.list_collection_names()))
    print("search indexes on memories before:", [(i["name"], i.get("status")) for i in db.memories().list_search_indexes()])
    print("vector index:", db.ensure_vector_index())
    ready = db.wait_index_ready()
    print("%s index %s status=%s queryable=%s" % (now(), ready["name"], ready["status"], ready["queryable"]))
    print("definition:", ready.get("latestDefinition"))

    # Live query: one probe document that only this check can see.
    vec = [0.0] * config.EMBED_DIMS
    vec[0] = 1.0
    probe = {
        "_id": "stage0-probe",
        "namespace": "_stage0",
        "lifecycle": "active",
        "actor": "stage0-check",
        "evidence": 0.0,
        "symptom": "stage 0 readiness probe",
        "fix_steps": ["none"],
        "source_ticket": "stage0",
        "embedding": vec,
    }
    hit, lag, other = [], 0.0, []
    try:
        db.memories().replace_one({"_id": probe["_id"]}, probe, upsert=True)
        pipeline = [
            {"$vectorSearch": {"index": config.VECTOR_INDEX, "path": "embedding", "queryVector": vec,
                               "numCandidates": 20, "limit": 3,
                               "filter": {"namespace": "_stage0", "lifecycle": "active"}}},
            {"$project": {"_id": 1, "score": {"$meta": "vectorSearchScore"}}},
        ]
        start = time.time()
        while time.time() - start < 120 and not hit:
            hit = list(db.memories().aggregate(pipeline))
            if not hit:
                time.sleep(2)
        lag = time.time() - start
        other = list(db.memories().aggregate([
            {"$vectorSearch": {"index": config.VECTOR_INDEX, "path": "embedding", "queryVector": vec,
                               "numCandidates": 20, "limit": 3,
                               "filter": {"namespace": "_other_team", "lifecycle": "active"}}},
            {"$project": {"_id": 1}}]))
    finally:
        db.memories().delete_one({"_id": probe["_id"]})
    print("%s live $vectorSearch: %r after %.1fs sync lag" % (now(), hit, lag))
    print("same query, other namespace filter: %r" % other)
    ok = bool(hit) and hit[0]["_id"] == "stage0-probe" and not other
    print("STAGE 0:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
