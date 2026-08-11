"""
Adaptive DDOS Detection with Dynamic Algorithm Switching
Optimized for power-constrained environments
"""

import os
import sys
import json
import signal
import threading
import time
import psutil
import numpy as np
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

# ML Model implementations
from ddos_models.xgboost_lite import XGBoostLiteDetector
from ddos_models.lstm_basic import LSTMBasicDetector
from ddos_models.lstm_attention import LSTMAttentionDetector
from ddos_models.bilstm_basic import BiLSTMBasicDetector
from ddos_models.bilstm_attention import BiLSTMAttentionDetector
from ddos_models.transformer_lite import TransformerLiteDetector

class DDOSAlgorithm(Enum):
    XGBOOST = "xgboost"
    LSTM = "lstm"
    LSTM_ATTENTION = "lstm_attention"
    BILSTM = "bilstm"
    BILSTM_ATTENTION = "bilstm_attention"
    TRANSFORMER_ATTENTION = "transformer_attention"

@dataclass
class DetectionConfig:
    algorithm: DDOSAlgorithm
    model_path: str
    monitoring_interface: str
    alert_threshold: float
    batch_size: int
    power_mode: str = "balanced"  # "minimal", "balanced", "performance"

class AdaptiveDDOSDetector:
    def __init__(self, config: DetectionConfig):
        self.config = config
        self.current_algorithm = config.algorithm
        self.running = True
        self.detector = None
        self.switch_lock = threading.Lock()
        self.threat_level = 0
        
        # Power optimization settings
        self.power_profiles = {
            "minimal": {"batch_size": 64, "update_interval": 10.0, "features": "basic"},
            "balanced": {"batch_size": 128, "update_interval": 5.0, "features": "standard"},
            "performance": {"batch_size": 256, "update_interval": 1.0, "features": "full"}
        }
        
        self._initialize_detector()
        
        # Setup signal handlers
        signal.signal(signal.SIGUSR1, self._handle_algorithm_switch)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _initialize_detector(self):
        """Initialize the current detection algorithm"""
        detector_map = {
            DDOSAlgorithm.XGBOOST: XGBoostLiteDetector,
            DDOSAlgorithm.LSTM: LSTMBasicDetector,
            DDOSAlgorithm.LSTM_ATTENTION: LSTMAttentionDetector,
            DDOSAlgorithm.BILSTM: BiLSTMBasicDetector,
            DDOSAlgorithm.BILSTM_ATTENTION: BiLSTMAttentionDetector,
            DDOSAlgorithm.TRANSFORMER_ATTENTION: TransformerLiteDetector,
        }
        
        if self.current_algorithm in detector_map:
            power_profile = self.power_profiles[self.config.power_mode]
            self.detector = detector_map[self.current_algorithm](
                model_path=self.config.model_path,
                power_profile=power_profile
            )
            print(f"Initialized {self.current_algorithm.value} DDOS detector")
        else:
            raise ValueError(f"Unsupported algorithm: {self.current_algorithm}")

    def _handle_algorithm_switch(self, signum, frame):
        """Handle algorithm switch signal from scheduler"""
        try:
            with open('/tmp/ddos_switch_command.json', 'r') as f:
                command = json.load(f)
            
            new_algorithm = DDOSAlgorithm(command['algorithm'])
            new_power_mode = command.get('power_mode', self.config.power_mode)
            
            self._switch_algorithm(new_algorithm, new_power_mode)
            
        except Exception as e:
            print(f"Algorithm switch failed: {e}")

    def _switch_algorithm(self, new_algorithm: DDOSAlgorithm, power_mode: str) -> bool:
        """Switch to new detection algorithm"""
        with self.switch_lock:
            try:
                print(f"Switching DDOS detection: {self.current_algorithm.value} -> {new_algorithm.value}")
                print(f"Power mode: {power_mode}")
                
                # Update configuration
                old_algorithm = self.current_algorithm
                self.current_algorithm = new_algorithm
                self.config.power_mode = power_mode
                
                # Initialize new detector
                if self.detector:
                    self.detector.cleanup()
                
                self._initialize_detector()
                
                # Signal successful switch
                self._signal_switch_success()
                return True
                
            except Exception as e:
                print(f"DDOS algorithm switch failed: {e}")
                self.current_algorithm = old_algorithm
                self._initialize_detector()
                return False

    def _signal_switch_success(self):
        """Signal successful algorithm switch to scheduler"""
        status = {
            'algorithm': self.current_algorithm.value,
            'power_mode': self.config.power_mode,
            'timestamp': time.time(),
            'status': 'success',
            'threat_level': self.threat_level
        }
        
        with open('/tmp/ddos_status.json', 'w') as f:
            json.dump(status, f)

    def _monitor_network_traffic(self):
        """Monitor network traffic for DDOS patterns"""
        while self.running:
            try:
                # Collect network statistics
                network_stats = self._collect_network_features()
                
                if network_stats:
                    # Detect threats using current algorithm
                    with self.switch_lock:
                        threat_score = self.detector.predict(network_stats)
                    
                    # Update threat level
                    self._update_threat_level(threat_score)
                    
                    # Log if threat detected
                    if threat_score > self.config.alert_threshold:
                        self._handle_threat_detection(threat_score, network_stats)
                
                # Sleep based on power mode
                sleep_time = self.power_profiles[self.config.power_mode]["update_interval"]
                time.sleep(sleep_time)
                
            except Exception as e:
                print(f"Network monitoring error: {e}")
                time.sleep(1.0)

    def _collect_network_features(self) -> Optional[np.ndarray]:
        """Collect network features for DDOS detection"""
        try:
            # Get network I/O statistics
            net_io = psutil.net_io_counters()
            
            # Calculate rates (simplified feature extraction)
            current_time = time.time()
            
            if not hasattr(self, '_last_net_stats'):
                self._last_net_stats = (net_io, current_time)
                return None
            
            last_io, last_time = self._last_net_stats
            time_delta = current_time - last_time
            
            if time_delta < 0.1:  # Avoid division by zero
                return None
            
            # Calculate packet and byte rates
            packet_rate = (net_io.packets_recv - last_io.packets_recv) / time_delta
            byte_rate = (net_io.bytes_recv - last_io.bytes_recv) / time_delta
            
            # Feature engineering based on power mode
            features = self._extract_features(packet_rate, byte_rate)
            
            self._last_net_stats = (net_io, current_time)
            return features
            
        except Exception as e:
            print(f"Feature collection error: {e}")
            return None

    def _extract_features(self, packet_rate: float, byte_rate: float) -> np.ndarray:
        """Extract features based on current power mode"""
        power_profile = self.power_profiles[self.config.power_mode]
        
        if power_profile["features"] == "basic":
            # Minimal features for power conservation
            return np.array([packet_rate, byte_rate])
        
        elif power_profile["features"] == "standard":
            # Standard feature set
            avg_packet_size = byte_rate / max(packet_rate, 1)
            return np.array([packet_rate, byte_rate, avg_packet_size])
        
        else:  # "full"
            # Full feature set for maximum accuracy
            avg_packet_size = byte_rate / max(packet_rate, 1)
            packet_variance = self._calculate_packet_variance()
            entropy = self._calculate_traffic_entropy()
            return np.array([packet_rate, byte_rate, avg_packet_size, packet_variance, entropy])

    def _update_threat_level(self, threat_score: float):
        """Update current threat level"""
        if threat_score > 0.9:
            self.threat_level = 5  # Critical
        elif threat_score > 0.7:
            self.threat_level = 4  # High
        elif threat_score > 0.5:
            self.threat_level = 3  # Medium
        elif threat_score > 0.3:
            self.threat_level = 2  # Low
        else:
            self.threat_level = 1  # Minimal

    def _handle_threat_detection(self, threat_score: float, features: np.ndarray):
        """Handle detected DDOS threat"""
        alert = {
            'timestamp': time.time(),
            'algorithm': self.current_algorithm.value,
            'threat_score': float(threat_score),
            'threat_level': self.threat_level,
            'features': features.tolist()
        }
        
        # Write alert to file for scheduler
        with open('/tmp/ddos_alert.json', 'w') as f:
            json.dump(alert, f)
        
        print(f"DDOS THREAT DETECTED: Score={threat_score:.3f}, Level={self.threat_level}")

    def start(self):
        """Start the adaptive DDOS detector"""
        print(f"Starting Adaptive DDOS Detector with {self.current_algorithm.value}")
        print(f"Power mode: {self.config.power_mode}")
        
        # Start monitoring thread
        monitor_thread = threading.Thread(target=self._monitor_network_traffic)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        print("DDOS detection started")
        
        # Keep main thread alive
        try:
            while self.running:
                time.sleep(1.0)
        except KeyboardInterrupt:
            self.shutdown()

    def shutdown(self):
        """Shutdown the detector"""
        self.running = False
        if self.detector:
            self.detector.cleanup()

if __name__ == "__main__":
    config = DetectionConfig(
        algorithm=DDOSAlgorithm.XGBOOST,
        model_path="/home/dev/ddos_models/",
        monitoring_interface="wlan0",
        alert_threshold=0.7,
        batch_size=128,
        power_mode="balanced"
    )
    
    detector = AdaptiveDDOSDetector(config)
    detector.start()
