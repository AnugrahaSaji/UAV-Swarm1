import ast
from pathlib import Path

root = Path("C:/Users/burak/ptojects/secure-tunnel")
py_files = [p for p in root.rglob("*.py")]

keywords = {
    "network": ["socket", "requests", "urllib", "http", "asyncio", "selectors", "zmq", "grpc", "pymavlink", "mavutil"],
    "crypto": ["cryptography", "oqs", "hashlib", "hmac", "AESGCM", "ChaCha20Poly1305", "pyascon", "ascon"],
    "timing": ["time", "perf_counter", "perf_counter_ns", "monotonic"],
    "logging": ["logging", "get_logger"],
    "benchmark": ["benchmark", "metrics", "perf", "ina219", "power"],
    "mavlink": ["pymavlink", "mavutil", "MAVProxy", "mavproxy"],
}


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
    uses_cli = False

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
    uses_cli = uses_argparse or "click" in lower_text or "typer" in lower_text

    feature_hits = {}
    for k, keys in keywords.items():
        hits = [kw for kw in keys if kw.lower() in lower_text]
        if hits:
            feature_hits[k] = hits

    summary = (module_doc or "").strip().splitlines()[0] if module_doc else ""

    return {
        "path": rel,
        "summary": summary,
        "imports": sorted(set(imports)),
        "classes": sorted(set(classes)),
        "functions": sorted(set(functions)),
        "has_main": has_main,
        "uses_cli": uses_cli,
        "uses_env": uses_env,
        "uses_json": uses_json,
        "uses_yaml": uses_yaml,
        "features": feature_hits,
    }

records = [analyze_file(p) for p in py_files]

out_path = root / "text-files" / "_python_inventory.md"
lines = []
lines.append(f"# Python Inventory ({len(records)} files)\n\n")
for rec in sorted(records, key=lambda r: r["path"]):
    lines.append(f"## {rec['path']}\n\n")
    if rec['summary']:
        lines.append(f"Summary: {rec['summary']}\n\n")
    lines.append(f"Has __main__: {rec['has_main']}\n\n")
    lines.append(f"CLI: {rec['uses_cli']} | Env: {rec['uses_env']} | JSON: {rec['uses_json']} | YAML: {rec['uses_yaml']}\n\n")
    lines.append("Imports:\n")
    if rec['imports']:
        lines.append("- " + "\n- ".join(rec['imports']) + "\n\n")
    else:
        lines.append("- (none)\n\n")
    lines.append("Classes:\n")
    if rec['classes']:
        lines.append("- " + "\n- ".join(rec['classes']) + "\n\n")
    else:
        lines.append("- (none)\n\n")
    lines.append("Functions:\n")
    if rec['functions']:
        lines.append("- " + "\n- ".join(rec['functions']) + "\n\n")
    else:
        lines.append("- (none)\n\n")
    lines.append("Feature flags:\n")
    if rec['features']:
        for k, hits in rec['features'].items():
            lines.append(f"- {k}: {', '.join(sorted(set(hits)))}\n")
        lines.append("\n")
    else:
        lines.append("- (none)\n\n")

out_path.write_text("".join(lines), encoding="utf-8")
print(out_path)
