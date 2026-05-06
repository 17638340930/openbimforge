import os
import sys
import traceback

# --- ENHANCED DIAGNOSTIC LOGGING ---
def log_debug(msg):
    print(f"[DEBUG] {msg}", file=sys.stderr, flush=True)

def log_error(msg, exc=None):
    print(f"[ERROR] {msg}", file=sys.stderr, flush=True)
    if exc:
        print("-" * 60, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        print("-" * 60, file=sys.stderr)

log_debug(f"Python Executable: {sys.executable}")

# Resolve project root
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# --- END DIAGNOSTIC ---

# Import the real entry point
try:
    import forge_core.build_agent.adapter_entry as core_entry
except Exception as e:
    log_error("Failed to import core adapter entry", e)
    sys.exit(1)

if __name__ == "__main__":
    try:
        sys.exit(core_entry.main())
    except Exception as e:
        log_error("Fatal error during core execution", e)
        sys.exit(1)
