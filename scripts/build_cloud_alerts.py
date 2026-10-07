"""Generate scoped Grafana-managed alert rules (no client data in notifications)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def rules():
    definitions = [
        ("collector", "QC required services / collector unavailable", 'sum(up{environment="qc",job=~"replisense-(node-api|qc-worker|python-gateway)"}) or vector(0)', "lt", 3, "3m", "critical", "Missing/private service metrics or loss of the QC collector. Check EC2/SSM and container health.", "prom"),
        ("edge", "QC public HTTPS endpoint unavailable", 'min(probe_success{environment="qc",service=~"frontend|api-edge"}) or vector(0)', "lt", 1, "2m", "critical", "Frontend or unauthenticated API HTTPS probe failed. The API probe expects HTTP 401.", "prom"),
        ("dependencies", "QC dependency readiness failed", 'min(probe_success{environment="qc",service=~"node-dependencies|document-engine|redis"}) or vector(0)', "lt", 1, "2m", "critical", "Check Node MongoDB/Redis readiness, Redis TCP and document-engine HTTP health.", "prom"),
        ("heartbeat", "QC worker heartbeat stale", 'max(time() - replisense_worker_heartbeat_timestamp_seconds{environment="qc",worker="qc-worker"}) or vector(999999)', "gt", 120, "2m", "critical", "The worker heartbeat is missing or older than two minutes. This is process liveness, not proof a job is making progress.", "prom"),
        ("http-errors", "QC API server errors", 'sum(increase(replisense_http_requests_total{environment="qc",status_code=~"5.."}[10m])) or vector(0)', "gt", 2, "1m", "warning", "At least three HTTP 5xx responses in ten minutes. Check sanitized operational events and private AWS logs.", "prom"),
        ("operational", "QC processing / export / provider error", 'sum(count_over_time({environment="qc",job="replisense-ops",event=~"qc.attempt_failed|qc.export_failed|worker.failed|worker.maintenance_failed|llm.failed"}[10m]))', "gt", 0, "0s", "warning", "An allowlisted operational failure occurred. A retry can subsequently succeed; this alert does not mean every finding is an incident.", "logs"),
        ("gemini-access", "QC Gemini billing / authentication failed", 'sum(increase(replisense_llm_requests_total{environment="qc",outcome=~"payment_required|authentication"}[10m])) or vector(0)', "gt", 0, "0s", "critical", "Gemini reported depleted credits or invalid authentication. Verify provider billing and the QC SecureString without exposing its value.", "prom"),
        ("tls", "QC HTTPS certificate expires soon", 'min(probe_ssl_earliest_cert_expiry{environment="qc",service=~"frontend|api-edge"}) - time()', "lt", 1209600, "10m", "warning", "Public HTTPS certificate has less than fourteen days remaining. Check ACM DNS validation and origin renewal automation.", "prom"),
    ]
    result = []
    for name, title, expression, operator, threshold, pending, severity, description, source in definitions:
        datasource = "grafanacloud-logs" if source == "logs" else "grafanacloud-prom"
        query = {"refId": "A", "datasourceUid": datasource, "relativeTimeRange": {"from": 600, "to": 0},
                 "model": {"refId": "A", "expr": expression, "instant": True, "range": False, "queryType": "instant", "editorMode": "code", "intervalMs": 60000, "maxDataPoints": 43200}}
        if source == "logs":
            query["queryType"] = "instant"
        reduce = {"refId": "B", "datasourceUid": "__expr__", "relativeTimeRange": {"from": 0, "to": 0},
                  "model": {"refId": "B", "type": "reduce", "expression": "A", "reducer": "last", "settings": {"mode": "dropNN"}, "conditions": []}}
        condition = {"refId": "C", "datasourceUid": "__expr__", "relativeTimeRange": {"from": 0, "to": 0},
                     "model": {"refId": "C", "type": "threshold", "expression": "B", "conditions": [{"type": "query", "evaluator": {"type": operator, "params": [threshold]}, "operator": {"type": "and"}, "query": {"params": ["C"]}, "reducer": {"type": "last", "params": []}}]}}
        result.append({"uid": "replisense-qc-" + name, "title": title, "folderUID": "replisense-qc", "ruleGroup": "qc-operations", "orgID": 1,
                       "condition": "C", "for": pending, "noDataState": "OK" if name in {"http-errors", "operational", "gemini-access", "tls"} else "Alerting",
                       "execErrState": "Alerting", "isPaused": False, "data": [query, reduce, condition],
                       "labels": {"environment": "qc", "application": "replisense", "observability": "replisense-qc", "severity": severity},
                       "annotations": {"summary": title, "description": description, "runbook_url": "https://neatparlor1816.grafana.net/d/replisense-qc-operations"}})
    return result


if __name__ == "__main__":
    (ROOT / "grafana/cloud/alert-rules.json").write_text(json.dumps(rules(), indent=2) + "\n")
    print("Generated eight scoped QC alert rules.")
