"""
Unified Process Lifecycle Management.

Provides a robust `ManagedProcess` class that guarantees:
1. Parent ownership (child dies if parent dies).
2. Clean termination (SIGTERM -> SIGKILL).
3. Group management (no orphans).
4. Cross-platform consistency (Windows Job Objects / Linux PDEATHSIG).
"""

import ctypes
import sys
import os
import time
import signal
import subprocess
import threading
import logging
import atexit
from typing import Optional, List, Union, IO, Any

logger = logging.getLogger("pqc.process")

# --- Platform Specifics ---

_use_job_objects = False
_libc = None

if sys.platform.startswith("win"):
    from ctypes import wintypes
    
    _kernel32 = ctypes.windll.kernel32
    
    # Job Object Constants
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    _JobObjectExtendedLimitInformation = 9  # Was incorrectly 2 (Basic); must be 9 for Extended
    
    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
            ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IO_COUNTERS(ctypes.Structure):
        """Windows IO_COUNTERS — 6 × ULONGLONG = 48 bytes."""
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),  # Was ctypes.c_void_p (8B); actual IO_COUNTERS is 48B
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    def _create_job_object():
        """Create a Windows Job Object that kills processes on close."""
        job = _kernel32.CreateJobObjectW(None, None)
        if not job:
            return None
        
        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        
        ret = _kernel32.SetInformationJobObject(
            job,
            _JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info)
        )
        if not ret:
            _kernel32.CloseHandle(job)
            return None
        return job

    def _assign_process_to_job(job, pid):
        """Assign a process to the job object."""
        # We need a handle to the process. subprocess.Popen gives us a handle but 
        # accessing it via ctypes requires the raw handle.
        # Popen.dethandle is not public API.
        # Instead, we open the process by PID.
        PROCESS_SET_QUOTA = 0x0100
        PROCESS_TERMINATE = 0x0001
        h_process = _kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
        if not h_process:
            return False
        
        ret = _kernel32.AssignProcessToJobObject(job, h_process)
        _kernel32.CloseHandle(h_process)
        return bool(ret)

    _use_job_objects = True

else:
    # Linux / POSIX
    try:
        _libc = ctypes.CDLL("libc.so.6")
    except Exception:
        _libc = None

    def _linux_preexec():
        """Set PR_SET_PDEATHSIG to SIGTERM."""
        if _libc:
            PR_SET_PDEATHSIG = 1
            _libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
        # Also set session ID to allow group killing if needed
        os.setsid()

# --- Global Registry ---

_REGISTRY = set()
_REGISTRY_LOCK = threading.Lock()

def _register(proc):
    with _REGISTRY_LOCK:
        _REGISTRY.add(proc)

def _unregister(proc):
    with _REGISTRY_LOCK:
        _REGISTRY.discard(proc)

def kill_all_managed_processes():
    """Kill all registered processes. Safe to call multiple times."""
    with _REGISTRY_LOCK:
        procs = list(_REGISTRY)
    
    if not procs:
        return

    logger.info(f"Cleaning up {len(procs)} managed processes...")
    for p in procs:
        try:
            p.stop(timeout=1.0)
        except Exception as e:
            logger.error(f"Error stopping process {p}: {e}")

atexit.register(kill_all_managed_processes)


# --- ManagedProcess Class ---

class ManagedProcess:
    def __init__(self, cmd: List[str], 
                 name: str = "process",
                 cwd: Optional[str] = None,
                 env: Optional[dict] = None,
                 stdout: Union[int, IO, None] = subprocess.DEVNULL,
                 stderr: Union[int, IO, None] = subprocess.STDOUT,
                 stdin: Union[int, IO, None] = subprocess.DEVNULL,
                 new_console: bool = False):
        self.cmd = cmd
        self.name = name
        self.cwd = cwd
        self.env = env
        self.stdout = stdout
        self.stderr = stderr
        self.stdin = stdin
        self.new_console = new_console
        
        self.process: Optional[subprocess.Popen] = None
        self._job_handle = None # Windows only
        
    def start(self) -> bool:
        if self.is_running():
            return True
            
        try:
            kwargs = {
                "cwd": self.cwd,
                "env": self.env,
                "stdout": self.stdout,
                "stderr": self.stderr,
                "stdin": self.stdin,
                "text": True,
            }

            if sys.platform.startswith("win"):
                # Windows Strategy:
                # 1. CREATE_NEW_PROCESS_GROUP for Ctrl+Break signaling
                # 2. Job Object for hard-kill on parent death
                
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
                if self.new_console:
                    creationflags |= subprocess.CREATE_NEW_CONSOLE
                    # If new console, and no redirection, detach handles so child uses new console
                    if self.stdout is None and self.stderr is None and self.stdin is None:
                        kwargs["close_fds"] = True
                
                kwargs["creationflags"] = creationflags
                
                # Create Job Object *before* spawning if possible, but we need PID.
                # NOTE: There is a small race window between Popen and AssignProcessToJobObject
                # where the parent could die and leave an orphan.  Windows does not support
                # CREATE_SUSPENDED via subprocess.Popen, so this gap is accepted.
                # Mitigation: atexit.register(kill_all_managed_processes) ensures cleanup
                # runs even during abnormal shutdown.  The Job Object's
                # KILL_ON_JOB_CLOSE flag handles the normal parent-exit case.
                
                self.process = subprocess.Popen(self.cmd, **kwargs)
                
                if _use_job_objects:
                    self._job_handle = _create_job_object()
                    if self._job_handle:
                        if not _assign_process_to_job(self._job_handle, self.process.pid):
                            logger.warning(f"Failed to assign {self.name} to Job Object")
            else:
                # Linux Strategy:
                # 1. preexec_fn with prctl(PDEATHSIG) and setsid
                kwargs["preexec_fn"] = _linux_preexec
                self.process = subprocess.Popen(self.cmd, **kwargs)

            _register(self)
            return True
            
        except Exception as e:
            logger.error(f"Failed to start {self.name}: {e}")
            return False

    def stop(self, timeout: float = 5.0):
        if not self.process:
            return

        _unregister(self) # Prevent double cleanup
        
        try:
            if self.process.poll() is not None:
                self.process = None
                return

            # Polite termination
            if sys.platform.startswith("win"):
                # BUG-25 fix: Try graceful CTRL_BREAK_EVENT first.
                # CREATE_NEW_PROCESS_GROUP means the process has its own
                # console group — CTRL_BREAK_EVENT targets that group.
                try:
                    _kernel32.GenerateConsoleCtrlEvent(1, self.process.pid)  # CTRL_BREAK_EVENT=1
                except Exception:
                    pass
                try:
                    self.process.wait(timeout=min(2.0, timeout))
                except subprocess.TimeoutExpired:
                    pass  # Graceful failed; fall through to force kill
                
                if self.process.poll() is None:
                    # Force kill the process tree
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(self.process.pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
            else:
                # Linux: Kill group
                try:
                    pgid = os.getpgid(self.process.pid)
                    os.killpg(pgid, signal.SIGTERM)
                except ProcessLookupError:
                    pass

            # Wait
            try:
                self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # Force kill
                if sys.platform.startswith("win"):
                    # Taskkill /F already did it, but just in case
                    self.process.kill()
                else:
                    try:
                        pgid = os.getpgid(self.process.pid)
                        os.killpg(pgid, signal.SIGKILL)
                    except (ProcessLookupError, OSError):
                        try:
                            self.process.kill()
                        except:
                            pass
        except Exception as e:
            logger.error(f"Error stopping {self.name}: {e}")
        finally:
            # Close Job Handle
            if self._job_handle:
                _kernel32.CloseHandle(self._job_handle)
                self._job_handle = None
            self.process = None

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def wait(self, timeout: Optional[float] = None):
        if self.process:
            return self.process.wait(timeout)
        return None
