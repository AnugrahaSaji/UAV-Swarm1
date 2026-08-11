"""
API Routes for PQC Benchmark Dashboard.

Endpoints:
- GET /api/runs - List all benchmark runs
- GET /api/suites - List all suites with filtering
- GET /api/suite/{suite_key} - Get detailed suite metrics
- GET /api/compare - Compare two suites
- GET /api/metrics/schema - Return schema definitions
- GET /api/health - Health check
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from datetime import date, datetime
import math

try:
    import numpy as np
except Exception:  # pragma: no cover - optional dependency for safer encoding
    np = None

try:
    import pandas as pd
except Exception:  # pragma: no cover - optional dependency for safer encoding
    pd = None

try:
    from ..models import (
        ComprehensiveSuiteMetrics,
        SuiteSummary,
        RunSummary,
        ComparisonResult,
        SchemaField,
        HealthResponse,
        SuiteInventoryResponse,
    )
    from ..ingest import get_store
    from ..analysis import (
        compare_suites,
        compute_comparison_table,
        get_drone_vs_gcs_summary,
        generate_schema_definition,
        aggregate_by_kem_family,
        aggregate_by_nist_level,
        is_suite_invalid,
        filter_valid_suites,
        build_metric_inventory,
        generate_metric_semantics,
    )
except ImportError:
    from models import (
        ComprehensiveSuiteMetrics,
        SuiteSummary,
        RunSummary,
        ComparisonResult,
        SchemaField,
        HealthResponse,
        SuiteInventoryResponse,
    )
    from ingest import get_store
    from analysis import (
        compare_suites,
        compute_comparison_table,
        get_drone_vs_gcs_summary,
        generate_schema_definition,
        aggregate_by_kem_family,
        aggregate_by_nist_level,
        is_suite_invalid,
        filter_valid_suites,
        build_metric_inventory,
        generate_metric_semantics,
    )

router = APIRouter(prefix="/api", tags=["api"])


def _json_safe_value(value: Any) -> Any:
    if value is None:
        return None
    if pd is not None and pd.isna(value):
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if np is not None and isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _json_safe_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {key: _json_safe_value(value) for key, value in row.items()}
        for row in records
    ]


# =============================================================================
# HEALTH CHECK
# =============================================================================

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    try:
        store = get_store()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    valid_count = len(filter_valid_suites(list(store._suites.values())))
    return HealthResponse(
        status="ok",
        suites_loaded=valid_count,
        runs_loaded=store.run_count
    )


# =============================================================================
# RUNS
# =============================================================================

@router.get("/runs", response_model=List[RunSummary])
async def list_runs():
    """List all benchmark runs."""
    try:
        store = get_store()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return store.list_runs()


# =============================================================================
# SUITES
# =============================================================================

@router.get("/suites", response_model=List[SuiteSummary])
async def list_suites(
    kem_family: Optional[str] = Query(None, description="Filter by KEM family"),
    sig_family: Optional[str] = Query(None, description="Filter by signature family"),
    aead: Optional[str] = Query(None, description="Filter by AEAD algorithm"),
    nist_level: Optional[str] = Query(None, description="Filter by NIST level"),
    run_id: Optional[str] = Query(None, description="Filter by run ID")
):
    """List all suites with optional filtering."""
    try:
        store = get_store()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return store.list_suites(
        kem_family=kem_family,
        sig_family=sig_family,
        aead=aead,
        nist_level=nist_level,
        run_id=run_id
    )


@router.get("/suites/filters")
async def get_suite_filters():
    """Get available filter values."""
    try:
        store = get_store()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {
        "kem_families": store.get_unique_values("kem_family"),
        "sig_families": store.get_unique_values("sig_family"),
        "aead_algorithms": store.get_unique_values("aead_algorithm"),
        "nist_levels": store.get_unique_values("nist_level"),
    }


@router.get("/suite/{suite_key}", response_model=ComprehensiveSuiteMetrics)
async def get_suite(suite_key: str):
    """
    Get detailed metrics for a specific suite.
    
    suite_key can be:
    - Composite key: "run_id:suite_id"
    - Just suite_id (returns first match)
    """
    try:
        store = get_store()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    
    if ":" in suite_key:
        suite = store.get_suite_by_key(suite_key)
    else:
        suite = store.get_suite(suite_key)
    
    if suite is None:
        raise HTTPException(status_code=404, detail=f"Suite not found: {suite_key}")
    
    return suite


@router.get("/suite/{suite_key}/inventory", response_model=SuiteInventoryResponse)
async def get_suite_inventory(suite_key: str):
    """
    Get full metric inventory for a suite, including raw payloads.
    """
    try:
        store = get_store()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if ":" in suite_key:
        suite = store.get_suite_by_key(suite_key)
    else:
        suite = store.get_suite(suite_key)

    if suite is None:
        raise HTTPException(status_code=404, detail=f"Suite not found: {suite_key}")

    metrics = build_metric_inventory(suite)
    return SuiteInventoryResponse(
        suite_key=suite_key,
        metrics=metrics,
        raw={
            "drone": suite.raw_drone or {},
            "gcs": suite.raw_gcs or {},
            "gcs_validation": suite.gcs_validation or {},
        },
    )


@router.get("/suite/{suite_key}/drone-vs-gcs")
async def get_suite_drone_vs_gcs(suite_key: str):
    """Get drone vs GCS comparison for a suite."""
    try:
        store = get_store()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    
    if ":" in suite_key:
        suite = store.get_suite_by_key(suite_key)
    else:
        suite = store.get_suite(suite_key)
    
    if suite is None:
        raise HTTPException(status_code=404, detail=f"Suite not found: {suite_key}")
    
    return get_drone_vs_gcs_summary(suite)


# =============================================================================
# COMPARISON
# =============================================================================

@router.get("/compare")
async def compare_two_suites(
    suite_a: str = Query(..., description="First suite key (run_id:suite_id or suite_id)"),
    suite_b: str = Query(..., description="Second suite key (run_id:suite_id or suite_id)")
):
    """
    Compare two suites side-by-side.
    
    Returns both suite data and computed differences.
    """
    try:
        store = get_store()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    
    # Get suite A
    if ":" in suite_a:
        s_a = store.get_suite_by_key(suite_a)
    else:
        s_a = store.get_suite(suite_a)
    
    if s_a is None:
        raise HTTPException(status_code=404, detail=f"Suite A not found: {suite_a}")
    
    # Get suite B
    if ":" in suite_b:
        s_b = store.get_suite_by_key(suite_b)
    else:
        s_b = store.get_suite(suite_b)
    
    if s_b is None:
        raise HTTPException(status_code=404, detail=f"Suite B not found: {suite_b}")

    if is_suite_invalid(s_a) or is_suite_invalid(s_b):
        raise HTTPException(status_code=400, detail="One or both suites are scientifically invalid and cannot be compared")
    
    result = compare_suites(s_a, s_b)
    comparison_table = compute_comparison_table(s_a, s_b)
    
    return {
        "summary": result.model_dump(),
        "detailed_comparison": comparison_table
    }


# =============================================================================
# AGGREGATION
# =============================================================================

@router.get("/aggregate/kem-family")
async def aggregate_by_kem(
    run_id: Optional[str] = Query(None, description="Filter by run ID")
):
    """
    Aggregate metrics by KEM family.
    
    This is an explicit aggregation - data is grouped only when requested.
    """
    try:
        store = get_store()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    try:
        suites = [
            store.get_suite_by_key(key)
            for key in store._suites.keys()
            if run_id is None or key.startswith(run_id + ":")
        ]
        suites = [s for s in suites if s is not None]

        if not suites:
            return {"data": [], "warning": "No suites found"}

        df = aggregate_by_kem_family(suites)

        if df.empty:
            return {"data": [], "warning": "No aggregatable data"}

        # Convert multi-index columns to flat, JSON-friendly keys
        df = df.copy()
        if df.index.name:
            df.index.name = df.index.name.replace(".", "_")
        df.columns = [
            "_".join([str(part).replace(".", "_") for part in col]) if isinstance(col, tuple) else str(col)
            for col in df.columns
        ]
        result = df.reset_index().to_dict(orient="records")
        return {"data": _json_safe_records(result)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"aggregate_kem_family_failed: {exc}")


@router.get("/aggregate/nist-level")
async def aggregate_by_nist(
    run_id: Optional[str] = Query(None, description="Filter by run ID")
):
    """
    Aggregate metrics by NIST security level.
    
    This is an explicit aggregation - data is grouped only when requested.
    """
    try:
        store = get_store()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    try:
        suites = [
            store.get_suite_by_key(key)
            for key in store._suites.keys()
            if run_id is None or key.startswith(run_id + ":")
        ]
        suites = [s for s in suites if s is not None]

        if not suites:
            return {"data": [], "warning": "No suites found"}

        df = aggregate_by_nist_level(suites)

        if df.empty:
            return {"data": [], "warning": "No aggregatable data"}

        df = df.copy()
        if df.index.name:
            df.index.name = df.index.name.replace(".", "_")
        df.columns = [
            "_".join([str(part).replace(".", "_") for part in col]) if isinstance(col, tuple) else str(col)
            for col in df.columns
        ]
        result = df.reset_index().to_dict(orient="records")
        return {"data": _json_safe_records(result)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"aggregate_nist_level_failed: {exc}")


# =============================================================================
# SCHEMA
# =============================================================================

@router.get("/metrics/schema", response_model=List[SchemaField])
async def get_schema():
    """Get schema field definitions with reliability classification."""
    return generate_schema_definition()


@router.get("/metrics/semantics")
async def get_metric_semantics():
    """Get generated metric semantics for schema + legacy metrics."""
    return generate_metric_semantics()


@router.get("/metrics/load-errors")
async def get_load_errors():
    """Get any errors encountered during data loading."""
    try:
        store = get_store()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {
        "errors": [
            {"file": f, "line": l, "error": e}
            for f, l, e in store.load_errors
        ],
        "count": len(store.load_errors)
    }


# =============================================================================
# COMPARISON BUCKETS
# =============================================================================

# NIST level ordering for sorting
NIST_ORDER = {"L1": 1, "L3": 2, "L5": 3, "": 99}

def _nist_sort_key(suite_summary):
    """Sort key for NIST level ordering."""
    level = suite_summary.suite_security_level
    return (NIST_ORDER.get(level, 99), suite_summary.suite_id)


@router.get("/buckets")
async def get_comparison_buckets(
    run_id: Optional[str] = Query(None, description="Filter by run ID")
):
    """
    Get predefined comparison bucket groupings.
    
    Returns suites grouped by:
    - NIST security level (L1, L3, L5)
    - NIST level + AEAD combination
    - AEAD algorithm only
    - KEM family (sorted by NIST level within family)
    - SIG family (sorted by NIST level within family)
    
    All buckets contain suite keys in format "run_id:suite_id".
    """
    try:
        store = get_store()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    suites = store.list_suites(run_id=run_id)
    
    # Initialize bucket structures
    buckets = {
        "nist_level": {},
        "nist_aead": {},
        "aead": {},
        "kem_family": {},
        "sig_family": {}
    }
    
    for s in suites:
        key = f"{s.run_id}:{s.suite_id}"
        nist = s.suite_security_level or "Unknown"
        aead = s.aead_algorithm or "Unknown"
        
        # Extract KEM family from algorithm name
        kem_alg = s.kem_algorithm or ""
        if "ML-KEM" in kem_alg or "mlkem" in kem_alg.lower():
            kem_family = "ML-KEM"
        elif "HQC" in kem_alg or "hqc" in kem_alg.lower():
            kem_family = "HQC"
        elif "McEliece" in kem_alg or "mceliece" in kem_alg.lower():
            kem_family = "ClassicMcEliece"
        else:
            kem_family = "Other"
        
        # Extract SIG family from algorithm name
        sig_alg = s.sig_algorithm or ""
        if "ML-DSA" in sig_alg or "mldsa" in sig_alg.lower():
            sig_family = "ML-DSA"
        elif "Falcon" in sig_alg or "falcon" in sig_alg.lower():
            sig_family = "Falcon"
        elif "SPHINCS" in sig_alg or "sphincs" in sig_alg.lower():
            sig_family = "SPHINCS+"
        else:
            sig_family = "Other"
        
        # Populate buckets
        # 1. NIST level
        if nist not in buckets["nist_level"]:
            buckets["nist_level"][nist] = []
        buckets["nist_level"][nist].append({"key": key, "suite": s})
        
        # 2. NIST + AEAD
        nist_aead_key = f"{nist}-{aead}"
        if nist_aead_key not in buckets["nist_aead"]:
            buckets["nist_aead"][nist_aead_key] = []
        buckets["nist_aead"][nist_aead_key].append({"key": key, "suite": s})
        
        # 3. AEAD only
        if aead not in buckets["aead"]:
            buckets["aead"][aead] = []
        buckets["aead"][aead].append({"key": key, "suite": s})
        
        # 4. KEM family
        if kem_family not in buckets["kem_family"]:
            buckets["kem_family"][kem_family] = []
        buckets["kem_family"][kem_family].append({"key": key, "suite": s})
        
        # 5. SIG family
        if sig_family not in buckets["sig_family"]:
            buckets["sig_family"][sig_family] = []
        buckets["sig_family"][sig_family].append({"key": key, "suite": s})
    
    # Sort and convert to final format
    result = {
        "nist_level": {},
        "nist_aead": {},
        "aead": {},
        "kem_family": {},
        "sig_family": {}
    }
    
    # Sort NIST levels by order
    for level in sorted(buckets["nist_level"].keys(), key=lambda x: NIST_ORDER.get(x, 99)):
        items = buckets["nist_level"][level]
        items.sort(key=lambda x: _nist_sort_key(x["suite"]))
        result["nist_level"][level] = [
            {"key": item["key"], "suite_id": item["suite"].suite_id, 
             "kem": item["suite"].kem_algorithm, "sig": item["suite"].sig_algorithm,
             "aead": item["suite"].aead_algorithm, "nist": item["suite"].suite_security_level,
             "handshake_ms": item["suite"].handshake_total_duration_ms,
             "power_w": item["suite"].power_avg_w, "energy_j": item["suite"].energy_total_j}
            for item in items
        ]
    
    # Sort NIST+AEAD combinations
    for combo in sorted(buckets["nist_aead"].keys()):
        items = buckets["nist_aead"][combo]
        items.sort(key=lambda x: _nist_sort_key(x["suite"]))
        result["nist_aead"][combo] = [
            {"key": item["key"], "suite_id": item["suite"].suite_id,
             "kem": item["suite"].kem_algorithm, "sig": item["suite"].sig_algorithm,
             "handshake_ms": item["suite"].handshake_total_duration_ms,
             "power_w": item["suite"].power_avg_w, "energy_j": item["suite"].energy_total_j}
            for item in items
        ]
    
    # Sort AEAD alphabetically
    for aead in sorted(buckets["aead"].keys()):
        items = buckets["aead"][aead]
        items.sort(key=lambda x: _nist_sort_key(x["suite"]))
        result["aead"][aead] = [
            {"key": item["key"], "suite_id": item["suite"].suite_id,
             "kem": item["suite"].kem_algorithm, "sig": item["suite"].sig_algorithm,
             "nist": item["suite"].suite_security_level,
             "handshake_ms": item["suite"].handshake_total_duration_ms,
             "power_w": item["suite"].power_avg_w, "energy_j": item["suite"].energy_total_j}
            for item in items
        ]
    
    # Sort KEM families, then by NIST level within
    for family in sorted(buckets["kem_family"].keys()):
        items = buckets["kem_family"][family]
        items.sort(key=lambda x: _nist_sort_key(x["suite"]))
        result["kem_family"][family] = [
            {"key": item["key"], "suite_id": item["suite"].suite_id,
             "kem": item["suite"].kem_algorithm, "sig": item["suite"].sig_algorithm,
             "aead": item["suite"].aead_algorithm, "nist": item["suite"].suite_security_level,
             "handshake_ms": item["suite"].handshake_total_duration_ms,
             "power_w": item["suite"].power_avg_w, "energy_j": item["suite"].energy_total_j}
            for item in items
        ]
    
    # Sort SIG families, then by NIST level within
    for family in sorted(buckets["sig_family"].keys()):
        items = buckets["sig_family"][family]
        items.sort(key=lambda x: _nist_sort_key(x["suite"]))
        result["sig_family"][family] = [
            {"key": item["key"], "suite_id": item["suite"].suite_id,
             "kem": item["suite"].kem_algorithm, "sig": item["suite"].sig_algorithm,
             "aead": item["suite"].aead_algorithm, "nist": item["suite"].suite_security_level,
             "handshake_ms": item["suite"].handshake_total_duration_ms,
             "power_w": item["suite"].power_avg_w, "energy_j": item["suite"].energy_total_j}
            for item in items
        ]
    
    return result

