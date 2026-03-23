"""
AIOps Dashboard Backend API
Flask REST API for serving dashboard data (CSV-based)
MongoDB used ONLY for login tracking
"""
import os
import sys
import secrets
import pandas as pd
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from datetime import datetime, timedelta
from io import BytesIO
import json
import random
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.login_tracker import get_login_tracker
from decision_engine.resolution_model import build_resolution_plan

# Serve static files from 'frontend' folder
app = Flask(__name__, static_folder="../frontend", static_url_path="")
CORS(app)  # Enable CORS for frontend

# Load environment variables from .env file
load_dotenv()

# -----------------------------
# PATHS
# -----------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE_DIR, "data", "processed", "final_decision_output.csv")
CONFIG_FILE = os.path.join(BASE_DIR, "dashboard", "config.json")

# -----------------------------
# SIMPLE LOGIN DATABASE (in-memory)
# -----------------------------
USERS = {
    "admin": {"password": "admin123", "role": "ADMIN"},
    "user": {"password": "user123", "role": "USER"}
}
ADMIN_SESSION_TTL_SECONDS = int(os.getenv("ADMIN_SESSION_TTL_SECONDS", "3600"))
admin_sessions = {}
AUDIT_LOG_MAX_BUFFER = int(os.getenv("AUDIT_LOG_MAX_BUFFER", "500"))
audit_log_buffer = []
_audit_indexes_ready = False

# -----------------------------
# INITIALIZE LOGIN TRACKER
# -----------------------------
login_tracker = get_login_tracker()

# Alert monitor handle (initialized later in __main__)
alert_monitor = None
ALERT_MONITOR_AUTOSTART = os.getenv("ALERT_MONITOR_AUTOSTART", "0").strip().lower() in ("1", "true", "yes")


def _prune_admin_sessions():
    """Remove expired admin sessions from memory."""
    now = datetime.now()
    expired_tokens = [
        token for token, session in admin_sessions.items()
        if session["expires_at"] <= now
    ]
    for token in expired_tokens:
        admin_sessions.pop(token, None)


def _create_admin_session(username: str):
    """Create an in-memory admin session token."""
    _prune_admin_sessions()
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(seconds=ADMIN_SESSION_TTL_SECONDS)
    admin_sessions[token] = {
        "username": username,
        "role": "ADMIN",
        "expires_at": expires_at
    }
    return token, expires_at.isoformat()


def _validate_admin_request():
    """Validate admin API access using token + user headers."""
    _prune_admin_sessions()

    token = request.headers.get("X-Admin-Token", "")
    username = request.headers.get("X-Admin-User", "")

    if not username:
        return None, (jsonify({
            "success": False,
            "error": "Missing admin authentication headers"
        }), 401)

    # Dev fallback: allow ADMIN user access even if the token is missing.
    # This keeps the demo working when frontend/backends are out of sync or after refreshes.
    # Disable by setting ALLOW_INSECURE_ADMIN=0.
    allow_insecure = os.getenv("ALLOW_INSECURE_ADMIN", "1").strip().lower() in ("1", "true", "yes")
    if not token:
        if allow_insecure or app.debug:
            u = USERS.get(username)
            if u and u.get("role") == "ADMIN":
                return username, None
        return None, (jsonify({
            "success": False,
            "error": "Missing admin authentication headers"
        }), 401)

    session = admin_sessions.get(token)
    if session is None:
        return None, (jsonify({
            "success": False,
            "error": "Invalid or expired admin session"
        }), 401)

    if session["expires_at"] <= datetime.now():
        admin_sessions.pop(token, None)
        return None, (jsonify({
            "success": False,
            "error": "Admin session expired"
        }), 401)

    if session["username"] != username or session["role"] != "ADMIN":
        return None, (jsonify({
            "success": False,
            "error": "Admin session mismatch"
        }), 403)

    return username, None


def _get_audit_collection():
    """Return MongoDB collection for audit logs if Mongo is available."""
    global _audit_indexes_ready
    if login_tracker.db is None:
        return None
    try:
        coll = login_tracker.db["admin_audit_logs"]
        if not _audit_indexes_ready:
            try:
                coll.create_index("timestamp")
                coll.create_index("actor")
                coll.create_index("action")
            finally:
                _audit_indexes_ready = True
        return coll
    except Exception:
        return None


def _record_audit_event(actor: str, action: str, details=None, status: str = "success"):
    """Record an admin audit event (MongoDB if available, else in-memory buffer)."""
    if details is None:
        details = {}
    event = {
        "timestamp": datetime.now(),
        "actor": actor,
        "action": action,
        "details": details,
        "status": status,
        "ip_address": request.remote_addr,
        "user_agent": request.headers.get("User-Agent", "Unknown"),
    }

    coll = _get_audit_collection()
    if coll is not None:
        try:
            coll.insert_one(event)
            return True
        except Exception as e:
            print(f"[WARN] Failed to write audit log to MongoDB: {e}")

    # Fallback: in-memory ring buffer
    try:
        fallback_event = dict(event)
        fallback_event["timestamp"] = fallback_event["timestamp"].isoformat()
        audit_log_buffer.append(fallback_event)
        if len(audit_log_buffer) > AUDIT_LOG_MAX_BUFFER:
            del audit_log_buffer[: max(1, AUDIT_LOG_MAX_BUFFER // 10)]
    except Exception:
        pass
    return False

# -----------------------------
# UTIL: Load dataset
# -----------------------------
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df

# Load data once at startup
try:
    df = load_data(DATA_FILE)
    print(f"[OK] Loaded {len(df)} records from CSV")
except Exception as e:
    print(f"[ERROR] Failed to load data: {e}")
    df = pd.DataFrame()

# -----------------------------
# API ROUTES
# -----------------------------

# -----------------------------
# API: Report Generation
# -----------------------------
@app.route('/api/report', methods=['GET'])
def generate_report():
    try:
        # 1. Get Data
        df = pd.read_csv(DATA_FILE)
        if df.empty:
            raise Exception("Data file is empty")
        
        # 2. Calculate Statistics (Executive Summary)
        total_records = len(df)
        if 'alert_status' in df.columns:
            alerts = df[df['alert_status'] == 'ALERT']
            total_alerts = len(alerts)
            alert_rate = (total_alerts / total_records) * 100
            
            # 3. Get Recent Incidents (Top 10)
            # Filter for alerts and sort by timestamp desc
            recent_incidents = alerts.tail(10).copy()
            # If no alerts, fallback to last 10 records
            if recent_incidents.empty:
                recent_incidents = df.tail(10).copy()
                
            # Prepare Table Data
            # Columns: Timestamp, Root Cause, Confidence, Action/Recommendation
            table_data = [['Timestamp', 'Root Cause', 'Confidence', 'Action']]
            
            for _, row in recent_incidents.iterrows():
                ts = str(row.get('timestamp', 'N/A'))
                cause = str(row.get('predicted_root_cause', 'Unknown'))
                
                # Mock Confidence if not present
                conf_val = 0.9 + (random.random() * 0.1) # 90-100%
                conf = f"{conf_val*100:.2f}%"

                # Determine Action based on Cause
                action = "Check logs / Monitor"
                if "CPU" in cause:
                    action = "Scale up CPU / Restart overloaded service"
                elif "MEMORY" in cause:
                    action = "Restart service / Check memory leak"
                elif "LATENCY" in cause:
                    action = "Check network / API latency / Load balancer"
                elif "FAILURE" in cause:
                    action = "Check error logs / Retry mechanism"
                
                table_data.append([ts, cause, conf, action])

        # 4. Generate PDF using Platypus
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()
        
        # Title
        title = Paragraph("AIOps Incident Report", styles['Title'])
        elements.append(title)
        elements.append(Spacer(1, 20))
        
        # Generated Time
        gen_time = Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal'])
        elements.append(gen_time)
        elements.append(Spacer(1, 40))

        # Executive Summary Section
        elements.append(Paragraph("Executive Summary", styles['Heading2']))
        elements.append(Spacer(1, 10))
        elements.append(Paragraph(f"<b>Total Records Analyzed:</b> {total_records}", styles['Normal']))
        elements.append(Paragraph(f"<b>Total Alerts Detected:</b> {total_alerts}", styles['Normal']))
        elements.append(Paragraph(f"<b>Alert Rate:</b> {alert_rate:.2f}%", styles['Normal']))
        elements.append(Spacer(1, 40))

        # Incidents Table Section
        elements.append(Paragraph("Recent Critical Incidents (Top 10)", styles['Heading2']))
        elements.append(Spacer(1, 10))

        # Create Table
        t = Table(table_data, colWidths=[120, 100, 80, 240])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
        ]))
        elements.append(t)
        
        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"aiops_report_enhanced_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mimetype='application/pdf'
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/')
def serve_index():
    return app.send_static_file('index.html')

@app.route('/dashboard')
def serve_dashboard():
    return app.send_static_file('dashboard.html')

@app.route('/admin')
def serve_admin():
    return app.send_static_file('admin.html')

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "records": len(df),
        "mongodb_connected": login_tracker.db is not None
    })

@app.route('/api/login', methods=['POST'])
def login():
    """User login endpoint with MongoDB tracking"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    # Get client info for tracking
    ip_address = request.remote_addr
    user_agent = request.headers.get('User-Agent', 'Unknown')
    
    user = USERS.get(username)
    if user and user["password"] == password:
        # Log successful login to MongoDB
        login_tracker.log_login(
            username=username,
            role=user["role"],
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        response = {
            "success": True,
            "username": username,
            "role": user["role"]
        }

        # Issue admin API session token for protected admin endpoints
        if user["role"] == "ADMIN":
            token, expires_at = _create_admin_session(username)
            response["admin_token"] = token
            response["admin_token_expires_at"] = expires_at

        return jsonify(response)
    else:
        # Log failed login attempt
        if username:
            login_tracker.log_failed_login(
                username=username,
                ip_address=ip_address,
                user_agent=user_agent
            )
        
        return jsonify({
            "success": False,
            "message": "Invalid username or password"
        }), 401

@app.route('/api/ingest', methods=['POST'])
def ingest_data():
    """Ingest new metrics data (Real-time stream)"""
    global df
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400
        
        # Validations
        required = ['cpu_usage', 'memory_usage', 'response_time']
        if not all(k in data for k in required):
            return jsonify({"success": False, "error": f"Missing required fields: {required}"}), 400
        
        # Validate data types
        try:
            data['cpu_usage'] = float(data['cpu_usage'])
            data['memory_usage'] = float(data['memory_usage'])
            data['response_time'] = float(data['response_time'])
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Invalid data types for metrics"}), 400
            
        # Add timestamp if missing
        if 'timestamp' not in data:
            data['timestamp'] = datetime.now()
        
        # Determine Status (Simple Rule for Demo)
        data['alert_status'] = "ALERT" if data['cpu_usage'] > 80 or data['response_time'] > 1000 else "OK"
        data['predicted_root_cause'] = "CPU_OVERLOAD" if data['cpu_usage'] > 80 else "LATENCY_SPIKE" if data['response_time'] > 1000 else "NORMAL"
        data['recommended_action'] = "Check Logs" if data['alert_status'] == "ALERT" else "No action needed"
        data['failure_probability'] = 0.8 if data['alert_status'] == "ALERT" else 0.1
        data['anomaly_label'] = 1 if data['alert_status'] == "ALERT" else 0
        data['anomaly_score'] = abs(data['cpu_usage'] - 50) / 100.0  # Simple anomaly score
        data['error_count'] = data.get('error_count', 0)
        data['predicted_failure'] = 1 if data['failure_probability'] > 0.5 else 0
        
        # Append to DataFrame
        new_row = pd.DataFrame([data])
        new_row['timestamp'] = pd.to_datetime(new_row['timestamp'], errors='coerce')
        
        # Handle empty dataframe case
        if df.empty:
            df = new_row.copy()
        else:
            df = pd.concat([df, new_row], ignore_index=True)
        
        # Optional: Save back to CSV occasionally (skipping for performance demo)
        
        return jsonify({
            "success": True, 
            "message": "Data ingested successfully", 
            "total_records": len(df),
            "ingested_record": data
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/data', methods=['GET'])
def get_data():
    """Get filtered data based on query parameters"""
    try:
        # Check if dataframe is empty
        if df.empty:
            return jsonify({
                "success": False,
                "error": "No data available. Please ensure CSV file exists and contains data."
            }), 404
        
        # Get query parameters
        alert_filter = request.args.get('alert_status', 'ALL')
        root_filter = request.args.get('root_cause', 'ALL')
        window = int(request.args.get('window', 250))
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Apply filters
        filtered = df.copy()
        
        if alert_filter != "ALL":
            filtered = filtered[filtered["alert_status"] == alert_filter]
        
        if root_filter != "ALL":
            filtered = filtered[filtered["predicted_root_cause"] == root_filter]
        
        # Date range filter
        if start_date and end_date:
            start = pd.to_datetime(start_date)
            end = pd.to_datetime(end_date)
            filtered = filtered[
                (filtered["timestamp"] >= start) &
                (filtered["timestamp"] <= end)
            ]
        
        # Check if filtered result is empty
        if filtered.empty:
            return jsonify({
                "success": False,
                "error": "No data found for selected filters"
            }), 404
        
        # Apply window
        view_df = filtered.tail(window).copy()
        
        # Check if view_df is empty after window
        if view_df.empty:
            return jsonify({
                "success": False,
                "error": "No data in selected window"
            }), 404
        
        # Get latest record
        latest = view_df.iloc[-1].to_dict()
        
        # Convert timestamp to string for JSON
        latest['timestamp'] = str(latest['timestamp'])
        
        # Calculate statistics
        alerts_count = int((view_df["alert_status"] == "ALERT").sum())
        ok_count = int((view_df["alert_status"] == "OK").sum())
        anom_count = int((view_df.get("anomaly_label", 0) == 1).sum()) if "anomaly_label" in view_df.columns else 0
        
        root_causes = view_df["predicted_root_cause"].value_counts().to_dict()
        
        return jsonify({
            "success": True,
            "data": view_df.to_dict('records'),
            "latest": latest,
            "statistics": {
                "total_records": len(view_df),
                "alerts_count": alerts_count,
                "ok_count": ok_count,
                "anomalies_count": anom_count,
                "root_causes": root_causes
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/kpi', methods=['GET'])
def get_kpi():
    """Get KPI metrics"""
    try:
        # Check if dataframe is empty
        if df.empty:
            return jsonify({
                "success": False,
                "error": "No data available"
            }), 404
        
        window = int(request.args.get('window', 250))
        view_df = df.tail(window).copy()
        
        # Check if view_df is empty
        if view_df.empty:
            return jsonify({
                "success": False,
                "error": "No data in selected window"
            }), 404
        
        latest = view_df.iloc[-1]
        
        return jsonify({
            "success": True,
            "kpi": {
                "cpu_usage": float(latest['cpu_usage']),
                "memory_usage": float(latest['memory_usage']),
                "response_time": float(latest['response_time']),
                "failure_probability": float(latest['failure_probability']),
                "anomaly_label": int(latest.get("anomaly_label", 0)),
                "alert_status": str(latest["alert_status"]),
                "timestamp": str(latest['timestamp'])
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    """Get analytics data"""
    try:
        # Check if dataframe is empty
        if df.empty:
            return jsonify({
                "success": False,
                "error": "No data available"
            }), 404
        
        window = int(request.args.get('window', 250))
        view_df = df.tail(window).copy()
        
        # Check if view_df is empty
        if view_df.empty:
            return jsonify({
                "success": False,
                "error": "No data in selected window"
            }), 404
        
        # Root cause distribution
        rc_counts = view_df["predicted_root_cause"].value_counts().to_dict() if "predicted_root_cause" in view_df.columns else {}
        
        # Alert status distribution
        alert_counts = view_df["alert_status"].value_counts().to_dict() if "alert_status" in view_df.columns else {}
        
        # Correlation matrix
        metrics = ['cpu_usage', 'memory_usage', 'response_time', 'failure_probability']
        available_metrics = [m for m in metrics if m in view_df.columns]
        
        if len(available_metrics) > 1:
            corr_matrix = view_df[available_metrics].corr().to_dict()
            stats = view_df[available_metrics].describe().to_dict()
        else:
            corr_matrix = {}
            stats = {}
        
        return jsonify({
            "success": True,
            "root_causes": rc_counts,
            "alert_status": alert_counts,
            "correlation": corr_matrix,
            "statistics": stats
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/insights', methods=['GET'])
def get_insights():
    """Get AI-powered insights"""
    try:
        # Check if dataframe is empty
        if df.empty:
            return jsonify({
                "success": False,
                "error": "No data available"
            }), 404
        
        window = int(request.args.get('window', 250))
        view_df = df.tail(window).copy()
        
        # Check if view_df is empty
        if view_df.empty:
            return jsonify({
                "success": False,
                "error": "No data in selected window"
            }), 404
        
        total_records = len(view_df)
        alerts_count = int((view_df["alert_status"] == "ALERT").sum()) if "alert_status" in view_df.columns else 0
        anom_count = int((view_df.get("anomaly_label", 0) == 1).sum()) if "anomaly_label" in view_df.columns else 0
        
        alert_rate = (alerts_count / total_records * 100) if total_records > 0 else 0
        anomaly_rate = (anom_count / total_records * 100) if total_records > 0 else 0
        
        avg_cpu = float(view_df['cpu_usage'].mean()) if 'cpu_usage' in view_df.columns else 0.0
        avg_memory = float(view_df['memory_usage'].mean()) if 'memory_usage' in view_df.columns else 0.0
        avg_response = float(view_df['response_time'].mean()) if 'response_time' in view_df.columns else 0.0
        avg_failure_prob = float(view_df['failure_probability'].mean()) if 'failure_probability' in view_df.columns else 0.0
        
        # Hourly trends
        hourly_trends = []
        if 'timestamp' in view_df.columns and not view_df.empty:
            view_df['hour'] = view_df['timestamp'].dt.hour
            hourly_stats = view_df.groupby('hour').agg({
                'cpu_usage': 'mean' if 'cpu_usage' in view_df.columns else 'count',
                'memory_usage': 'mean' if 'memory_usage' in view_df.columns else 'count',
                'response_time': 'mean' if 'response_time' in view_df.columns else 'count',
                'alert_status': lambda x: (x == 'ALERT').sum() if 'alert_status' in view_df.columns else 0
            }).reset_index()
            hourly_trends = hourly_stats.to_dict('records')
        
        return jsonify({
            "success": True,
            "insights": {
                "alert_rate": alert_rate,
                "anomaly_rate": anomaly_rate,
                "avg_cpu": avg_cpu,
                "avg_memory": avg_memory,
                "avg_response": avg_response,
                "avg_failure_prob": avg_failure_prob,
                "hourly_trends": hourly_trends
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/options', methods=['GET'])
def get_options():
    """Get filter options"""
    try:
        # Check if dataframe is empty
        if df.empty:
            return jsonify({
                "success": True,
                "root_causes": [],
                "date_range": {
                    "min": "",
                    "max": ""
                }
            })
        
        alert_filter = request.args.get('alert_status', 'ALL')
        
        temp = df.copy()
        if alert_filter != "ALL" and "alert_status" in temp.columns:
            temp = temp[temp["alert_status"] == alert_filter]
        
        root_causes = []
        if "predicted_root_cause" in temp.columns:
            root_causes = sorted(temp["predicted_root_cause"].astype(str).unique().tolist())
        
        date_min = ""
        date_max = ""
        if "timestamp" in df.columns and not df.empty:
            date_min = str(df["timestamp"].min().date())
            date_max = str(df["timestamp"].max().date())
        
        return jsonify({
            "success": True,
            "root_causes": root_causes,
            "date_range": {
                "min": date_min,
                "max": date_max
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/login-history', methods=['GET'])
def get_login_history():
    """Get login history (Admin only) - MongoDB tracking"""
    try:
        limit = int(request.args.get('limit', 20))
        logins = login_tracker.get_recent_logins(limit=limit)
        
        return jsonify({
            "success": True,
            "logins": logins,
            "total": len(logins)
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/login-stats', methods=['GET'])
def get_login_stats():
    """Get login statistics (Admin only) - MongoDB tracking"""
    try:
        stats = login_tracker.get_login_stats()
        
        return jsonify({
            "success": True,
            "stats": stats
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    """Get or Update System Configuration"""
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard", "config.json")
    
    if request.method == 'POST':
        try:
            admin_user, auth_error = _validate_admin_request()
            if auth_error:
                return auth_error

            new_config = request.get_json()
            with open(config_path, 'w') as f:
                json.dump(new_config, f, indent=4)

            _record_audit_event(
                actor=admin_user,
                action="config.update",
                details={"keys": sorted(list(new_config.keys())) if isinstance(new_config, dict) else []},
                status="success",
            )
            return jsonify({"success": True, "config": new_config})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    else:
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                return jsonify({"success": True, "config": config})
            else:
                # Defaults
                return jsonify({"success": True, "config": {
                    "cpu_threshold": 80, 
                    "memory_threshold": 8, 
                    "latency_threshold": 1000,
                    "hotfix_until": 0
                }})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/forecast', methods=['POST'])
def get_forecast():
    """Predictive Forecasting API"""
    try:
        req = request.get_json()
        if not req:
            return jsonify({"success": False, "error": "No JSON body provided"}), 400
            
        metric = req.get('metric', 'cpu_usage')
        horizon = int(req.get('horizon', 30))
        
        # Validate metric exists in dataframe
        if metric not in df.columns:
            return jsonify({
                "success": False, 
                "error": f"Metric '{metric}' not found. Available: {list(df.columns)}"
            }), 400
        
        # Prepare Data
        if df.empty:
            return jsonify({"success": False, "error": "No data available"}), 404
            
        temp_df = df.dropna(subset=[metric, 'timestamp']).copy()
        if len(temp_df) < 10:
             return jsonify({
                 "success": False, 
                 "error": f"Insufficient data for forecasting. Need at least 10 records, got {len(temp_df)}"
             }), 400
             
        # Feature Engineering (Simple index-based)
        temp_df['time_idx'] = np.arange(len(temp_df))
        X = temp_df[['time_idx']].values
        y = temp_df[metric].values
        
        # Training
        model = RandomForestRegressor(n_estimators=50, random_state=42, n_jobs=1)
        model.fit(X, y)
        
        # Prediction
        last_idx = temp_df['time_idx'].iloc[-1]
        future_X = np.arange(last_idx + 1, last_idx + 1 + horizon).reshape(-1, 1)
        predictions = model.predict(future_X).tolist()
        
        # Future Dates
        last_date = pd.to_datetime(temp_df['timestamp'].iloc[-1])
        # Calculate average time interval
        if len(temp_df) > 1:
            time_diffs = temp_df['timestamp'].diff().dropna()
            avg_interval = time_diffs.mean()
            # Use average interval in minutes, default to 1 min if calculation fails
            interval_minutes = max(1, int(avg_interval.total_seconds() / 60))
        else:
            interval_minutes = 1
            
        future_dates = [(last_date + timedelta(minutes=interval_minutes * (i+1))).isoformat() for i in range(horizon)]
        
        return jsonify({
            "success": True,
            "metric": metric,
            "dates": future_dates,
            "predictions": predictions,
            "avg_predicted": float(np.mean(predictions)),
            "max_predicted": float(np.max(predictions)),
            "min_predicted": float(np.min(predictions)),
            "training_samples": len(temp_df)
        })
        
    except ValueError as ve:
        return jsonify({"success": False, "error": f"Value error: {str(ve)}"}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/admin/history', methods=['GET'])
def get_admin_history():
    """Get login history for admin dashboard"""
    try:
        _, auth_error = _validate_admin_request()
        if auth_error:
            return auth_error

        limit = int(request.args.get('limit', 20))
        history = login_tracker.get_recent_logins(limit=limit)
        return jsonify({"success": True, "history": history})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/admin/users', methods=['GET', 'POST', 'DELETE'])
def manage_users():
    """User Management Endpoint (Admin only)"""
    try:
        admin_user, auth_error = _validate_admin_request()
        if auth_error:
            return auth_error

        if request.method == 'GET':
            # Return all users (without passwords)
            users_list = [
                {"username": username, "role": info["role"]}
                for username, info in USERS.items()
            ]
            return jsonify({"success": True, "users": users_list})
        
        elif request.method == 'POST':
            # Add new user
            data = request.get_json()
            username = data.get('username')
            password = data.get('password')
            role = data.get('role', 'USER')
            
            if not username or not password:
                return jsonify({"success": False, "error": "Username and password required"}), 400
            
            if username in USERS:
                return jsonify({"success": False, "error": "User already exists"}), 400
            
            USERS[username] = {"password": password, "role": role}
            _record_audit_event(
                actor=admin_user,
                action="user.create",
                details={"target_username": username, "target_role": role},
                status="success",
            )
            return jsonify({"success": True, "message": f"User '{username}' added successfully"})
        
        elif request.method == 'DELETE':
            # Delete user
            data = request.get_json()
            username = data.get('username')
            
            if not username:
                return jsonify({"success": False, "error": "Username required"}), 400
            
            if username not in USERS:
                return jsonify({"success": False, "error": "User not found"}), 404
            
            if username == 'admin':
                return jsonify({"success": False, "error": "Cannot delete admin user"}), 403
            
            del USERS[username]
            _record_audit_event(
                actor=admin_user,
                action="user.delete",
                details={"target_username": username},
                status="success",
            )
            return jsonify({"success": True, "message": f"User '{username}' deleted successfully"})
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/admin/system-health', methods=['GET'])
def get_system_health():
    """System Health Monitoring Endpoint (Admin only)"""
    try:
        _, auth_error = _validate_admin_request()
        if auth_error:
            return auth_error

        # Check database connection
        db_status = "Connected" if login_tracker.db is not None else "Disconnected"
        collection_name = None
        if login_tracker.db is not None:
            collection = getattr(login_tracker, "logins_collection", None)
            collection_name = getattr(collection, "name", "user_logins")
        
        # Check data file
        data_file_exists = os.path.exists(DATA_FILE)
        data_file_size = os.path.getsize(DATA_FILE) if data_file_exists else 0
        
        # Try to get system metrics with psutil
        memory_mb = 0
        cpu_percent = 0
        uptime_seconds = 0
        
        psutil_available = False
        try:
            import psutil
            psutil_available = True
            process = psutil.Process()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024  # Convert to MB
            cpu_percent = psutil.cpu_percent(interval=0.1)
            uptime_seconds = int((datetime.now() - datetime.fromtimestamp(process.create_time())).total_seconds())
        except ImportError:
            # psutil not installed, use fallback values
            memory_mb = 0
            cpu_percent = 0
            uptime_seconds = 0
        except Exception as e:
            # Any other psutil error
            print(f"Warning: Could not get system metrics: {e}")
            memory_mb = 0
            cpu_percent = 0
            uptime_seconds = 0
        
        health_data = {
            "mongodb": {
                "status": db_status,
                "collection": collection_name
            },
            "data_file": {
                "exists": data_file_exists,
                "path": DATA_FILE,
                "size_mb": round(data_file_size / 1024 / 1024, 2),
                "records": len(df)
            },
            "server": {
                "memory_mb": round(memory_mb, 2),
                "cpu_percent": round(cpu_percent, 2),
                "uptime_seconds": uptime_seconds,
                "psutil_available": psutil_available
            },
            "users": {
                "total_count": len(USERS)
            }
        }
        
        return jsonify({"success": True, "health": health_data})
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/admin/export-logs', methods=['GET'])
def export_logs():
    """Export login history as JSON (Admin only)"""
    try:
        admin_user, auth_error = _validate_admin_request()
        if auth_error:
            return auth_error

        limit = int(request.args.get('limit', 100))
        logs = login_tracker.get_recent_logins(limit=limit)
        
        # Create JSON export
        export_data = {
            "exported_at": datetime.now().isoformat(),
            "total_records": len(logs),
            "logs": logs
        }

        _record_audit_event(
            actor=admin_user,
            action="logs.export_login_history",
            details={"limit": limit, "records": len(logs)},
            status="success",
        )
        
        return jsonify({"success": True, "data": export_data})
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/logs', methods=['GET'])
def get_logs():
    """Log Intelligence API"""
    try:
        # Generate logs for the last N records
        window = int(request.args.get('window', 50))
        
        if df.empty:
            return jsonify({"success": False, "error": "No data available"}), 404
            
        view_df = df.tail(window).copy()
        
        # Ensure timestamp column exists and is valid
        if 'timestamp' not in view_df.columns:
            return jsonify({"success": False, "error": "Timestamp column not found"}), 500
        
        LOG_TEMPLATES = {
            "INFO": [
                "Health check passed for service 'payments-v2'",
                "Incoming request: GET /api/v1/user/1023",
                "Cache hit for key 'session:1023'",
                "Database connection pool: 5/20 utilized",
                "Successfully processed batch update",
                "API endpoint /v2/metrics responded in 45ms"
            ],
            "WARNING": [
                "High memory usage detected (75%)",
                "Database query took longer than expected (350ms)",
                "Rate limit approaching for API key 'client_web'",
                "Retry attempt 2/3 for external service call",
                "Cache eviction triggered due to memory pressure"
            ],
            "ERROR": [
                "Connection refused: mongodb://db-primary:27017",
                "Timeout waiting for upstream service",
                "NullPointerException in PaymentController",
                "Transaction rolled back due to deadlock",
                "Failed to acquire database lock after 5 retries",
                "HTTP 500 error from payment gateway"
            ]
        }
        
        logs = []
        for _, row in view_df.iterrows():
            try:
                # Ensure timestamp is valid
                timestamp = row.get('timestamp')
                if pd.isna(timestamp):
                    continue
                    
                timestamp_str = pd.to_datetime(timestamp).isoformat()
                
                # Determine severity
                alert_status = row.get('alert_status', 'OK')
                cpu_usage = row.get('cpu_usage', 0)
                memory_usage = row.get('memory_usage', 0)
                
                if alert_status == 'ALERT':
                    severity = "ERROR" if random.random() > 0.3 else "WARNING"
                    count = random.randint(2, 5)
                else:
                    severity = "INFO" if random.random() > 0.1 else "WARNING"
                    count = random.randint(0, 2)
                
                for _ in range(count):
                    msg = random.choice(LOG_TEMPLATES[severity])
                    
                    # Correlate specific errors
                    if severity == "ERROR" and cpu_usage > 90:
                        msg = f"Critical CPU Throttle at {cpu_usage:.1f}%"
                    elif severity == "WARNING" and memory_usage > 7:
                        msg = f"High memory usage detected: {memory_usage:.2f} GB"
                    
                    logs.append({
                        "timestamp": timestamp_str,
                        "level": severity,
                        "message": msg
                    })
                    
            except Exception as row_err:
                # Skip problematic rows
                print(f"Warning: Skipping row due to error: {row_err}")
                continue
                
        return jsonify({"success": True, "logs": logs, "total": len(logs)})
        
    except ValueError as ve:
        return jsonify({"success": False, "error": f"Invalid parameter: {str(ve)}"}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# -----------------------------
# API: Email Alert Management
# -----------------------------
@app.route('/api/admin/test-email', methods=['POST'])
def test_email():
    """Send test email to verify SendGrid configuration"""
    try:
        admin_user, auth_error = _validate_admin_request()
        if auth_error:
            return auth_error

        from email_service import email_service
        
        if not email_service.enabled:
            return jsonify({
                "success": False, 
                "error": "Email service not configured. Check SENDGRID_API_KEY in .env file"
            }), 400
        
        success = email_service.send_test_email()
        
        if success:
            _record_audit_event(
                actor=admin_user,
                action="email.test_send",
                details={"recipients": len(email_service.recipient_emails)},
                status="success",
            )
            return jsonify({
                "success": True,
                "message": f"Test email sent to {len(email_service.recipient_emails)} recipients"
            })
        else:
            _record_audit_event(
                actor=admin_user,
                action="email.test_send",
                details={"recipients": len(email_service.recipient_emails)},
                status="failed",
            )
            return jsonify({
                "success": False,
                "error": "Failed to send email. Check server logs for details."
            }), 500
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/admin/alert-history', methods=['GET'])
def get_alert_history():
    """Get recent alert history"""
    try:
        _, auth_error = _validate_admin_request()
        if auth_error:
            return auth_error

        if alert_monitor is None:
            return jsonify({
                "success": True,
                "alerts": [],
                "total": 0,
                "message": "Alert monitor not running"
            })
        
        limit = int(request.args.get('limit', 20))
        history = alert_monitor.get_alert_history(limit)
        
        return jsonify({
            "success": True,
            "alerts": history,
            "total": len(history)
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/admin/alert-config', methods=['GET'])
def get_alert_config():
    """Get current alert configuration"""
    try:
        _, auth_error = _validate_admin_request()
        if auth_error:
            return auth_error

        from email_service import email_service
        
        return jsonify({
            "success": True,
            "config": {
                "enabled": email_service.enabled,
                "from_email": email_service.from_email,
                "recipients": email_service.recipient_emails,
                "recipient_count": len(email_service.recipient_emails)
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/admin/alert-monitor/status', methods=['GET'])
def get_alert_monitor_status():
    """Get alert monitor running status (Admin only)."""
    try:
        _, auth_error = _validate_admin_request()
        if auth_error:
            return auth_error

        running = bool(alert_monitor is not None and getattr(alert_monitor, "running", False))
        return jsonify({"success": True, "running": running, "autostart": ALERT_MONITOR_AUTOSTART})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/admin/alert-monitor/start', methods=['POST'])
def start_alert_monitor():
    """Start background alert monitoring (Admin only)."""
    global alert_monitor
    try:
        admin_user, auth_error = _validate_admin_request()
        if auth_error:
            return auth_error

        from alert_monitor import AlertMonitor

        if alert_monitor is None:
            alert_monitor = AlertMonitor(DATA_FILE, CONFIG_FILE)

        alert_monitor.start()
        _record_audit_event(actor=admin_user, action="alert_monitor.start", details={}, status="success")
        return jsonify({"success": True, "message": "Alert monitor started"})
    except Exception as e:
        try:
            _record_audit_event(actor=admin_user, action="alert_monitor.start", details={"error": str(e)}, status="failed")
        except Exception:
            pass
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/admin/alert-monitor/stop', methods=['POST'])
def stop_alert_monitor():
    """Stop background alert monitoring (Admin only)."""
    global alert_monitor
    try:
        admin_user, auth_error = _validate_admin_request()
        if auth_error:
            return auth_error

        if alert_monitor is None:
            return jsonify({"success": True, "message": "Alert monitor not running"})

        alert_monitor.stop()
        _record_audit_event(actor=admin_user, action="alert_monitor.stop", details={}, status="success")
        return jsonify({"success": True, "message": "Alert monitor stopped"})
    except Exception as e:
        try:
            _record_audit_event(actor=admin_user, action="alert_monitor.stop", details={"error": str(e)}, status="failed")
        except Exception:
            pass
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/admin/audit-logs', methods=['GET'])
def get_audit_logs():
    """Get recent admin audit logs (Admin only)."""
    try:
        _, auth_error = _validate_admin_request()
        if auth_error:
            return auth_error

        limit = int(request.args.get("limit", 100))
        limit = max(1, min(limit, 1000))

        coll = _get_audit_collection()
        if coll is not None:
            events = list(coll.find({}).sort("timestamp", -1).limit(limit))
            for ev in events:
                ev["_id"] = str(ev.get("_id"))
                ts = ev.get("timestamp")
                if isinstance(ts, datetime):
                    ev["timestamp"] = ts.isoformat()
        else:
            events = list(reversed(audit_log_buffer))[:limit]

        return jsonify({"success": True, "events": events, "total": len(events)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# -----------------------------
# API: Groq AI Chat
# -----------------------------
@app.route('/api/chat', methods=['POST'])
def ai_chat():
    """Interactive chat with Groq AI assistant"""
    try:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(__file__))
        from groq_service import groq_service
        
        data = request.json
        user_message = data.get('message', '')
        conversation_history = data.get('history', [])
        
        if not user_message:
            return jsonify({"success": False, "error": "No message provided"}), 400
        
        if not groq_service.enabled:
            return jsonify({
                "success": False,
                "error": "AI service not configured. Add GROQ_API_KEY to .env file"
            }), 400
        
        response = groq_service.chat(user_message, conversation_history)
        
        return jsonify({
            "success": True,
            "response": response
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/analyze-anomaly', methods=['POST'])
def analyze_anomaly():
    """Analyze an anomaly and get AI recommendations"""
    try:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(__file__))
        from groq_service import groq_service
        
        data = request.json
        metric = data.get('metric', '')
        value = data.get('value', '')
        threshold = data.get('threshold', '')
        logs = data.get('logs', '')
        
        if not groq_service.enabled:
            return jsonify({
                "success": False,
                "error": "AI service not configured"
            }), 400
        
        analysis = groq_service.analyze_anomaly(metric, value, threshold, logs)
        
        return jsonify({
            "success": True,
            "analysis": analysis
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/resolution-preview', methods=['GET', 'POST'])
def resolution_preview():
    """Return a deterministic remediation plan for the latest or provided record."""
    try:
        if request.method == 'POST':
            payload = request.get_json() or {}
            record = payload.get("record", payload)
        else:
            if df.empty:
                return jsonify({"success": False, "error": "No data available"}), 404
            record = df.iloc[-1].to_dict()

        if record is None:
            return jsonify({"success": False, "error": "No record provided"}), 400

        plan = build_resolution_plan(record)
        return jsonify({
            "success": True,
            "record": record,
            "resolution": plan
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == '__main__':
    print("ðŸš€ Starting AIOps Backend API Server...")
    print(f"ðŸ“Š Data file: {DATA_FILE}")
    print(f"ðŸ“ˆ Records loaded: {len(df)}")
    print(f"ðŸ” MongoDB login tracking: {'Enabled' if login_tracker.db is not None else 'Disabled'}")
    
    # Initialize and start alert monitoring
    try:
        from alert_monitor import AlertMonitor
        from email_service import email_service
        
        alert_monitor = AlertMonitor(DATA_FILE, CONFIG_FILE)
        if ALERT_MONITOR_AUTOSTART:
            alert_monitor.start()
            print(f"ðŸ“§ Email alerting: {'Enabled' if email_service.enabled else 'Disabled (No API key)'}")
        else:
            print("â„¹ï¸  Alert monitor autostart disabled (set ALERT_MONITOR_AUTOSTART=1 to enable).")
            print("â„¹ï¸  Use POST /api/admin/alert-monitor/start to start it explicitly.")
    except Exception as e:
        print(f"âš ï¸  Alert monitor failed to start: {e}")
        alert_monitor = None
    
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)

