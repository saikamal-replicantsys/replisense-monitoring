"""Generate the QC dashboard deterministically; do not edit generated JSON."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DS = {"type": "prometheus", "uid": "prometheus"}


def dashboard(cloud=False):
    datasource = {"type": "prometheus", "uid": "grafanacloud-prom"} if cloud else DS
    panels = []

    def panel(title, expr, unit="short", kind="timeseries", description=""):
        index = len(panels)
        panels.append({
            "id": index + 1, "title": title, "type": kind,
            "description": description, "datasource": datasource,
            "gridPos": {"x": (index % 2) * 12, "y": (index // 2) * 8, "w": 12, "h": 8},
            "targets": [{"refId": "A", "expr": expr, "legendFormat": "{{environment}} {{service}} {{worker}} {{status}} {{severity}}"}],
            "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
            "options": {"legend": {"displayMode": "list", "placement": "bottom"}},
        })
        if title in ("Public endpoint availability", "Metrics scrape availability"):
            panels[-1]["fieldConfig"]["defaults"]["mappings"] = [{
                "type": "value", "options": {
                    "0": {"text": "Unavailable", "color": "red", "index": 0},
                    "1": {"text": "Available", "color": "green", "index": 1},
                },
            }]

    env = 'environment=~"$environment"'
    panel("Public endpoint availability", f'probe_success{{{env},job="blackbox-http"}}', "short", "stat",
          "1 = expected HTTPS/status response; 0 = failed. API probe expects 401 without authentication, not a full workflow test.")
    panel("Metrics scrape availability", f'up{{{env},job=~"replisense-.*"}}', "short", "stat",
          "Missing series means not configured, NOT healthy. QC internal metrics need an outbound collector or private tunnel.")
    panel("HTTP requests / second", f'sum by (environment,service) (rate(replisense_http_requests_total{{{env}}}[5m]))', "reqps")
    panel("HTTP 5xx / ten minutes", f'sum by (environment,service) (increase(replisense_http_requests_total{{{env},status_code=~"5.."}}[10m]))')
    panel("HTTP latency p95", f'histogram_quantile(0.95, sum by (le,environment,service) (rate(replisense_http_request_duration_seconds_bucket{{{env}}}[5m])))', "s",
          description="Includes document uploads/processing; not an interactive API-only SLO.")
    panel("TLS expiry (days)", f'(probe_ssl_earliest_cert_expiry{{{env},job="blackbox-http"}} - time()) / 86400', "d", "stat")
    panel("QC lifecycle events / hour", f'sum by (environment,status) (increase(replisense_qc_runs_total{{{env}}}[1h]))',
          description="Lifecycle event counter, not current MongoDB job totals or quota usage; counters reset at restart.")
    panel("QC worker failures / hour", f'sum by (environment,worker) (increase(replisense_worker_jobs_failed_total{{{env},worker="qc-worker"}}[1h]))',
          description="Failed engine attempts; retries may later succeed. Private worker endpoint required.")
    panel("QC duration p95", f'histogram_quantile(0.95, sum by (le,environment,worker) (rate(replisense_worker_job_duration_seconds_bucket{{{env},worker="qc-worker"}}[1h])))', "s",
          description="Requires worker-process metrics; never infer duration from API-only metrics.")
    panel("QC findings / hour", f'sum by (environment,severity) (increase(replisense_qc_issues_found_total{{{env}}}[1h]))',
          description="Requires worker metrics. Findings are not application incidents.")
    panel("Worker heartbeat age", f'time() - replisense_worker_heartbeat_timestamp_seconds{{{env}}}', "s",
          description="Unavailable until worker metrics exposure is implemented; missing data is not a healthy heartbeat.")
    panel("Active monitoring alerts", f'ALERTS{{{env},alertstate="firing",severity!="heartbeat"}}', "short", "stat")
    if cloud:
        # Grafana-managed alert state is displayed in its dedicated panel, not fabricated Prometheus ALERTS.
        panels[-1].update({"type": "alertlist", "targets": [], "options": {"viewMode": "list", "maxItems": 10, "alertName": "QC", "stateFilter": {"firing": True, "pending": True}, "showOptions": "current"}})
        panel("Gemini invocations / hour", f'sum by (model,outcome) (increase(replisense_llm_requests_total{{{env}}}[1h]))',
              description="Application provider calls, including repeated calls. SDK-internal retries are not counted separately.")
        panel("Gemini reported tokens / hour", f'sum by (kind) (increase(replisense_llm_tokens_total{{{env}}}[1h]))',
              description="Total includes provider-reported thinking usage. Not a billing estimate; activity by other apps sharing the key is not visible here.")
        panel("Reviewed DOCX exports / hour", f'sum by (outcome) (increase(replisense_qc_exports_total{{{env}}}[1h]))',
              description="One event per claimed export attempt; repeated reads of an already-ready export do not increment.")
        panel("Dependency availability", f'probe_success{{{env},service=~"node-dependencies|document-engine|redis"}}', "short", "stat",
              "Node readiness checks MongoDB connection and Redis readiness; Redis TCP and document-engine HTTP health are also probed.")
        panel("Host CPU utilization", f'100 * (1 - avg(rate(node_cpu_seconds_total{{{env},mode="idle"}}[5m])))', "percent",
              description="Aggregate QC host CPU; no Docker socket or privileged exporter is used.")
        panel("Host memory utilization", f'100 * (1 - node_memory_MemAvailable_bytes{{{env}}} / node_memory_MemTotal_bytes{{{env}}})', "percent")
        panel("Sanitized operational events", '{environment=~"$environment",job="replisense-ops"}', kind="logs",
              description="Only allowlisted event names, never document text, filenames, client identities, prompts or credentials.")
        panels[-1]["datasource"] = {"type": "loki", "uid": "grafanacloud-logs"}
        panels[-1]["targets"][0]["datasource"] = panels[-1]["datasource"]
    return {
        "uid": "replisense-qc-operations", "title": "RepliSense QC Operations",
        "schemaVersion": 41, "version": 1, "editable": False,
        "tags": ["qc", "RS-1124", "observability"], "refresh": "30s",
        "time": {"from": "now-6h", "to": "now"}, "timezone": "browser",
        "templating": {"list": [{
            "name": "environment", "label": "Environment", "type": "query",
            "datasource": datasource, "query": "label_values(up, environment)",
            "refresh": 1, "multi": True, "includeAll": True, "allValue": ".*",
            "current": {"selected": True, "text": "All", "value": "$__all"},
        }]}, "panels": panels,
    }


if __name__ == "__main__":
    target = ROOT / "grafana/dashboards/qc-operations.json"
    target.write_text(json.dumps(dashboard(), indent=2) + "\n", encoding="utf-8")
    print("Generated", target.name)
    manifest = {"apiVersion": "dashboard.grafana.app/v1beta1", "kind": "Dashboard",
                "metadata": {"name": "replisense-qc-operations", "namespace": "stacks-1859509", "annotations": {"grafana.app/folder": "replisense-qc"}},
                "spec": dashboard(cloud=True)}
    cloud_target = ROOT / "grafana/cloud/dashboard.json"
    cloud_target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
