"""MongoDB access: one client, three collections, one vector index."""
import time

from pymongo import ASCENDING, MongoClient
from pymongo.operations import SearchIndexModel
from pymongo.write_concern import WriteConcern

from . import config

_client = None


def db():
    global _client
    if not config.MONGODB_URI:
        raise SystemExit("MONGODB_URI is not set. Put it in .env.")
    if _client is None:
        _client = MongoClient(config.MONGODB_URI, serverSelectionTimeoutMS=15000, appname="govmem")
    return _client[config.MONGODB_DB]


def memories():
    return db()["memories"]


def reviews():
    return db()["reviews"]


def runs():
    # A receipt must be durable before the next tool call: majority + journal.
    return db().get_collection("runs", write_concern=WriteConcern(w="majority", j=True))


def tickets():
    return db()["tickets"]


INDEX_DEFINITION = {
    "fields": [
        {"type": "vector", "path": "embedding", "numDimensions": config.EMBED_DIMS, "similarity": "cosine"},
        {"type": "filter", "path": "namespace"},
        {"type": "filter", "path": "lifecycle"},
    ]
}


def ensure_collections():
    have = set(db().list_collection_names())
    for name in ("memories", "reviews", "runs", "tickets"):
        if name not in have:
            db().create_collection(name)
    schema = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["namespace", "lifecycle", "actor", "evidence", "symptom", "fix_steps", "source_ticket"],
            "properties": {
                "namespace": {"bsonType": "string", "minLength": 1},
                "lifecycle": {"enum": list(config.LIFECYCLES)},
                "actor": {"bsonType": "string", "minLength": 1},
                "evidence": {"bsonType": "number", "minimum": 0, "maximum": 1},
                "symptom": {"bsonType": "string"},
                "fix_steps": {"bsonType": "array", "minItems": 1},
                "source_ticket": {"bsonType": "string", "minLength": 1},
            },
        }
    }
    db().command("collMod", "memories", validator=schema, validationLevel="strict", validationAction="error")
    memories().create_index([("namespace", ASCENDING), ("lifecycle", ASCENDING)])
    runs().create_index([("run_id", ASCENDING), ("seq", ASCENDING)], unique=True)
    reviews().create_index([("status", ASCENDING)])


def index_status():
    found = list(memories().list_search_indexes(config.VECTOR_INDEX))
    return found[0] if found else None


def ensure_vector_index():
    """Create the index if missing. Returns 'exists' or 'created'. Raises if the tier refuses."""
    if index_status():
        return "exists"
    model = SearchIndexModel(definition=INDEX_DEFINITION, name=config.VECTOR_INDEX, type="vectorSearch")
    memories().create_search_index(model)
    return "created"


def wait_index_ready(timeout=300):
    start = time.time()
    while time.time() - start < timeout:
        info = index_status()
        if info and info.get("queryable") and info.get("status") == "READY":
            return info
        time.sleep(3)
    raise SystemExit("Vector index did not reach READY and queryable in %ss: %r" % (timeout, index_status()))
