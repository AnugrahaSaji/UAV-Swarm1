#!/usr/bin/env python3
"""
Clock Synchronization Module - core/clock_sync.py

Implements a 3-Way Handshake (NTP-lite) to measure drift between GCS (Server) and Drone (Client).
Formula: Offset = ((t2 - t1) + (t3 - t4)) / 2

Time definition:
  t1: Client sends request
  t2: Server receives request
  t3: Server sends response
  t4: Client receives response
  
  Offset (Server - Client) is added to Client time to get Server time.

Smoothing (opt-in):
  When smoothing=True and window >= 2, incoming offsets are collected in
  a fixed-size rolling window and the median is used.  This rejects
  single-sample outliers caused by GC pauses, scheduling jitter, or
  transient network spikes.  Default behaviour (smoothing=False) is
  unchanged: single-sample direct assignment, fully deterministic.
"""

import time
import struct
import socket
import json
import logging
from collections import deque
from statistics import median

class ClockSync:
    def __init__(self, *, smoothing: bool = False, window: int = 3):
        """
        Args:
            smoothing: If True, use median-of-N smoothing for offset updates.
                       If False (default), preserve legacy single-sample behaviour.
            window:    Number of samples to keep in the rolling window (>= 2).
                       Only used when smoothing=True.  Clamped to [2, 15].
        """
        self._offset = 0.0
        self._synced = False
        self._smoothing = bool(smoothing)
        self._window_size = max(2, min(15, int(window))) if self._smoothing else 1
        self._history: deque = deque(maxlen=self._window_size)

    def _apply_offset(self, raw_offset: float) -> float:
        """Apply a new raw offset sample and return the effective offset.

        When smoothing is disabled (default), this is a direct assignment.
        When smoothing is enabled, the raw sample is appended to a rolling
        window and the median of all stored samples becomes the effective
        offset.

        Returns:
            float: The effective offset now stored in self._offset.
        """
        if not self._smoothing:
            # Legacy path — deterministic, single-sample, no history
            self._offset = raw_offset
        else:
            self._history.append(raw_offset)
            self._offset = median(self._history)
        self._synced = True
        return self._offset
        
    def client_handshake(self, sock: socket.socket) -> float:
        """
        Perform handshake as Client (Drone).
        Sends SYNC_REQ, waits for SYNC_ACK with timestamps.
        
        Args:
            sock: Connected TCP socket to GCS.
            
        Returns:
            float: Calculated time offset (seconds).
        """
        # T1: Client sends request
        t1 = time.time()
        
        req = json.dumps({
            "cmd": "chronos_sync",
            "t1": t1
        }).encode('utf-8')
        
        sock.sendall(req + b"\n")
        
        # Read response
        data = b""
        chunk = b""
        start_wait = time.time()
        
        while time.time() - start_wait < 5.0:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break
                
        if not data:
            raise TimeoutError("No sync response received")
            
        # T4: Client receives response
        t4 = time.time()
        
        try:
            resp = json.loads(data.decode().strip())
        except json.JSONDecodeError:
            raise ValueError("Invalid sync response format")
            
        if resp.get("status") != "ok":
            raise ValueError(f"Sync failed: {resp.get('message')}")
            
        t2 = resp.get("t2", 0.0)
        t3 = resp.get("t3", 0.0)
        
        if t2 == 0.0 or t3 == 0.0:
            raise ValueError("Invalid timestamps in sync response")
            
        # Calculate offset
        # Offset = ((t2 - t1) + (t3 - t4)) / 2
        # This represents "GCS - Drone"
        offset = ((t2 - t1) + (t3 - t4)) / 2.0
        
        self._apply_offset(offset)
        
        return offset

    def update_from_rpc(self, t1: float, t4: float, resp: dict) -> float:
        """
        Update offset using RPC response (Authenticated).
        
        Args:
            t1: Time request sent.
            t4: Time response received.
            resp: Response dict from GCS containing t2, t3.
        """
        t2 = resp.get("t2", 0.0)
        t3 = resp.get("t3", 0.0)
        
        if t2 == 0.0 or t3 == 0.0:
            raise ValueError("Invalid timestamps in sync response")
            
        offset = ((t2 - t1) + (t3 - t4)) / 2.0
        
        self._apply_offset(offset)
        return offset
    
    def server_handle_sync(self, request: dict) -> dict:
        """
        Handle sync request as Server (GCS).
        
        Args:
            request: The parsed JSON request containing 't1'.
            
        Returns:
            dict: Response dictionary to send back (cmd='chronos_ack').
        """
        # T2: Server receives request (approximate, ideally captured at socket recv)
        t2 = time.time() 
        t1 = request.get("t1", 0.0)
        
        # T3: Server sends response
        t3 = time.time()
        
        return {
            "status": "ok",
            "cmd": "chronos_ack",
            "t1": t1, # Echo back
            "t2": t2,
            "t3": t3
        }
        
    def set_offset(self, offset: float):
        """Manually set offset (bypasses smoothing window)."""
        self._offset = offset
        self._synced = True
        
    def get_offset(self) -> float:
        return self._offset
        
    def synced_time(self) -> float:
        """Return current time synchronized to GCS."""
        return time.time() + self._offset

    def is_synced(self) -> bool:
        return self._synced
