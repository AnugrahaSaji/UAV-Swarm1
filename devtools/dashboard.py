"""
Development Dashboard - Tkinter GUI

Single-page live dashboard for observing scheduler, policy, and link state.

Panels:
1. SYSTEM STATUS - Suite, action, cooldown, armed state
2. BATTERY - Live voltage, rate, mode selector, sliders
3. TELEMETRY - rx_pps, gap_p95, blackout_count, age
4. DATA PLANE - Encrypted/plaintext PPS, replay drops, handshake
5. TIMELINE - Voltage graph, suite switches, policy markers

Properties:
- Non-blocking (runs in separate thread)
- Thread-safe (uses data bus locks)
- Configurable refresh rate (5-10 Hz)
- Completely disabled via config

CRITICAL: This GUI NEVER calls scheduler or policy functions directly.
It only reads from the DataBus (read-only perspective).
"""

import logging
import threading
import time
import tkinter as tk
from tkinter import ttk
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Deque, List, Optional, Tuple

if TYPE_CHECKING:
    from devtools.config import GuiConfig
    from devtools.data_bus import DataBus, BatteryState, TimelineEvent
    from devtools.battery_sim import BatteryProvider, SimulationMode

logger = logging.getLogger("devtools.dashboard")

# Color scheme
COLORS = {
    "bg": "#1e1e1e",
    "panel_bg": "#2d2d2d",
    "text": "#ffffff",
    "text_dim": "#888888",
    "accent": "#007acc",
    "warning": "#ffcc00",
    "error": "#ff4444",
    "success": "#44ff44",
    "graph_bg": "#1a1a1a",
    "graph_line": "#00aaff",
    "graph_grid": "#333333",
    "event_suite": "#00ff88",
    "event_action": "#ff8800",
    "event_battery": "#ff4488",
}


@dataclass
class GraphPoint:
    """Point on timeline graph."""
    x: float  # Relative time (seconds from start)
    y: float  # Value


class DevDashboard:
    """
    Development dashboard GUI.
    
    Runs in a separate thread to avoid blocking the main scheduler loop.
    """
    
    def __init__(
        self,
        data_bus: "DataBus",
        battery_provider: Optional["BatteryProvider"],
        config: "GuiConfig"
    ):
        self._data_bus = data_bus
        self._battery_provider = battery_provider
        self._config = config
        
        self._root: Optional[tk.Tk] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._start_time = time.monotonic()
        
        # Graph data
        self._voltage_points: Deque[GraphPoint] = deque(maxlen=config.timeline_points)
        self._last_graph_update = 0.0
        
        # UI elements (set during _build_ui)
        self._labels = {}
        self._voltage_canvas: Optional[tk.Canvas] = None
        self._mode_var: Optional[tk.StringVar] = None
        self._drain_slider: Optional[tk.Scale] = None
        
        logger.info(f"DevDashboard initialized (refresh_hz={config.refresh_hz})")
    
    def start(self) -> None:
        """Start the dashboard in a separate thread."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run_gui, daemon=True)
        self._thread.start()
        logger.info("Dashboard thread started")
    
    def stop(self) -> None:
        """Stop the dashboard."""
        self._running = False
        if self._root:
            try:
                self._root.quit()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("Dashboard stopped")
    
    def _run_gui(self) -> None:
        """Main GUI thread."""
        try:
            self._root = tk.Tk()
            self._root.title("PQC Drone - Development Dashboard")
            self._root.geometry(f"{self._config.window_width}x{self._config.window_height}")
            self._root.configure(bg=COLORS["bg"])
            self._root.protocol("WM_DELETE_WINDOW", self._on_close)
            
            self._build_ui()
            self._schedule_update()
            
            self._root.mainloop()
            
        except Exception as e:
            logger.error(f"Dashboard GUI error: {e}")
            self._running = False
    
    def _on_close(self) -> None:
        """Handle window close."""
        self._running = False
        if self._root:
            self._root.destroy()
    
    def _build_ui(self) -> None:
        """Build the dashboard UI."""
        root = self._root
        
        # Main container
        main_frame = ttk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Configure style
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Panel.TFrame", background=COLORS["panel_bg"])
        style.configure("Panel.TLabel", background=COLORS["panel_bg"], foreground=COLORS["text"])
        style.configure("PanelTitle.TLabel", background=COLORS["panel_bg"], foreground=COLORS["accent"], font=("Consolas", 11, "bold"))
        style.configure("Value.TLabel", background=COLORS["panel_bg"], foreground=COLORS["text"], font=("Consolas", 12))
        style.configure("Warning.TLabel", background=COLORS["panel_bg"], foreground=COLORS["warning"], font=("Consolas", 12, "bold"))
        style.configure("Error.TLabel", background=COLORS["panel_bg"], foreground=COLORS["error"], font=("Consolas", 12, "bold"))
        
        # Top row: System Status, Battery, Telemetry
        top_row = ttk.Frame(main_frame)
        top_row.pack(fill=tk.X, pady=(0, 10))
        
        self._build_system_panel(top_row)
        self._build_battery_panel(top_row)
        self._build_telemetry_panel(top_row)
        
        # Middle row: Data Plane
        middle_row = ttk.Frame(main_frame)
        middle_row.pack(fill=tk.X, pady=(0, 10))
        
        self._build_dataplane_panel(middle_row)
        
        # Bottom: Timeline
        bottom_row = ttk.Frame(main_frame)
        bottom_row.pack(fill=tk.BOTH, expand=True)
        
        self._build_timeline_panel(bottom_row)
    
    def _build_system_panel(self, parent: ttk.Frame) -> None:
        """Build System Status panel."""
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        ttk.Label(panel, text="SYSTEM STATUS", style="PanelTitle.TLabel").pack(anchor=tk.W)
        ttk.Separator(panel, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)
        
        # Suite
        row = ttk.Frame(panel, style="Panel.TFrame")
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Suite:", style="Panel.TLabel", width=12).pack(side=tk.LEFT)
        self._labels["suite"] = ttk.Label(row, text="---", style="Value.TLabel")
        self._labels["suite"].pack(side=tk.LEFT)
        
        # Action
        row = ttk.Frame(panel, style="Panel.TFrame")
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Action:", style="Panel.TLabel", width=12).pack(side=tk.LEFT)
        self._labels["action"] = ttk.Label(row, text="HOLD", style="Value.TLabel")
        self._labels["action"].pack(side=tk.LEFT)
        
        # Cooldown
        row = ttk.Frame(panel, style="Panel.TFrame")
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Cooldown:", style="Panel.TLabel", width=12).pack(side=tk.LEFT)
        self._labels["cooldown"] = ttk.Label(row, text="0 ms", style="Value.TLabel")
        self._labels["cooldown"].pack(side=tk.LEFT)
        
        # Armed
        row = ttk.Frame(panel, style="Panel.TFrame")
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Armed:", style="Panel.TLabel", width=12).pack(side=tk.LEFT)
        self._labels["armed"] = ttk.Label(row, text="NO", style="Value.TLabel")
        self._labels["armed"].pack(side=tk.LEFT)
        
        # Epoch
        row = ttk.Frame(panel, style="Panel.TFrame")
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Epoch:", style="Panel.TLabel", width=12).pack(side=tk.LEFT)
        self._labels["epoch"] = ttk.Label(row, text="0", style="Value.TLabel")
        self._labels["epoch"].pack(side=tk.LEFT)
    
    def _build_battery_panel(self, parent: ttk.Frame) -> None:
        """Build Battery panel with interactive controls."""
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        ttk.Label(panel, text="BATTERY", style="PanelTitle.TLabel").pack(anchor=tk.W)
        ttk.Separator(panel, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)
        
        # Voltage
        row = ttk.Frame(panel, style="Panel.TFrame")
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Voltage:", style="Panel.TLabel", width=12).pack(side=tk.LEFT)
        self._labels["voltage"] = ttk.Label(row, text="0 mV", style="Value.TLabel")
        self._labels["voltage"].pack(side=tk.LEFT)
        
        # Rate
        row = ttk.Frame(panel, style="Panel.TFrame")
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Rate:", style="Panel.TLabel", width=12).pack(side=tk.LEFT)
        self._labels["batt_rate"] = ttk.Label(row, text="0 mV/s", style="Value.TLabel")
        self._labels["batt_rate"].pack(side=tk.LEFT)
        
        # Stress
        row = ttk.Frame(panel, style="Panel.TFrame")
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Stress:", style="Panel.TLabel", width=12).pack(side=tk.LEFT)
        self._labels["stress"] = ttk.Label(row, text="LOW", style="Value.TLabel")
        self._labels["stress"].pack(side=tk.LEFT)
        
        # Source
        row = ttk.Frame(panel, style="Panel.TFrame")
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Source:", style="Panel.TLabel", width=12).pack(side=tk.LEFT)
        self._labels["batt_source"] = ttk.Label(row, text="---", style="Value.TLabel")
        self._labels["batt_source"].pack(side=tk.LEFT)
        
        # Simulation controls (only if battery provider is simulated)
        if self._battery_provider and self._battery_provider.is_simulated():
            ttk.Separator(panel, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)
            ttk.Label(panel, text="SIMULATION CONTROLS", style="PanelTitle.TLabel").pack(anchor=tk.W)
            
            # Mode selector
            row = ttk.Frame(panel, style="Panel.TFrame")
            row.pack(fill=tk.X, pady=5)
            ttk.Label(row, text="Mode:", style="Panel.TLabel").pack(side=tk.LEFT)
            
            self._mode_var = tk.StringVar(value="stable")
            modes = ["stable", "slow_drain", "fast_drain", "throttle_drain", "step_drop", "recovery"]
            mode_combo = ttk.Combobox(row, textvariable=self._mode_var, values=modes, width=15, state="readonly")
            mode_combo.pack(side=tk.LEFT, padx=5)
            mode_combo.bind("<<ComboboxSelected>>", self._on_mode_change)
            
            # Step drop button (for step_drop mode)
            self._step_btn = ttk.Button(row, text="Trigger Drop", command=self._on_step_drop)
            self._step_btn.pack(side=tk.LEFT, padx=5)
            
            # Reset button
            reset_btn = ttk.Button(row, text="Reset", command=self._on_reset)
            reset_btn.pack(side=tk.LEFT, padx=5)
    
    def _build_telemetry_panel(self, parent: ttk.Frame) -> None:
        """Build Telemetry panel."""
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        ttk.Label(panel, text="TELEMETRY", style="PanelTitle.TLabel").pack(anchor=tk.W)
        ttk.Separator(panel, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)
        
        # RX PPS
        row = ttk.Frame(panel, style="Panel.TFrame")
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="RX PPS:", style="Panel.TLabel", width=14).pack(side=tk.LEFT)
        self._labels["rx_pps"] = ttk.Label(row, text="0.0", style="Value.TLabel")
        self._labels["rx_pps"].pack(side=tk.LEFT)
        
        # Gap P95
        row = ttk.Frame(panel, style="Panel.TFrame")
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Gap P95:", style="Panel.TLabel", width=14).pack(side=tk.LEFT)
        self._labels["gap_p95"] = ttk.Label(row, text="0.0 ms", style="Value.TLabel")
        self._labels["gap_p95"].pack(side=tk.LEFT)
        
        # Blackout count
        row = ttk.Frame(panel, style="Panel.TFrame")
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Blackouts:", style="Panel.TLabel", width=14).pack(side=tk.LEFT)
        self._labels["blackouts"] = ttk.Label(row, text="0", style="Value.TLabel")
        self._labels["blackouts"].pack(side=tk.LEFT)
        
        # Jitter
        row = ttk.Frame(panel, style="Panel.TFrame")
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Jitter:", style="Panel.TLabel", width=14).pack(side=tk.LEFT)
        self._labels["jitter"] = ttk.Label(row, text="0.0 ms", style="Value.TLabel")
        self._labels["jitter"].pack(side=tk.LEFT)
        
        # Telemetry age
        row = ttk.Frame(panel, style="Panel.TFrame")
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Age:", style="Panel.TLabel", width=14).pack(side=tk.LEFT)
        self._labels["telem_age"] = ttk.Label(row, text="--- ms", style="Value.TLabel")
        self._labels["telem_age"].pack(side=tk.LEFT)
        
        # Samples
        row = ttk.Frame(panel, style="Panel.TFrame")
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Samples:", style="Panel.TLabel", width=14).pack(side=tk.LEFT)
        self._labels["samples"] = ttk.Label(row, text="0", style="Value.TLabel")
        self._labels["samples"].pack(side=tk.LEFT)
    
    def _build_dataplane_panel(self, parent: ttk.Frame) -> None:
        """Build Data Plane panel."""
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        panel.pack(fill=tk.X)
        
        ttk.Label(panel, text="DATA PLANE", style="PanelTitle.TLabel").pack(anchor=tk.W)
        ttk.Separator(panel, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)
        
        # Horizontal layout for data plane stats
        stats_frame = ttk.Frame(panel, style="Panel.TFrame")
        stats_frame.pack(fill=tk.X)
        
        # Encrypted PPS
        col = ttk.Frame(stats_frame, style="Panel.TFrame")
        col.pack(side=tk.LEFT, expand=True)
        ttk.Label(col, text="Encrypted PPS", style="Panel.TLabel").pack()
        self._labels["enc_pps"] = ttk.Label(col, text="0.0", style="Value.TLabel")
        self._labels["enc_pps"].pack()
        
        # Plaintext PPS
        col = ttk.Frame(stats_frame, style="Panel.TFrame")
        col.pack(side=tk.LEFT, expand=True)
        ttk.Label(col, text="Plaintext PPS", style="Panel.TLabel").pack()
        self._labels["plain_pps"] = ttk.Label(col, text="0.0", style="Value.TLabel")
        self._labels["plain_pps"].pack()
        
        # Replay drops
        col = ttk.Frame(stats_frame, style="Panel.TFrame")
        col.pack(side=tk.LEFT, expand=True)
        ttk.Label(col, text="Replay Drops", style="Panel.TLabel").pack()
        self._labels["replay_drops"] = ttk.Label(col, text="0", style="Value.TLabel")
        self._labels["replay_drops"].pack()
        
        # Handshake status
        col = ttk.Frame(stats_frame, style="Panel.TFrame")
        col.pack(side=tk.LEFT, expand=True)
        ttk.Label(col, text="Handshake", style="Panel.TLabel").pack()
        self._labels["handshake"] = ttk.Label(col, text="---", style="Value.TLabel")
        self._labels["handshake"].pack()
        
        # Bytes encrypted
        col = ttk.Frame(stats_frame, style="Panel.TFrame")
        col.pack(side=tk.LEFT, expand=True)
        ttk.Label(col, text="Bytes Encrypted", style="Panel.TLabel").pack()
        self._labels["bytes_enc"] = ttk.Label(col, text="0", style="Value.TLabel")
        self._labels["bytes_enc"].pack()
        
        # Bytes decrypted
        col = ttk.Frame(stats_frame, style="Panel.TFrame")
        col.pack(side=tk.LEFT, expand=True)
        ttk.Label(col, text="Bytes Decrypted", style="Panel.TLabel").pack()
        self._labels["bytes_dec"] = ttk.Label(col, text="0", style="Value.TLabel")
        self._labels["bytes_dec"].pack()
    
    def _build_timeline_panel(self, parent: ttk.Frame) -> None:
        """Build Timeline panel with voltage graph and event markers."""
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=10)
        panel.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(panel, text="TIMELINE - Battery Voltage", style="PanelTitle.TLabel").pack(anchor=tk.W)
        ttk.Separator(panel, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)
        
        # Canvas for graph
        canvas_frame = ttk.Frame(panel, style="Panel.TFrame")
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self._voltage_canvas = tk.Canvas(
            canvas_frame,
            bg=COLORS["graph_bg"],
            highlightthickness=0
        )
        self._voltage_canvas.pack(fill=tk.BOTH, expand=True)
        
        # Event legend
        legend_frame = ttk.Frame(panel, style="Panel.TFrame")
        legend_frame.pack(fill=tk.X, pady=(5, 0))
        
        # Legend items
        for event_type, color, label in [
            ("suite", COLORS["event_suite"], "Suite Switch"),
            ("action", COLORS["event_action"], "Policy Action"),
            ("battery", COLORS["event_battery"], "Battery Event"),
        ]:
            item = ttk.Frame(legend_frame, style="Panel.TFrame")
            item.pack(side=tk.LEFT, padx=10)
            marker = tk.Canvas(item, width=12, height=12, bg=COLORS["panel_bg"], highlightthickness=0)
            marker.pack(side=tk.LEFT)
            marker.create_rectangle(2, 2, 10, 10, fill=color, outline="")
            ttk.Label(item, text=label, style="Panel.TLabel").pack(side=tk.LEFT, padx=(2, 0))
    
    def _schedule_update(self) -> None:
        """Schedule the next UI update."""
        if not self._running or not self._root:
            return
        
        interval_ms = int(1000 / self._config.refresh_hz)
        self._root.after(interval_ms, self._update_ui)
    
    def _update_ui(self) -> None:
        """Update all UI elements from data bus."""
        if not self._running:
            return
        
        try:
            # Get current state from data bus
            battery = self._data_bus.get_battery()
            telemetry = self._data_bus.get_telemetry()
            policy = self._data_bus.get_policy()
            proxy = self._data_bus.get_proxy()
            
            # Update system panel
            suite_display = policy.current_suite or "---"
            if len(suite_display) > 35:
                suite_display = suite_display[:32] + "..."
            self._labels["suite"].config(text=suite_display)
            self._labels["action"].config(text=policy.current_action)
            self._labels["cooldown"].config(text=f"{policy.cooldown_remaining_ms:.0f} ms")
            self._labels["armed"].config(
                text="YES" if policy.armed else "NO",
                style="Warning.TLabel" if policy.armed else "Value.TLabel"
            )
            self._labels["epoch"].config(text=str(policy.local_epoch))
            
            # Update battery panel
            self._labels["voltage"].config(text=f"{battery.voltage_mv} mV")
            self._labels["batt_rate"].config(text=f"{battery.rate_mv_per_sec:.1f} mV/s")
            self._labels["stress"].config(text=battery.stress_level.value.upper())
            source_text = f"{battery.source}"
            if battery.is_simulated:
                source_text += f" ({battery.simulation_mode})"
            self._labels["batt_source"].config(text=source_text)
            
            # Style based on stress
            stress_style = {
                "low": "Value.TLabel",
                "medium": "Value.TLabel",
                "high": "Warning.TLabel",
                "critical": "Error.TLabel",
            }.get(battery.stress_level.value, "Value.TLabel")
            self._labels["stress"].config(style=stress_style)
            
            # Update telemetry panel
            self._labels["rx_pps"].config(text=f"{telemetry.rx_pps:.1f}")
            self._labels["gap_p95"].config(text=f"{telemetry.gap_p95_ms:.1f} ms")
            self._labels["blackouts"].config(text=str(telemetry.blackout_count))
            self._labels["jitter"].config(text=f"{telemetry.jitter_ms:.1f} ms")
            self._labels["telem_age"].config(
                text=f"{telemetry.telemetry_age_ms:.0f} ms" if telemetry.telemetry_age_ms >= 0 else "---"
            )
            self._labels["samples"].config(text=str(telemetry.sample_count))
            
            # Update data plane panel
            self._labels["enc_pps"].config(text=f"{proxy.encrypted_pps:.1f}")
            self._labels["plain_pps"].config(text=f"{proxy.plaintext_pps:.1f}")
            self._labels["replay_drops"].config(text=str(proxy.replay_drops))
            self._labels["handshake"].config(text=proxy.handshake_status)
            self._labels["bytes_enc"].config(text=self._format_bytes(proxy.bytes_encrypted))
            self._labels["bytes_dec"].config(text=self._format_bytes(proxy.bytes_decrypted))
            
            # Update timeline graph (at lower rate)
            now = time.monotonic()
            if now - self._last_graph_update > 1.0 / self._config.graph_update_hz:
                self._update_graph()
                self._last_graph_update = now
            
        except Exception as e:
            logger.error(f"UI update error: {e}")
        
        self._schedule_update()
    
    def _update_graph(self) -> None:
        """Update the voltage timeline graph."""
        if not self._voltage_canvas:
            return
        
        canvas = self._voltage_canvas
        canvas.delete("all")
        
        # Get canvas dimensions
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width < 50 or height < 50:
            return
        
        # Margins
        margin_left = 60
        margin_right = 20
        margin_top = 20
        margin_bottom = 30
        
        graph_width = width - margin_left - margin_right
        graph_height = height - margin_top - margin_bottom
        
        # Get battery history
        history = self._data_bus.get_battery_history(max_points=self._config.timeline_points)
        if not history:
            return
        
        # Add current point to local graph data
        now = time.monotonic()
        rel_time = now - self._start_time
        if history:
            self._voltage_points.append(GraphPoint(x=rel_time, y=history[-1].voltage_mv))
        
        points = list(self._voltage_points)
        if len(points) < 2:
            return
        
        # Calculate time range (last 60 seconds)
        time_window = 60.0
        x_max = points[-1].x
        x_min = max(0, x_max - time_window)
        
        # Voltage range
        v_min = 13000
        v_max = 17000
        
        # Draw grid
        for i in range(5):
            y = margin_top + (graph_height * i / 4)
            canvas.create_line(margin_left, y, width - margin_right, y, fill=COLORS["graph_grid"], dash=(2, 4))
            v = v_max - (v_max - v_min) * i / 4
            canvas.create_text(margin_left - 5, y, text=f"{int(v)}", anchor=tk.E, fill=COLORS["text_dim"], font=("Consolas", 8))
        
        # Draw voltage line
        coords = []
        for p in points:
            if p.x < x_min:
                continue
            x = margin_left + (p.x - x_min) / time_window * graph_width
            y = margin_top + (1 - (p.y - v_min) / (v_max - v_min)) * graph_height
            y = max(margin_top, min(margin_top + graph_height, y))
            coords.extend([x, y])
        
        if len(coords) >= 4:
            canvas.create_line(coords, fill=COLORS["graph_line"], width=2, smooth=True)
        
        # Draw event markers
        events = self._data_bus.get_events(max_events=50)
        for event in events:
            # Calculate x position based on event time
            event_rel_time = event.timestamp_mono - self._start_time
            if event_rel_time < x_min or event_rel_time > x_max:
                continue
            
            x = margin_left + (event_rel_time - x_min) / time_window * graph_width
            
            # Color based on event type
            if "suite" in event.event_type:
                color = COLORS["event_suite"]
            elif "action" in event.event_type:
                color = COLORS["event_action"]
            else:
                color = COLORS["event_battery"]
            
            # Draw vertical line
            canvas.create_line(x, margin_top, x, margin_top + graph_height, fill=color, dash=(3, 3))
        
        # Draw axes
        canvas.create_line(margin_left, margin_top, margin_left, height - margin_bottom, fill=COLORS["text_dim"])
        canvas.create_line(margin_left, height - margin_bottom, width - margin_right, height - margin_bottom, fill=COLORS["text_dim"])
        
        # X-axis label
        canvas.create_text(width / 2, height - 5, text="Time (s)", fill=COLORS["text_dim"], font=("Consolas", 8))
        
        # Y-axis label
        canvas.create_text(15, height / 2, text="mV", fill=COLORS["text_dim"], font=("Consolas", 8), angle=90)
    
    def _format_bytes(self, n: int) -> str:
        """Format byte count for display."""
        if n < 1024:
            return str(n)
        if n < 1024 * 1024:
            return f"{n / 1024:.1f} KB"
        if n < 1024 * 1024 * 1024:
            return f"{n / 1024 / 1024:.1f} MB"
        return f"{n / 1024 / 1024 / 1024:.1f} GB"
    
    # =========================================================================
    # Event handlers for battery simulation controls
    # =========================================================================
    
    def _on_mode_change(self, event) -> None:
        """Handle simulation mode change."""
        if not self._battery_provider or not self._mode_var:
            return
        
        from devtools.battery_sim import SimulationMode
        mode_str = self._mode_var.get()
        try:
            mode = SimulationMode(mode_str)
            self._battery_provider.set_mode(mode)
        except ValueError:
            logger.warning(f"Invalid mode: {mode_str}")
    
    def _on_step_drop(self) -> None:
        """Handle step drop button."""
        if not self._battery_provider:
            return
        
        if hasattr(self._battery_provider, "trigger_step_drop"):
            self._battery_provider.trigger_step_drop()
    
    def _on_reset(self) -> None:
        """Handle reset button."""
        if not self._battery_provider:
            return
        
        if hasattr(self._battery_provider, "reset"):
            self._battery_provider.reset()
