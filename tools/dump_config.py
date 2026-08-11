import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import CONFIG
import json

print("=== LOADED CONFIG DUMP ===")
dump = {
    "GCS_HOST": CONFIG.get("GCS_HOST"),
    "DRONE_HOST": CONFIG.get("DRONE_HOST"),
    "DRONE_HOSTS": CONFIG.get("DRONE_HOSTS"),
    "DRONE_HOST_ALLOWLIST": CONFIG.get("DRONE_HOST_ALLOWLIST"),
    "GCS_CONTROL_PORT": CONFIG.get("GCS_CONTROL_PORT"),
    "DRONE_PSK_LEN": len(CONFIG.get("DRONE_PSK", "")),
    "GCS_CONTROL_HOST": CONFIG.get("GCS_CONTROL_HOST"),
    "ALLOW_NON_LOOPBACK": CONFIG.get("ALLOW_NON_LOOPBACK_PLAINTEXT"),
    "ENV": CONFIG.get("ENV", "unknown")
}
print(json.dumps(dump, indent=2))
