#!/usr/bin/env python3
"""Quick probe to discover actual APIs on Pi."""
import sys, os, json
sys.path.insert(0, os.path.expanduser("~/secure-tunnel"))

results = {}

# 1. oqs API
try:
    import oqs
    results["oqs_dir"] = [x for x in dir(oqs) if not x.startswith("_")]
    # Try submodules
    try:
        from oqs import oqs as oqs_inner
        results["oqs_inner_dir"] = [x for x in dir(oqs_inner) if not x.startswith("_")]
    except:
        results["oqs_inner_dir"] = "no oqs.oqs"
    # Try KeyEncapsulation
    try:
        from oqs import KeyEncapsulation
        results["KE_class"] = str(KeyEncapsulation)
    except:
        try:
            from oqs.oqs import KeyEncapsulation
            results["KE_class"] = "oqs.oqs.KeyEncapsulation"
        except:
            results["KE_class"] = "NOT FOUND"
    # list KEMs
    try:
        kems = oqs.get_enabled_KEM_mechanisms()
        results["kems_count"] = len(kems)
    except:
        try:
            from oqs.oqs import get_enabled_KEM_mechanisms
            kems = get_enabled_KEM_mechanisms()
            results["kems_count_inner"] = len(kems)
        except Exception as e:
            results["kems_err"] = str(e)
except Exception as e:
    results["oqs_import_err"] = str(e)

# 2. INA219 / PowerMonitor API
try:
    from core.power_monitor import Ina219PowerMonitor
    import inspect
    sig = inspect.signature(Ina219PowerMonitor.__init__)
    results["ina219_params"] = str(sig)
except Exception as e:
    results["ina219_err"] = str(e)

# 3. SUITES structure
try:
    from core.suites import SUITES
    results["suites_type"] = str(type(SUITES))
    results["suites_len"] = len(SUITES)
    if isinstance(SUITES, dict):
        first_key = list(SUITES.keys())[0]
        first_val = SUITES[first_key]
        results["first_key"] = first_key
        results["first_val_type"] = str(type(first_val))
        results["first_val_dir"] = [x for x in dir(first_val) if not x.startswith("_")] if not isinstance(first_val, (str, dict)) else str(first_val)[:200]
    elif isinstance(SUITES, (list, tuple)):
        first = SUITES[0]
        results["first_type"] = str(type(first))
        results["first_dir"] = [x for x in dir(first) if not x.startswith("_")] if not isinstance(first, (str, dict)) else str(first)[:200]
except Exception as e:
    results["suites_err"] = str(e)

# 4. pathlib check
try:
    from pathlib import Path
    p = Path("/tmp/test_probe")
    p.mkdir(exist_ok=True)
    results["pathlib"] = "ok"
except Exception as e:
    results["pathlib_err"] = str(e)

print(json.dumps(results, indent=2))
