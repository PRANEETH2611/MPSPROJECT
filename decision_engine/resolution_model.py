"""
Structured incident resolution planner.

This module adds a safe, deterministic remediation layer that can be used
alongside the existing dashboard and AI assistant features. It does not
execute any changes; it only returns a suggested plan and indicates whether
the suggested action is considered low-risk enough for manual approval.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_upper(value: Any, default: str = "UNKNOWN") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text.upper() if text else default


def _playbook(*steps: str) -> list[str]:
    return [step for step in steps if step]


def build_resolution_plan(record: Dict[str, Any] | None) -> Dict[str, Any]:
    """
    Build a deterministic remediation plan for a metric/event record.

    Expected input keys include:
      - predicted_root_cause
      - alert_status
      - cpu_usage
      - memory_usage
      - response_time
      - failure_probability
      - anomaly_label
      - recommended_action
    """
    record = record or {}

    root_cause = _as_upper(record.get("predicted_root_cause"), "UNKNOWN")
    alert_status = _as_upper(record.get("alert_status"), "UNKNOWN")
    cpu = _to_float(record.get("cpu_usage"))
    memory = _to_float(record.get("memory_usage"))
    latency = _to_float(record.get("response_time"))
    failure_probability = _to_float(record.get("failure_probability"))
    anomaly_label = int(_to_float(record.get("anomaly_label")))

    plan: Dict[str, Any] = {
        "root_cause": root_cause,
        "severity": "CRITICAL" if alert_status == "ALERT" else "INFO",
        "auto_resolution": "Manual review recommended",
        "resolution_playbook": _playbook(
            "Review latest dashboard metrics",
            "Check application and infrastructure logs",
            str(record.get("recommended_action") or "Escalate to operator if issue persists"),
        ),
        "resolution_confidence": 0.55,
        "can_auto_execute": False,
        "safety_notes": [
            "This planner is advisory only and does not execute infrastructure changes."
        ],
    }

    if root_cause == "CPU_OVERLOAD" or cpu >= 85:
        plan.update({
            "severity": "CRITICAL",
            "auto_resolution": "Scale workload horizontally or restart the hottest service after validation",
            "resolution_playbook": _playbook(
                "Identify the top CPU-consuming service or container",
                "Check for recent deployments or runaway jobs",
                "Scale replicas or instance size if load is sustained",
                "Restart the overloaded service only after confirming safe redundancy",
            ),
            "resolution_confidence": 0.86,
            "can_auto_execute": False,
            "safety_notes": [
                "Avoid automatic restarts for stateful or singleton services.",
                "Prefer scaling before restart when traffic is still active.",
            ],
        })
    elif root_cause == "MEMORY_LEAK" or memory >= 8:
        plan.update({
            "severity": "CRITICAL",
            "auto_resolution": "Perform controlled restart and inspect for memory leak regressions",
            "resolution_playbook": _playbook(
                "Capture memory usage snapshot / heap indicators",
                "Compare current build with recent deployments",
                "Restart the affected service during a safe window or behind redundancy",
                "Create follow-up task to inspect leak source in code or dependency updates",
            ),
            "resolution_confidence": 0.84,
            "can_auto_execute": False,
            "safety_notes": [
                "Restart only after confirming redundancy or maintenance approval."
            ],
        })
    elif root_cause == "LATENCY_SPIKE" or latency >= 1000:
        plan.update({
            "severity": "WARNING",
            "auto_resolution": "Rate-limit noisy traffic, inspect dependencies, and rebalance requests",
            "resolution_playbook": _playbook(
                "Check downstream API/database latency",
                "Review load balancer health and error rates",
                "Shift traffic away from unhealthy instances if available",
                "Validate latency recovery after mitigation",
            ),
            "resolution_confidence": 0.81,
            "can_auto_execute": False,
            "safety_notes": [
                "Traffic shifting should follow existing routing and rollback rules."
            ],
        })
    elif anomaly_label == 1:
        plan.update({
            "severity": "WARNING",
            "auto_resolution": "Collect evidence and isolate the anomaly before changing production state",
            "resolution_playbook": _playbook(
                "Capture the latest anomalous metrics and logs",
                "Check whether the anomaly matches a known maintenance window or deploy",
                "Escalate for operator review if anomalies persist across consecutive samples",
            ),
            "resolution_confidence": 0.72,
            "can_auto_execute": False,
            "safety_notes": [
                "Unknown anomalies should not trigger automatic remediation."
            ],
        })
    elif alert_status == "OK":
        plan.update({
            "severity": "INFO",
            "auto_resolution": "No action required",
            "resolution_playbook": _playbook(
                "Continue monitoring current trends",
                "Review routine capacity and error-rate thresholds",
            ),
            "resolution_confidence": 0.93,
            "can_auto_execute": True,
            "safety_notes": [
                "Auto-execution only means the system can safely keep monitoring without intervention."
            ],
        })

    if failure_probability >= 0.85 and plan["severity"] != "INFO":
        plan["severity"] = "CRITICAL"
        plan["resolution_confidence"] = min(0.97, float(plan["resolution_confidence"]) + 0.05)

    return plan


def build_resolution_summary(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Return plans for multiple records with simple counts for dashboards/tests."""
    plans = [build_resolution_plan(record) for record in records]
    critical = sum(1 for plan in plans if plan["severity"] == "CRITICAL")
    warning = sum(1 for plan in plans if plan["severity"] == "WARNING")
    info = sum(1 for plan in plans if plan["severity"] == "INFO")
    return {
        "plans": plans,
        "counts": {
            "critical": critical,
            "warning": warning,
            "info": info,
            "total": len(plans),
        },
    }
