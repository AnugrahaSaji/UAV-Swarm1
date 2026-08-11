#!/usr/bin/env python3
"""
Robust Logger with Aggressive Append-Mode Logging
core/robust_logger.py

Features:
1. Append-mode logging (no data loss on failure)
2. Atomic file writes with temp files
3. Incremental metric updates with timestamps
4. Automatic retry on failures
5. Sync status tracking between GCS and Drone
6. Recovery from partial failures

Usage:
    from core.robust_logger import RobustLogger, SyncTracker
    
    logger = RobustLogger(run_id="20260205_145749", role="drone", base_dir=Path("logs"))
    logger.log_event("suite_started", {"suite_id": "cs-mlkem512-falcon512"})
    logger.log_metrics_incremental("handshake", {"handshake_ms": 12.5})
    logger.flush()  # Force write to disk
"""

import os
import sys
import json
import time
import shutil
import threading
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List, Callable
from contextlib import contextmanager

# Windows doesn't have fcntl, use msvcrt instead
if sys.platform == 'win32':
    import msvcrt
    
    @contextmanager
    def file_lock(f):
        """Windows file locking."""
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            yield
        finally:
            try:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception:
                pass
else:
    import fcntl
    
    @contextmanager
    def file_lock(f):
        """Unix file locking."""
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass


@dataclass
class LogEntry:
    """Single log entry with timestamp and metadata."""
    timestamp_utc: str
    timestamp_mono: float
    event_type: str
    suite_id: Optional[str]
    data: Dict[str, Any]
    role: str
    run_id: str
    sequence: int = 0


@dataclass
class SyncStatus:
    """Tracks synchronization status between GCS and Drone."""
    clock_offset_ms: float = 0.0
    clock_sync_method: str = "unknown"
    last_sync_utc: str = ""
    drift_estimate_ms_per_hour: float = 0.0
    sync_count: int = 0
    sync_history: List[Dict[str, Any]] = field(default_factory=list)


class RobustLogger:
    """
    Robust logger with append-mode, atomic writes, and failure recovery.
    """
    
    MAX_BUFFER_SIZE = 50  # Flush after this many entries
    MAX_BUFFER_AGE_S = 10.0  # Flush after this many seconds
    MAX_RETRIES = 3
    RETRY_DELAY_S = 0.5
    MAX_SYNC_HISTORY = 20  # Keep last N sync records
    
    def __init__(
        self,
        run_id: str,
        role: str,
        base_dir: Path,
        sync_tracker: "SyncTracker" = None,
    ):
        """
        Initialize robust logger.
        
        Args:
            run_id: Unique run identifier (shared between GCS and Drone)
            role: "gcs" or "drone"
            base_dir: Base directory for logs
        """
        self.run_id = run_id
        self.role = role
        self.base_dir = Path(base_dir)
        self.sync_tracker = sync_tracker or SyncTracker()
        
        # Ensure directory exists
        self.log_dir = self.base_dir / f"live_run_{run_id}"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # File paths
        self.events_file = self.log_dir / f"events_{role}.jsonl"
        self.metrics_file = self.log_dir / f"metrics_{role}.jsonl"
        self.sync_file = self.log_dir / "sync_status.json"
        self.suite_progress_file = self.log_dir / f"suite_progress_{role}.json"
        
        # Buffer for batched writes
        self._buffer: List[LogEntry] = []
        self._buffer_lock = threading.Lock()
        self._last_flush = time.monotonic()
        self._sequence = 0
        
        # Suite tracking
        self._current_suite: Optional[str] = None
        self._suite_metrics: Dict[str, Any] = {}
        self._suite_start_mono: float = 0.0
        
        # Background flush thread
        self._running = True
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()
        
        # Write startup event
        self.log_event("logger_started", {
            "role": self.role,
            "run_id": self.run_id,
            "log_dir": str(self.log_dir),
            "pid": os.getpid(),
        })
    
    def _flush_loop(self):
        """Background thread that periodically flushes buffer."""
        while self._running:
            time.sleep(1.0)
            if time.monotonic() - self._last_flush > self.MAX_BUFFER_AGE_S:
                self.flush()
    
    def _get_timestamp(self) -> tuple:
        """Get both UTC ISO and monotonic timestamps."""
        utc = datetime.now(timezone.utc).isoformat()
        mono = time.monotonic()
        return utc, mono
    
    def log_event(self, event_type: str, data: Dict[str, Any] = None):
        """
        Log an event with timestamp.
        
        Args:
            event_type: Type of event (e.g., "suite_started", "handshake_complete")
            data: Event-specific data
        """
        utc, mono = self._get_timestamp()
        
        with self._buffer_lock:
            self._sequence += 1
            entry = LogEntry(
                timestamp_utc=utc,
                timestamp_mono=mono,
                event_type=event_type,
                suite_id=self._current_suite,
                data=data or {},
                role=self.role,
                run_id=self.run_id,
                sequence=self._sequence,
            )
            self._buffer.append(entry)
            
            # Check if we should flush
            if len(self._buffer) >= self.MAX_BUFFER_SIZE:
                self._flush_internal()
    
    def log_metrics_incremental(self, category: str, metrics: Dict[str, Any]):
        """
        Log metrics incrementally (append to current suite).
        
        This is the key improvement - metrics are logged immediately
        rather than waiting for suite finalization.
        
        Args:
            category: Metric category (e.g., "handshake", "data_plane", "mavlink")
            metrics: Metric values
        """
        utc, mono = self._get_timestamp()
        
        # Update suite metrics
        if category not in self._suite_metrics:
            self._suite_metrics[category] = {}
        self._suite_metrics[category].update(metrics)
        
        # Log as event for incremental recovery
        self.log_event(f"metrics_{category}", {
            "category": category,
            "metrics": metrics,
            "elapsed_s": mono - self._suite_start_mono if self._suite_start_mono else 0,
        })
        
        # Immediately write to metrics JSONL (append mode)
        self._append_to_jsonl(self.metrics_file, {
            "timestamp_utc": utc,
            "timestamp_mono": mono,
            "suite_id": self._current_suite,
            "category": category,
            "metrics": metrics,
        })
    
    def start_suite(self, suite_id: str, config: Dict[str, Any] = None):
        """
        Start logging for a new suite.
        
        Args:
            suite_id: Suite identifier
            config: Suite configuration
        """
        self._current_suite = suite_id
        self._suite_metrics = {}
        self._suite_start_mono = time.monotonic()
        
        self.log_event("suite_started", {
            "suite_id": suite_id,
            "config": config or {},
            "sync_status": asdict(self.sync_tracker.status),
        })
        
        # Update progress file
        self._update_progress("started")
    
    def end_suite(self, success: bool, error: str = ""):
        """
        End logging for current suite.
        
        Args:
            success: Whether suite completed successfully
            error: Error message if failed
        """
        elapsed = time.monotonic() - self._suite_start_mono if self._suite_start_mono else 0
        
        self.log_event("suite_ended", {
            "suite_id": self._current_suite,
            "success": success,
            "error": error,
            "elapsed_s": elapsed,
            "collected_metrics": list(self._suite_metrics.keys()),
        })
        
        # Save comprehensive suite metrics
        self._save_suite_comprehensive(success, error)
        
        # Update progress
        self._update_progress("completed" if success else "failed")
        
        # Flush everything
        self.flush()
        
        self._current_suite = None
        self._suite_metrics = {}
    
    def _save_suite_comprehensive(self, success: bool, error: str):
        """Save comprehensive suite metrics to dedicated file."""
        if not self._current_suite:
            return
        
        utc, mono = self._get_timestamp()
        
        comprehensive = {
            "timestamp_utc": utc,
            "run_id": self.run_id,
            "role": self.role,
            "suite_id": self._current_suite,
            "success": success,
            "error": error,
            "elapsed_s": mono - self._suite_start_mono if self._suite_start_mono else 0,
            "sync_status": asdict(self.sync_tracker.status),
            "metrics": self._suite_metrics,
        }
        
        # Save to suite-specific file with retries
        suite_file = self.log_dir / f"suite_{self._current_suite}_{self.role}.json"
        self._atomic_write_json(suite_file, comprehensive)
        
        # Also append to combined JSONL
        combined_file = self.log_dir / f"all_suites_{self.role}.jsonl"
        self._append_to_jsonl(combined_file, comprehensive)
    
    def _update_progress(self, status: str):
        """Update suite progress file."""
        utc, _ = self._get_timestamp()
        
        progress = {
            "last_updated_utc": utc,
            "run_id": self.run_id,
            "role": self.role,
            "current_suite": self._current_suite,
            "status": status,
            "sync_offset_ms": self.sync_tracker.status.clock_offset_ms,
        }
        
        self._atomic_write_json(self.suite_progress_file, progress)
    
    def record_sync(self, offset_ms: float, method: str = "chronos"):
        """
        Record a clock synchronization event.
        
        Args:
            offset_ms: Clock offset in milliseconds (GCS - local)
            method: Sync method used
        """
        self.sync_tracker.record_sync(offset_ms, method)
        
        self.log_event("clock_sync", {
            "offset_ms": offset_ms,
            "method": method,
            "sync_count": self.sync_tracker.status.sync_count,
        })
        
        # Save sync status
        self._atomic_write_json(self.sync_file, asdict(self.sync_tracker.status))
    
    def flush(self):
        """Force flush all buffered entries to disk."""
        with self._buffer_lock:
            self._flush_internal()
    
    def _flush_internal(self):
        """Internal flush (must hold lock)."""
        if not self._buffer:
            return
        
        entries = self._buffer.copy()
        self._buffer.clear()
        self._last_flush = time.monotonic()
        
        # Write to events file
        for entry in entries:
            self._append_to_jsonl(self.events_file, asdict(entry))
    
    def _append_to_jsonl(self, path: Path, data: Dict[str, Any]):
        """
        Append data to JSONL file with retries.
        
        This is the core "aggressive logging" feature - data is immediately
        appended rather than batched and saved all at once.
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(data, default=str) + "\n")
                    f.flush()
                    os.fsync(f.fileno())  # Ensure written to disk
                return
            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY_S * (attempt + 1))
                else:
                    # Log to stderr as last resort
                    print(f"[ROBUST_LOG] FAILED to append to {path}: {e}", file=sys.stderr)
    
    def _atomic_write_json(self, path: Path, data: Dict[str, Any]):
        """
        Atomically write JSON file (write to temp, then rename).
        
        This prevents corruption from partial writes.
        """
        temp_path = path.with_suffix(".tmp")
        
        for attempt in range(self.MAX_RETRIES):
            try:
                # Write to temp file
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, default=str)
                    f.flush()
                    os.fsync(f.fileno())
                
                # Atomic rename
                if sys.platform == 'win32':
                    # Windows doesn't support atomic rename if dest exists
                    if path.exists():
                        path.unlink()
                shutil.move(str(temp_path), str(path))
                return
            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY_S * (attempt + 1))
                else:
                    print(f"[ROBUST_LOG] FAILED to write {path}: {e}", file=sys.stderr)
    
    def stop(self):
        """Stop the logger and flush all data."""
        self._running = False
        self.log_event("logger_stopped", {})
        self.flush()
        
        if self._flush_thread.is_alive():
            self._flush_thread.join(timeout=2.0)


class SyncTracker:
    """
    Tracks clock synchronization between GCS and Drone.
    
    Features:
    - Records sync history
    - Estimates drift rate
    - Provides interpolated offset at any time
    """
    
    def __init__(self):
        self.status = SyncStatus()
        self._sync_times: List[tuple] = []  # (mono_time, offset_ms)
        self._lock = threading.Lock()
    
    def record_sync(self, offset_ms: float, method: str = "chronos"):
        """Record a sync event."""
        with self._lock:
            now_utc = datetime.now(timezone.utc).isoformat()
            now_mono = time.monotonic()
            
            self.status.clock_offset_ms = offset_ms
            self.status.clock_sync_method = method
            self.status.last_sync_utc = now_utc
            self.status.sync_count += 1
            
            # Add to history
            self._sync_times.append((now_mono, offset_ms))
            
            # Trim history
            if len(self._sync_times) > 100:
                self._sync_times = self._sync_times[-50:]
            
            # Update sync history (for export)
            self.status.sync_history.append({
                "timestamp_utc": now_utc,
                "offset_ms": offset_ms,
                "method": method,
            })
            if len(self.status.sync_history) > 20:
                self.status.sync_history = self.status.sync_history[-20:]
            
            # Calculate drift if we have enough samples
            self._estimate_drift()
    
    def _estimate_drift(self):
        """Estimate clock drift from sync history."""
        if len(self._sync_times) < 3:
            return
        
        # Simple linear regression for drift
        times = [t[0] for t in self._sync_times]
        offsets = [t[1] for t in self._sync_times]
        
        n = len(times)
        sum_t = sum(times)
        sum_o = sum(offsets)
        sum_to = sum(t * o for t, o in zip(times, offsets))
        sum_tt = sum(t * t for t in times)
        
        denom = n * sum_tt - sum_t * sum_t
        if abs(denom) > 1e-10:
            slope = (n * sum_to - sum_t * sum_o) / denom
            # Convert to ms per hour
            self.status.drift_estimate_ms_per_hour = slope * 3600.0 * 1000.0
    
    def get_current_offset(self) -> float:
        """
        Get interpolated offset at current time.
        
        Accounts for estimated drift since last sync.
        """
        with self._lock:
            if not self._sync_times:
                return 0.0
            
            last_time, last_offset = self._sync_times[-1]
            elapsed = time.monotonic() - last_time
            
            # Apply drift correction
            drift_per_s = self.status.drift_estimate_ms_per_hour / 3600000.0
            return last_offset + elapsed * drift_per_s


# =============================================================================
# Helper for shared run ID coordination
# =============================================================================

def generate_run_id() -> str:
    """Generate a new run ID based on UTC timestamp."""
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def coordinate_run_id(role: str, peer_run_id: str = None) -> str:
    """
    Coordinate run ID between GCS and Drone.
    
    The Drone is the "master" and generates the run ID.
    The GCS should use the same run ID received from Drone.
    
    Args:
        role: "gcs" or "drone"
        peer_run_id: Run ID from peer (for GCS)
    
    Returns:
        Coordinated run ID
    """
    if role == "drone":
        return generate_run_id()
    elif role == "gcs" and peer_run_id:
        return peer_run_id
    else:
        # Fallback
        return generate_run_id()


# =============================================================================
# Test
# =============================================================================

if __name__ == "__main__":
    import tempfile
    
    print("Testing RobustLogger...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        sync = SyncTracker()
        logger = RobustLogger(
            run_id="test_20260205_120000",
            role="drone",
            base_dir=Path(tmpdir),
            sync_tracker=sync,
        )
        
        # Simulate sync
        logger.record_sync(offset_ms=15.5, method="chronos")
        
        # Simulate suite
        logger.start_suite("cs-mlkem512-falcon512", {"nist_level": "L1"})
        
        # Log incremental metrics
        logger.log_metrics_incremental("handshake", {"handshake_ms": 12.5})
        time.sleep(0.1)
        logger.log_metrics_incremental("data_plane", {"packets_sent": 1000})
        time.sleep(0.1)
        logger.log_metrics_incremental("mavlink", {"total_msgs": 500})
        
        logger.end_suite(success=True)
        
        logger.stop()
        
        # Check files
        log_dir = Path(tmpdir) / "live_run_test_20260205_120000"
        print(f"\nFiles created in {log_dir}:")
        for f in log_dir.iterdir():
            print(f"  {f.name} ({f.stat().st_size} bytes)")
        
        # Read events
        events_file = log_dir / "events_drone.jsonl"
        if events_file.exists():
            print(f"\nEvents logged:")
            with open(events_file) as f:
                for line in f:
                    entry = json.loads(line)
                    print(f"  [{entry['event_type']}] {entry['timestamp_utc']}")
    
    print("\nTest complete!")
