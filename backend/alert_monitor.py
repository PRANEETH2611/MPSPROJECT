"""
Background Alert Monitoring Service
Continuously monitors system metrics and triggers email alerts
"""
import threading
import time
import pandas as pd
from datetime import datetime, timedelta
from email_service import email_service

class AlertMonitor:
    def __init__(self, data_file, config_file):
        self.data_file = data_file
        self.config_file = config_file
        self.running = False
        self.thread = None
        self.last_alert_time = {}
        self.cooldown_minutes = 5  # Minimum time between alerts for same metric
        self.alert_history = []
        
    def start(self):
        """Start background monitoring thread"""
        if self.running:
            print("⚠️  Alert monitor already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        print("✅ Alert monitor started")
    
    def stop(self):
        """Stop background monitoring"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        print("🛑 Alert monitor stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop - runs every 30 seconds"""
        while self.running:
            try:
                self._check_metrics()
            except Exception as e:
                print(f"❌ Error in alert monitor: {e}")
            
            # Wait 30 seconds before next check
            time.sleep(30)
    
    def _check_metrics(self):
        """Check current metrics against thresholds"""
        try:
            # Load latest data
            df = pd.read_csv(self.data_file)
            if df.empty:
                return
            
            # Get most recent record
            latest = df.iloc[-1]
            
            # Load configuration (default thresholds)
            thresholds = {
                'cpu_usage': 80,
                'memory_usage': 8,
                'response_time': 1000
            }
            
            # Try to load from config file
            try:
                import json
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    thresholds['cpu_usage'] = config.get('cpu_threshold', 80)
                    thresholds['memory_usage'] = config.get('memory_threshold', 8)
                    thresholds['response_time'] = config.get('latency_threshold', 1000)
            except:
                pass
            
            # Check each metric
            self._check_cpu(latest, thresholds['cpu_usage'])
            self._check_memory(latest, thresholds['memory_usage'])
            self._check_latency(latest, thresholds['response_time'])
            self._check_anomaly(latest)
            
        except Exception as e:
            print(f"Error checking metrics: {e}")
    
    def _check_cpu(self, record, threshold):
        """Check CPU usage"""
        cpu = record.get('cpu_usage', 0)
        if cpu > threshold:
            if self._should_send_alert('cpu'):
                email_service.send_alert(
                    alert_type="High CPU Usage",
                    metric_name="CPU Usage",
                    current_value=f"{cpu:.1f}%",
                    threshold=f"{threshold}%",
                    severity="CRITICAL"
                )
                self._record_alert('cpu', cpu, threshold)
    
    def _check_memory(self, record, threshold):
        """Check Memory usage"""
        memory = record.get('memory_usage', 0)
        if memory > threshold:
            if self._should_send_alert('memory'):
                email_service.send_alert(
                    alert_type="High Memory Usage",
                    metric_name="Memory Usage",
                    current_value=f"{memory:.2f} GB",
                    threshold=f"{threshold} GB",
                    severity="CRITICAL"
                )
                self._record_alert('memory', memory, threshold)
    
    def _check_latency(self, record, threshold):
        """Check Response Time"""
        latency = record.get('response_time', 0)
        if latency > threshold:
            if self._should_send_alert('latency'):
                email_service.send_alert(
                    alert_type="High Response Time",
                    metric_name="Network Latency",
                    current_value=f"{latency:.0f} ms",
                    threshold=f"{threshold} ms",
                    severity="WARNING"
                )
                self._record_alert('latency', latency, threshold)
    
    def _check_anomaly(self, record):
        """Check for anomalies"""
        anomaly = record.get('anomaly_label', 0)
        if anomaly == 1:
            if self._should_send_alert('anomaly'):
                email_service.send_alert(
                    alert_type="Anomaly Detected",
                    metric_name="System Anomaly",
                    current_value="DETECTED",
                    threshold="NORMAL",
                    severity="CRITICAL"
                )
                self._record_alert('anomaly', 'DETECTED', 'NORMAL')
    
    def _should_send_alert(self, metric_name):
        """Check if enough time has passed since last alert (cooldown)"""
        if metric_name not in self.last_alert_time:
            return True
        
        time_since_last = datetime.now() - self.last_alert_time[metric_name]
        return time_since_last > timedelta(minutes=self.cooldown_minutes)
    
    def _record_alert(self, metric_name, value, threshold):
        """Record alert in history"""
        self.last_alert_time[metric_name] = datetime.now()
        self.alert_history.append({
            'timestamp': datetime.now().isoformat(),
            'metric': metric_name,
            'value': str(value),
            'threshold': str(threshold)
        })
        
        # Keep only last 100 alerts
        if len(self.alert_history) > 100:
            self.alert_history = self.alert_history[-100:]
    
    def get_alert_history(self, limit=20):
        """Get recent alert history"""
        return self.alert_history[-limit:]

# Global instance (will be initialized in app.py)
alert_monitor = None
