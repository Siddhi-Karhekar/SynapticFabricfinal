# ==========================================
# 🔴 GLOBAL SHARED STATE (NO IMPORT LOOPS)
# ==========================================

LIVE_MACHINES = {}

# Pre-spike snapshots keyed by machine_id. Populated by POST /spike,
# consumed by maintenance handlers to revert what-if scenarios.
WHATIF_SNAPSHOTS: dict[str, dict] = {}