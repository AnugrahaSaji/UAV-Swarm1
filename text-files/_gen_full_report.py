import ast
from pathlib import Path
import re

root = Path("C:/Users/burak/ptojects/secure-tunnel")
py_files = [p for p in root.rglob("*.py")]

NETWORK_KEYS = ["socket", "selectors", "asyncio", "requests", "urllib", "http", "grpc", "zmq", "pymavlink", "mavutil", "serial"]
CRYPTO_KEYS = ["cryptography", "oqs", "hashlib", "hmac", "AESGCM", "ChaCha20Poly1305", "pyascon", "ascon", "HKDF"]
TIMING_KEYS = ["time", "perf_counter", "perf_counter_ns", "monotonic", "sleep", "datetime"]
LOGGING_KEYS = ["logging", "get_logger", "logger", "log("]
BENCH_KEYS = ["benchmark", "metrics", "perf", "ina219", "power", "throughput", "latency", "jitter"]

ROLE_KEYS = {
    "gcs": ["gcs", "ground", "control station"],
    "drone": ["drone", "uav", "uavpi"],
}


def _detect_keys(text, keys):
    text_lower = text.lower()
    hits = []
    for k in keys:
        if k.lower() in text_lower:
            hits.append(k)
    return sorted(set(hits))


def analyze_file(path: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    rel = path.relative_to(root).as_posix()

    module_doc = None
    try:
        module_doc = ast.get_docstring(ast.parse(text))
    except Exception:
        module_doc = None

    try:
        tree = ast.parse(text)
    except Exception:
        tree = None

    imports = []
    classes = []
    functions = []
    has_main = False
    uses_argparse = False
    uses_env = False
    uses_json = False
    uses_yaml = False
    uses_config = False
    uses_settings = False

    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                imports.append(mod)
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, ast.FunctionDef):
                functions.append(node.name)
            elif isinstance(node, ast.If):
                try:
                    if (
                        isinstance(node.test, ast.Compare)
                        and isinstance(node.test.left, ast.Name)
                        and node.test.left.id == "__name__"
                    ):
                        for cmp in node.test.comparators:
                            if isinstance(cmp, ast.Constant) and cmp.value == "__main__":
                                has_main = True
                except Exception:
                    pass

    lower_text = text.lower()
    uses_argparse = "argparse" in lower_text
    uses_env = "os.environ" in lower_text or "getenv" in lower_text
    uses_json = "json." in lower_text
    uses_yaml = "yaml" in lower_text
    uses_config = "config" in lower_text and "core.config" in lower_text
    uses_settings = "settings.json" in lower_text

    network_hits = _detect_keys(text, NETWORK_KEYS)
    crypto_hits = _detect_keys(text, CRYPTO_KEYS)
    timing_hits = _detect_keys(text, TIMING_KEYS)
    logging_hits = _detect_keys(text, LOGGING_KEYS)
    bench_hits = _detect_keys(text, BENCH_KEYS)

    role_hints = []
    for role, keys in ROLE_KEYS.items():
        if any(k in lower_text for k in keys):
            role_hints.append(role)

    summary = (module_doc or "").strip().splitlines()[0] if module_doc else ""

    return {
        "path": rel,
        "summary": summary,
        "imports": sorted(set(imports)),
        "classes": sorted(set(classes)),
        "functions": sorted(set(functions)),
        "has_main": has_main,
        "uses_argparse": uses_argparse,
        "uses_env": uses_env,
        "uses_json": uses_json,
        "uses_yaml": uses_yaml,
        "uses_config": uses_config,
        "uses_settings": uses_settings,
        "network_hits": network_hits,
        "crypto_hits": crypto_hits,
        "timing_hits": timing_hits,
        "logging_hits": logging_hits,
        "bench_hits": bench_hits,
        "role_hints": sorted(set(role_hints)),
    }

records = [analyze_file(p) for p in py_files]

out_path = root / "text-files" / "full_analysis.md"
lines = []
lines.append(f"# Full Python File Analysis ({len(records)} files)\n\n")
lines.append("This report is generated from static code inspection. Any item not observed in code is marked as 'Not Found In Code'.\n\n")

for rec in sorted(records, key=lambda r: r["path"]):
    lines.append(f"## {rec['path']}\n\n")
    lines.append(f"Summary: {rec['summary'] or 'Not Found In Code'}\n\n")

    # Imports
    lines.append("Imports:\n")
    if rec['imports']:
        lines.append("- " + "\n- ".join(rec['imports']) + "\n\n")
    else:
        lines.append("- Not Found In Code\n\n")

    # Entry points
    entry = "__main__ guard" if rec['has_main'] else "Not Found In Code"
    cli = "argparse/CLI" if rec['uses_argparse'] else "Not Found In Code"
    lines.append("Entry Points:\n")
    lines.append(f"- Main Guard: {entry}\n")
    lines.append(f"- CLI: {cli}\n\n")

    # Config & Inputs
    lines.append("Config & Input Sources:\n")
    lines.append(f"- CONFIG usage: {'Yes' if rec['uses_config'] else 'Not Found In Code'}\n")
    lines.append(f"- Env vars: {'Yes' if rec['uses_env'] else 'Not Found In Code'}\n")
    lines.append(f"- JSON: {'Yes' if rec['uses_json'] else 'Not Found In Code'}\n")
    lines.append(f"- YAML: {'Yes' if rec['uses_yaml'] else 'Not Found In Code'}\n")
    lines.append(f"- settings.json: {'Yes' if rec['uses_settings'] else 'Not Found In Code'}\n\n")

    # Classes & functions
    lines.append("Classes:\n")
    if rec['classes']:
        lines.append("- " + "\n- ".join(rec['classes']) + "\n\n")
    else:
        lines.append("- Not Found In Code\n\n")
    lines.append("Core Functions:\n")
    if rec['functions']:
        lines.append("- " + "\n- ".join(rec['functions']) + "\n\n")
    else:
        lines.append("- Not Found In Code\n\n")

    # I/O and security
    lines.append("Network I/O:\n")
    lines.append(f"- {'; '.join(rec['network_hits']) if rec['network_hits'] else 'Not Found In Code'}\n\n")
    lines.append("Crypto Usage:\n")
    lines.append(f"- {'; '.join(rec['crypto_hits']) if rec['crypto_hits'] else 'Not Found In Code'}\n\n")

    # Timing/logging/benchmark hooks
    lines.append("Timing/Logging/Benchmarking Hooks:\n")
    lines.append(f"- Timing: {'; '.join(rec['timing_hits']) if rec['timing_hits'] else 'Not Found In Code'}\n")
    lines.append(f"- Logging: {'; '.join(rec['logging_hits']) if rec['logging_hits'] else 'Not Found In Code'}\n")
    lines.append(f"- Benchmark: {'; '.join(rec['bench_hits']) if rec['bench_hits'] else 'Not Found In Code'}\n\n")

    # Role hints
    lines.append("Role Hints (from identifiers):\n")
    lines.append(f"- {', '.join(rec['role_hints']) if rec['role_hints'] else 'Not Found In Code'}\n\n")

out_path.write_text("".join(lines), encoding="utf-8")
print(out_path)
