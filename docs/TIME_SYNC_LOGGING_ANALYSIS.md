# Time Synchronization & Logging Analysis
## sdrone_bench.py and sgcs_bench.py

---

## 1. Current Issues Identified

### 1.1 Log Directory Mismatch

**Problem**: GCS and Drone create separate log directories with different timestamps.

```python
# sdrone_bench.py (line 68)
_TS = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
LOGS_DIR = ROOT / "logs" / "benchmarks" / f"live_run_{_TS}"

# sgcs_bench.py (line 76)
_TS = time.strftime("%Y%m%d_%H%M%S")
LOGS_DIR = ROOT / "logs" / "benchmarks" / f"live_run_{_TS}"
```

**Impact**: 
- Files end up in different directories (`live_run_20260205_145749` vs `live_run_20260205_145751`)
- Makes consolidation difficult
- 27/72 comprehensive files were lost because they couldn't be matched

**Solution**: 
- Drone generates run_id and sends it to GCS in `start_proxy` command
- GCS uses the same run_id for its log directory
- Already partially implemented (run_id passed in command) but LOGS_DIR is set at module load time

### 1.2 Clock Synchronization

**Current Implementation**:
```python
# sdrone_bench.py (lines 354-367)
try:
    t1 = time.time()
    resp = send_gcs_command("chronos_sync", t1=t1)
    t4 = time.time()
    if resp.get("status") == "ok":
        offset = self.clock_sync.update_from_rpc(t1, t4, resp)
        log(f"Clock sync offset (gcs-drone): {offset:.6f}s")
        if self.metrics_aggregator:
            self.metrics_aggregator.set_clock_offset(offset, method="chronos")
```

**Issues**:
1. **Single sync at startup**: Only synced once, drift accumulates over 2+ hour runs
2. **No continuous tracking**: Offset could drift by 100+ ms over a long run
3. **Not stored in each suite**: Metrics don't include current offset at time of collection
4. **No drift estimation**: Can't compensate for clock drift rate

**Solution**:
- Re-sync every N suites (e.g., every 10 suites or 20 minutes)
- Record sync offset in each comprehensive metrics file
- Track drift rate for interpolation between syncs

### 1.3 Metrics Saving Strategy

**Current Strategy** (metrics_aggregator.py):
```python
def save_suite_metrics(self, metrics: ComprehensiveSuiteMetrics = None) -> Optional[str]:
    # ... build filename ...
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
```

**Problems**:
1. **All-or-nothing write**: If save fails, ALL metrics for that suite are lost
2. **No incremental updates**: Can't recover partial data
3. **No retry logic**: Single attempt, no error recovery
4. **No fsync**: Data may not be persisted to disk before crash

**Evidence of failures** (from previous run):
- 72 suites tested, only 45 comprehensive files saved
- 27 files lost due to save failures (likely file I/O issues)

**Solution** (implemented in RobustLogger):
1. Append-mode logging (JSONL files, incremental)
2. Atomic writes (temp file → rename)
3. Retry with exponential backoff
4. fsync after writes

### 1.4 Inconsistent Timestamp Formats

**Problem**: Different timestamp formats used across files:

```python
# sdrone_bench.py
datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")  # UTC
time.strftime("%Y%m%d-%H%M%S")  # Local time!

# sgcs_bench.py  
time.strftime("%Y%m%d-%H%M%S")  # Local time!
datetime.now().strftime('%Y%m%d_%H%M%S')  # Local time!
```

**Impact**: Inconsistent file naming, correlation issues between GCS/Drone files

**Solution**: Always use UTC with consistent format:
```python
datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
```

---

## 2. Time Synchronization Deep Dive

### 2.1 Chronos Sync Protocol

The current implementation uses a simple NTP-like 4-timestamp protocol:

```
Drone                           GCS
  |                              |
  | -------- t1: request ------> |
  |                              | t2: receive
  |                              | t3: respond
  | <------- t4: receive ------- |
  |                              |

offset = ((t2 - t1) + (t3 - t4)) / 2
RTT = (t4 - t1) - (t3 - t2)
```

### 2.2 Implementation in clock_sync.py

```python
class ClockSync:
    def update_from_rpc(self, t1: float, t4: float, resp: Dict) -> float:
        t2 = resp.get("t2")
        t3 = resp.get("t3")
        offset = ((t2 - t1) + (t3 - t4)) / 2
        self._offset = offset
        return offset
```

### 2.3 Proposed Improvements

1. **Periodic Re-sync**:
   ```python
   SYNC_INTERVAL_SUITES = 10  # Re-sync every 10 suites
   SYNC_INTERVAL_SECONDS = 1200  # Or every 20 minutes
   
   def should_resync(self) -> bool:
       suites_since = self._suite_count - self._last_sync_suite
       time_since = time.monotonic() - self._last_sync_mono
       return suites_since >= SYNC_INTERVAL_SUITES or time_since >= SYNC_INTERVAL_SECONDS
   ```

2. **Drift Tracking**:
   ```python
   def estimate_drift(self, samples: List[Tuple[float, float]]) -> float:
       """Estimate drift in ms/hour from sync samples (mono_time, offset_ms)."""
       # Linear regression
       ...
       return drift_ms_per_hour
   ```

3. **Interpolated Offset**:
   ```python
   def get_current_offset(self) -> float:
       """Get interpolated offset accounting for drift."""
       elapsed = time.monotonic() - self._last_sync_mono
       drift_correction = elapsed * self._drift_rate
       return self._last_offset + drift_correction
   ```

---

## 3. Logging Strategy Improvements

### 3.1 New File Structure

```
logs/benchmarks/live_run_20260205_145749/
├── events_drone.jsonl          # Append-mode event log
├── events_gcs.jsonl            # Append-mode event log
├── metrics_drone.jsonl         # Incremental metrics (per-category)
├── metrics_gcs.jsonl           # Incremental metrics (per-category)
├── sync_status.json            # Current sync state (atomic update)
├── suite_progress_drone.json   # Current suite progress
├── suite_progress_gcs.json     # Current suite progress
├── all_suites_drone.jsonl      # Combined suite summaries (append)
├── all_suites_gcs.jsonl        # Combined suite summaries (append)
├── suite_cs-mlkem512-*.json    # Individual suite files (atomic)
├── comprehensive/              # Legacy format for compatibility
│   └── *.json
└── logs/                       # Process logs
    └── *.log
```

### 3.2 Incremental Metrics Format (metrics_*.jsonl)

```json
{"timestamp_utc": "2026-02-05T15:01:23.456Z", "suite_id": "cs-mlkem512-aesgcm-falcon512", "category": "handshake", "metrics": {"handshake_ms": 12.5, "rekey_ms": 11.2}}
{"timestamp_utc": "2026-02-05T15:01:24.789Z", "suite_id": "cs-mlkem512-aesgcm-falcon512", "category": "data_plane", "metrics": {"packets_sent": 1000, "packets_received": 998}}
{"timestamp_utc": "2026-02-05T15:01:25.012Z", "suite_id": "cs-mlkem512-aesgcm-falcon512", "category": "mavlink", "metrics": {"total_msgs": 500, "heartbeat_count": 50}}
```

**Recovery**: If suite finalization fails, metrics can be reconstructed from JSONL

### 3.3 Event Log Format (events_*.jsonl)

```json
{"timestamp_utc": "2026-02-05T15:00:00.000Z", "timestamp_mono": 12345.678, "event_type": "logger_started", "suite_id": null, "data": {"role": "drone", "run_id": "20260205_145749"}, "role": "drone", "run_id": "20260205_145749", "sequence": 1}
{"timestamp_utc": "2026-02-05T15:01:00.000Z", "timestamp_mono": 12405.678, "event_type": "suite_started", "suite_id": "cs-mlkem512-aesgcm-falcon512", "data": {"config": {...}}, "role": "drone", "run_id": "20260205_145749", "sequence": 2}
```

---

## 4. Integration Plan

### 4.1 sdrone_bench.py Changes

1. **Import RobustLogger**:
   ```python
   from core.robust_logger import RobustLogger, SyncTracker, coordinate_run_id
   ```

2. **Initialize at BenchmarkScheduler.__init__**:
   ```python
   self.sync_tracker = SyncTracker()
   self.robust_logger = RobustLogger(
       run_id=self.policy.run_id,
       role="drone",
       base_dir=ROOT / "logs" / "benchmarks",
       sync_tracker=self.sync_tracker,
   )
   ```

3. **Record sync in run()**:
   ```python
   if resp.get("status") == "ok":
       offset = self.clock_sync.update_from_rpc(t1, t4, resp)
       self.sync_tracker.record_sync(offset * 1000.0, method="chronos")  # Convert to ms
       self.robust_logger.record_sync(offset * 1000.0, method="chronos")
   ```

4. **Start/end suite**:
   ```python
   def _activate_suite(self, suite_name: str) -> bool:
       self.robust_logger.start_suite(suite_name, suite_config)
       # ... existing code ...
       self.robust_logger.log_metrics_incremental("handshake", {
           "handshake_ms": handshake_ms,
           "rekey_ms": metrics.get("rekey_ms", 0),
       })
   
   def _finalize_metrics(self, success: bool, error: str = "", gcs_metrics: Dict = None):
       # ... existing code ...
       self.robust_logger.log_metrics_incremental("data_plane", counters)
       self.robust_logger.end_suite(success, error)
   ```

5. **Periodic re-sync**:
   ```python
   if self.policy.current_index % 10 == 0:  # Every 10 suites
       self._perform_clock_sync()
   ```

### 4.2 sgcs_bench.py Changes

1. **Use drone's run_id**:
   ```python
   # In start_proxy handler:
   run_id = request.get("run_id") or self.run_id
   if run_id != self.run_id:
       # Update log directory to match drone
       self._update_log_dir(run_id)
   ```

2. **Initialize RobustLogger**:
   ```python
   self.robust_logger = RobustLogger(
       run_id=run_id,
       role="gcs",
       base_dir=ROOT / "logs" / "benchmarks",
       sync_tracker=self.sync_tracker,
   )
   ```

3. **Log metrics incrementally** in `stop_suite` handler.

---

## 5. Summary of Fixes

| Issue | Current Behavior | Fix |
|-------|------------------|-----|
| Log directory mismatch | GCS/Drone use different timestamps | Share run_id from drone |
| Single clock sync | Once at startup | Re-sync every 10 suites |
| All-or-nothing saves | Lost 27/72 files | Append-mode JSONL |
| No retry logic | Single attempt | 3 retries with backoff |
| No fsync | Data may be lost | fsync after each write |
| Inconsistent timestamps | Local vs UTC mixed | Always UTC ISO format |
| No drift tracking | Offset accumulates error | Linear regression drift model |

---

## 6. Testing

After integration, validate with:

1. **Short run (5 suites)**: Verify all files created correctly
2. **Simulated failure**: Kill process mid-suite, verify recovery from JSONL
3. **Long run (72 suites)**: Verify no missing files
4. **Clock drift test**: Compare sync offsets over 2+ hour run
