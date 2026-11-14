"""Every threshold and name lives here. Nothing else in the code holds a magic number."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MONGODB_URI = os.environ.get("MONGODB_URI", "")
MONGODB_DB = os.environ.get("MONGODB_DB", "govmem")
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY", "")

EMBED_MODEL = "voyage-3"
EMBED_DIMS = 1024
VECTOR_INDEX = "memories_vec"

# Decision thresholds. Changing any of these is the owner's decision.
FAST_SIM = 0.77        # fast path: raw cosine at least this ...
FAST_EVIDENCE = 0.80   # ... and evidence at least this
TRUST_SIM = 0.55       # trusted recall band
TRUST_EVIDENCE = 0.60
VETO_SIM = 0.30        # veto: similarity at least this ...
VETO_EVIDENCE = 0.50   # ... and evidence below this
HOLD_CONFIDENCE = 0.70  # hold for a human below this
PROBE_ABORT_SIM = 0.75  # Stage 1 abort line for repeat tickets

PROMOTED_EVIDENCE = 0.85   # evidence set when a human promotes a candidate
CANDIDATE_EVIDENCE = 0.40  # evidence of a candidate before review

LIFECYCLES = ("candidate", "active", "superseded", "retired")
