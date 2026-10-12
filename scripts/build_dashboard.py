"""Generate the QC dashboard deterministically; do not edit generated JSON."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DS = {"type": "prometheus", "uid": "prometheus"}


def manager_layout(panels, datasource, cloud):
    """Keep existing panel IDs; add a compact summary and explicit hierarchy."""
    original = {item["title"]: item for item in panels}
    ordered = []
    next_id = max(item["id"] for item in panels) + 1
    env = 'environment=~"$environment"'

    def place(item, x, y, w, h):
        item["gridPos"] = {"x": x, "y": y, "w": w, "h": h}
        ordered.append(item)
        return item

    def row(title, y):
        nonlocal next_id
        place({"id": next_id, "title": title, "type": "row", "collapsed": False, "panels": [], "targets": []}, 0, y, 24, 1)
        next_id += 1

    def stat(title, expr, pos, description, health=False, warning=False):
        nonlocal next_id
        defaults = {"unit": "short", "decimals": 0, "noValue": "Not reporting" if health else "No telemetry", "color": {"mode": "fixed", "fixedColor": "blue"}}
        if health:
            defaults.update(mappings=[{"type": "value", "options": {
                "0": {"text": "Needs attention", "color": "red", "index": 0},
                "1": {"text": "Healthy", "color": "green", "index": 1},
            }}, {"type": "special", "options": {"match": "null", "result": {"text": "Not reporting", "color": "gray"}}}])
        if health or warning:
            defaults.update(color={"mode": "thresholds"}, thresholds={"mode": "absolute", "steps": [
                {"color": "red" if health else "green", "value": None},
                {"color": "green" if health else "orange", "value": 1},
            ]})
        item = {"id": next_id, "title": title, "type": "stat", "description": description, "datasource": datasource,
                "targets": [{"refId": "A", "expr": expr, "instant": True, "range": False, "legendFormat": "{{environment}}"}],
                "fieldConfig": {"defaults": defaults, "overrides": []},
                "options": {"graphMode": "none", "colorMode": "value", "orientation": "horizontal", "textMode": "auto",
                            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}}}
        next_id += 1
        return place(item, *pos)

    def zero_when_reporting(expr, job):
        up = f'up{{{env},job="{job}"}}'
        # Empty event/error series is zero only when its producer is up and fresh.
        # A missing collector is never silently converted into a healthy zero.
        return (f'({expr}) or on(environment) ((0 * (min by(environment) ({up}) == 1))'
                f' and on(environment) (max by(environment) (time() - timestamp({up})) < 180))')

    def count(metric, labels, job="replisense-qc-worker"):
        return zero_when_reporting(f'sum by(environment) (increase({metric}{{{env},{labels}}}[$__range]))', job)

    row("At a glance — live health and activity in the selected period", 0)
    edge = f'probe_success{{{env},service=~"frontend|api-edge"}}'
    stat("Customer access", f'min by(environment) ({edge}) * on(environment) (count by(environment) ({edge}) == bool 2) * on(environment) (max by(environment) (time() - timestamp({edge})) < bool 180)',
         (0, 1, 8, 5), "Live website HTTPS and API reachability; both checks must report and pass. API expects 401 without login. This is not an end-to-end evaluation test.", health=True)
    services = f'up{{{env},job=~"replisense-(node-api|qc-worker|python-gateway)"}}'
    dependencies = f'probe_success{{{env},service=~"node-dependencies|document-engine|redis"}}'
    processing = (f'min by(environment) ({services}) * on(environment) (count by(environment) ({services}) == bool 3)'
                  f' * on(environment) min by(environment) ({dependencies})'
                  f' * on(environment) (count by(environment) ({dependencies}) == bool 3)'
                  f' * on(environment) (max by(environment) (time() - replisense_worker_heartbeat_timestamp_seconds{{{env},worker="qc-worker"}}) < bool 120)')
    stat("QC processing health", processing, (8, 1, 8, 5), "Live API, worker, Python, database/cache and document-engine readiness plus a heartbeat younger than two minutes. Healthy means reachable, not guaranteed job success.", health=True)
    coverage = f'up{{{env},job=~"replisense-(node-api|qc-worker|python-gateway|host)"}}'
    stat("Monitoring coverage", f'min by(environment) ({coverage}) * on(environment) (count by(environment) ({coverage}) == bool 4) * on(environment) (max by(environment) (time() - timestamp({coverage})) < bool 180)',
         (16, 1, 8, 5), "All four expected private metric targets must report successfully within three minutes. Missing telemetry is Not reporting, never Healthy. Health is current, not historical uptime.", health=True)
    estimates = "Estimated sampled counter increase in the selected period; not database totals, unique documents or contract quota. Collection gaps/restarts can undercount."
    stat("Reviews completed", count("replisense_qc_runs_total", 'status="completed"'), (0, 6, 6, 4), estimates)
    stat("Reviewed DOCX generated", count("replisense_qc_exports_total", 'outcome="completed"'), (6, 6, 6, 4), estimates + " Generated exports are not downloads.")
    stat("Processing attempts failed", count("replisense_worker_jobs_failed_total", 'worker="qc-worker"'), (12, 6, 6, 4), estimates + " Retries can succeed later; not a count of permanently failed documents.", warning=True)
    stat("API server errors", count("replisense_http_requests_total", 'service="node-api",status_code=~"5.."', "replisense-node-api"), (18, 6, 6, 4), "HTTP 5xx responses in the selected period. Zero only while fresh API metrics report; missing telemetry stays unknown.", warning=True)

    alerts = original["Active monitoring alerts"]
    alerts["title"] = "Needs attention — current alerts"
    alerts["description"] = "Current firing, pending, recovery and evaluation-error alerts. An empty list means no matching alerts, not proof of end-to-end health. Document findings are not monitoring incidents."
    if cloud:
        alerts["options"] = {"viewMode": "list", "maxItems": 8, "sortOrder": 3, "dashboardAlerts": False,
                             "folder": {"uid": "replisense-qc", "title": "RepliSense QC"}, "groupMode": "default",
                             "alertInstanceLabelFilter": '{environment=~"$environment",observability="replisense-qc",setup_test!="true"}',
                             "showInstances": True, "showInactiveAlerts": False,
                             "stateFilter": {"firing": True, "pending": True, "recovering": True, "error": True, "noData": True, "normal": False}}
    place(alerts, 0, 10, 12, 6)
    activity = original["QC lifecycle events / hour"]
    activity["title"] = "Review activity · rolling hour"
    activity["targets"][0]["legendFormat"] = "{{status}}"
    place(activity, 12, 10, 12, 6)
    timing = original["QC duration p95"]
    timing["title"] = "Review processing time · 95th percentile"
    timing["description"] = "95% of measured worker attempts finish within this time. Includes failed attempts; excludes queue waiting and DOCX generation. No jobs means no measurement, not zero seconds."
    timing["targets"][0]["legendFormat"] = "QC worker"
    timing["targets"][0]["expr"] = f'({timing["targets"][0]["expr"]}) and on(environment,worker) (sum by(environment,worker) (increase(replisense_worker_job_duration_seconds_count{{{env},worker="qc-worker"}}[1h])) > 0)'
    timing["fieldConfig"]["defaults"]["noValue"] = "No measured reviews"
    place(timing, 0, 16, 8, 6)
    findings = original["QC findings / hour"]
    findings["title"] = "Findings identified · rolling hour"
    findings["targets"][0]["legendFormat"] = "{{severity}}"
    findings["fieldConfig"]["defaults"]["noValue"] = "No review activity"
    findings["fieldConfig"]["overrides"] = [{"matcher": {"id": "byName", "options": severity}, "properties": [{"id": "displayName", "value": severity.title()}, {"id": "color", "value": {"mode": "fixed", "fixedColor": color}}]} for severity, color in (("critical", "red"), ("major", "orange"), ("minor", "blue"))]
    place(findings, 8, 16, 8, 6)
    attempts = original["QC worker failures / hour"]
    attempts["title"] = "Failed processing attempts · rolling hour"
    attempts["targets"][0]["expr"] = zero_when_reporting(f'sum by(environment) (increase(replisense_worker_jobs_failed_total{{{env},worker="qc-worker"}}[1h]))', "replisense-qc-worker")
    attempts["fieldConfig"]["defaults"].update(min=0, decimals=0, custom={"axisSoftMax": 3}, noValue="No telemetry")
    place(attempts, 16, 16, 8, 6)

    row("Performance — traffic and responsiveness", 22)
    for title, new_title, x in (("HTTP requests / second", "Application requests", 0), ("HTTP latency p95", "Response time · 95th percentile", 8), ("HTTP 5xx / ten minutes", "Server errors · last 10 minutes", 16)):
        item = original[title]
        item["title"] = new_title
        item["targets"][0]["legendFormat"] = "{{service}}"
        if title == "HTTP 5xx / ten minutes":
            item["targets"][0]["expr"] = zero_when_reporting(f'sum by(environment) (increase(replisense_http_requests_total{{{env},status_code=~"5.."}}[10m]))', "replisense-node-api")
            item["targets"][0]["legendFormat"] = "{{environment}}"
            item["fieldConfig"]["defaults"].update(min=0, decimals=0, custom={"axisSoftMax": 3}, noValue="No telemetry")
        else:
            item["targets"][0]["expr"] = item["targets"][0]["expr"].replace(f'{{{env}}}', f'{{{env},route!="/health",route!="/ready"}}')
        if title == "HTTP requests / second":
            item["description"] = "Requests per second, excluding health/readiness checks. Includes API polling, not a count of users or documents."
        if title == "HTTP latency p95":
            item["targets"][0]["expr"] = f'({item["targets"][0]["expr"]}) and on(environment,service) (sum by(environment,service) (increase(replisense_http_request_duration_seconds_count{{{env},route!="/health",route!="/ready"}}[5m])) > 0)'
            item["fieldConfig"]["defaults"]["noValue"] = "No measured requests"
        place(item, x, 23, 8, 6)
    details_y = 29
    if cloud:
        row("AI usage — application activity, not a provider bill", 29)
        place(original["AI provider calls / hour"], 0, 30, 12, 6)
        place(original["AI reported tokens / hour"], 12, 30, 12, 6)
        details_y = 36
    row("Technical details — dependencies, capacity and certificates", details_y)
    for title, new_title, x in (("Public endpoint availability", "Individual service checks", 0), ("Metrics scrape availability", "Metrics collection", 12)):
        item = original[title]
        item["title"] = new_title
        item["targets"][0].update(instant=True, range=False, legendFormat="{{service}}" if x == 0 else "{{job}}")
        item["options"]["text"] = {"valueSize": 22, "titleSize": 13}
        place(item, x, details_y + 1, 12, 4)
    tls = original["TLS expiry (days)"]
    tls["description"] = "Public website/API certificate days remaining. Warning below 30 days, critical below 14. This is not the private origin certificate."
    tls["targets"][0].update(instant=True, range=False, legendFormat="{{service}}")
    tls["options"]["text"] = {"valueSize": 28, "titleSize": 13}
    place(tls, 16 if cloud else 0, details_y + 5, 8, 5)
    heartbeat = original["Worker heartbeat age"]
    heartbeat["targets"][0]["legendFormat"] = "QC worker"
    place(heartbeat, 0 if cloud else 8, details_y + 10 if cloud else details_y + 5, 8, 5)
    if cloud:
        for title, new_title, x in (("Host CPU utilization", "Server CPU usage", 0), ("Host memory utilization", "Server memory usage", 8)):
            item = original[title]
            item["title"] = new_title
            item["targets"][0]["legendFormat"] = "Server" if x == 0 else "{{environment}}"
            place(item, x, details_y + 5, 8, 5)
        exports = original["Reviewed DOCX exports / hour"]
        exports["title"] = "Reviewed document generation · rolling hour"
        # Keep the detailed delivery trend, but avoid another oversized status card.
        place(exports, 8, details_y + 10, 16, 5)
        logs = original["Sanitized operational events"]
        logs["targets"][0]["expr"] += ' | json | line_format "{{.event}}"'
        logs["options"] = {"showTime": True, "showLabels": False, "showCommonLabels": False, "wrapLogMessage": True, "prettifyLogMessage": False, "sortOrder": "Descending", "enableLogDetails": True}
        place(logs, 0, details_y + 15, 24, 5)
        # Dependency checks are already included in Individual service checks.
    return story_layout(ordered, datasource, cloud)


def story_layout(panels, datasource, cloud):
    """Native Grafana views over existing stored telemetry; no new collection."""
    if not cloud:
        return panels
    by_title = {p["title"]: p for p in panels}
    env = 'environment=~"$environment"'
    next_id = max(p["id"] for p in panels) + 1
    by_title["Monitoring coverage"]["gridPos"].update(w=4)
    panels.append({
        "id": next_id, "title": "Telemetry freshness", "type": "stat", "datasource": datasource,
        "description": "Age of the oldest visible API/worker/Python/host scrape sample. Below three minutes is fresh. A missing target is also detected by Monitoring coverage; no series means unknown, not fresh.",
        "gridPos": {"x": 20, "y": 1, "w": 4, "h": 5},
        "targets": [{"refId": "A", "expr": f'max(time() - timestamp(up{{{env},job=~"replisense-(node-api|qc-worker|python-gateway|host)"}}))', "instant": True, "range": False}],
        "fieldConfig": {"defaults": {"unit": "s", "min": 0, "decimals": 0, "noValue": "Not reporting", "color": {"mode": "thresholds"},
            "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "orange", "value": 180}, {"color": "red", "value": 300}]},
            "mappings": [{"type": "special", "options": {"match": "null", "result": {"text": "Not reporting", "color": "gray"}}}]}, "overrides": []},
        "options": {"graphMode": "none", "colorMode": "value", "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}},
    })
    timeline = by_title["Review activity · rolling hour"]
    timeline.update(title="Availability history", type="state-timeline",
                    description="Historical checks, not request traces or guaranteed QC success. Green = passing, red = failing, gaps = no observation. Never connect gaps into a healthy interval.")
    timeline["targets"] = [
        {"refId": "A", "expr": f'probe_success{{{env},service=~"frontend|api-edge|document-engine|node-dependencies"}}', "legendFormat": "{{service}}", "range": True},
        {"refId": "B", "expr": f'up{{{env},service=~"qc-worker|python-gateway"}}', "legendFormat": "{{service}}", "range": True},
    ]
    timeline["fieldConfig"] = {"defaults": {"noValue": "Unknown", "color": {"mode": "thresholds"},
        "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]},
        "mappings": [{"type": "value", "options": {"0": {"text": "Unavailable", "color": "red"}, "1": {"text": "Available", "color": "green"}}}],
        "custom": {"spanNulls": False}}, "overrides": [
            {"matcher": {"id": "byName", "options": name}, "properties": [{"id": "displayName", "value": title}]}
            for name, title in (("frontend", "Website"), ("api-edge", "API access"), ("qc-worker", "QC worker"), ("python-gateway", "Python"), ("document-engine", "DOCX engine"), ("node-dependencies", "DB / cache"))
        ]}
    timeline["options"] = {"mergeValues": True, "showValue": "never", "alignValue": "center", "rowHeight": 0.8, "legend": {"showLegend": False}, "tooltip": {"mode": "single"}}

    heatmap = by_title["Review processing time · 95th percentile"]
    heatmap.update(title="Review speed distribution", type="heatmap",
                   description="Measured worker attempts by duration bucket and time; excludes queue waiting/export. Five-minute sampled histogram increases are estimates, not exact document counts. Empty intervals mean no measured attempts. Durations over one hour are outside the finite buckets.")
    heatmap["targets"] = [{"refId": "A", "expr": f'sum by(le) (increase(replisense_worker_job_duration_seconds_bucket{{{env},worker="qc-worker",le!="+Inf"}}[5m]))', "format": "heatmap", "legendFormat": "{{le}}", "range": True}]
    heatmap["fieldConfig"] = {"defaults": {"unit": "short"}, "overrides": []}
    heatmap["options"] = {"calculate": False, "cellGap": 1, "color": {"mode": "scheme", "scheme": "Blues", "scale": "linear", "steps": 64},
                          "yAxis": {"axisLabel": "Worker duration", "unit": "s", "decimals": 0}, "legend": {"show": True}, "tooltip": {"mode": "single", "showColorScale": True}, "filterValues": {"le": 0}}

    graph = by_title["Individual service checks"]
    # Edges describe the configured architecture, not measured traffic/latency.
    # Nodes use real health values. A missing check with a reporting collector is
    # explicitly Unknown (2); a missing collector produces no topology data.
    base = f'max by(environment) (up{{{env},job=~"replisense-.*"}})'
    nodes = []
    for node, title, metric in (
        ("website", "Website", f'probe_success{{{env},service="frontend"}}'),
        ("api", "Node API", f'up{{{env},service="node-api"}}'),
        ("worker", "QC worker", f'up{{{env},service="qc-worker"}}'),
        ("python", "Python QC", f'up{{{env},service="python-gateway"}}'),
        ("docx", "DOCX engine", f'probe_success{{{env},service="document-engine"}}'),
        ("storage", "DB / cache readiness", f'probe_success{{{env},service="node-dependencies"}}'),
    ):
        value = f'(max by(environment) ({metric}) or on(environment) (2 + 0 * ({base})))'
        states = " or ".join(f'label_replace(({value} == {number}), "mainstat", "{label}", "", "")' for number, label in ((0, "Down"), (1, "Healthy"), (2, "Unknown")))
        labelled = f'label_replace(label_replace(({states}), "node", "{node}", "", ""), "title", "{title}", "", "")'
        nodes.append(f'sum by(id,title,mainstat) (label_join({labelled}, "id", ".", "environment", "node"))')
    edges = []
    for source, target in (("website", "api"), ("api", "worker"), ("worker", "python"), ("api", "docx"), ("api", "storage"), ("worker", "storage")):
        value = f'2 + 0 * ({base})'
        for label, content in (("edge", source + "-" + target), ("source_node", source), ("target_node", target)):
            value = f'label_replace(({value}), "{label}", "{content}", "", "")'
        for label, suffix in (("id", "edge"), ("source", "source_node"), ("target", "target_node")):
            value = f'label_join({value}, "{label}", ".", "environment", "{suffix}")'
        edges.append(f'sum by(id,source,target) ({value})')
    graph.update(title="QC dependency overview", type="nodeGraph", description="Configured dependencies with live health checks; arrows are architectural relationships, NOT request traces or measured flow. DB/cache is Node's combined readiness check, not a separate MongoDB probe.",
                 targets=[{"refId": "nodes", "expr": " or ".join(nodes), "format": "table", "instant": True, "range": False},
                          {"refId": "edges", "expr": " or ".join(edges), "format": "table", "instant": True, "range": False}],
                 transformations=[{"id": "renameByRegex", "options": {"regex": "^Value(?: #.*)?$", "renamePattern": "color"}}],
                 fieldConfig={"defaults": {"color": {"mode": "thresholds"}, "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}, {"color": "gray", "value": 2}]}}, "overrides": []},
                 options={"zoomMode": "cooperative", "layoutAlgorithm": "layered", "nodes": {}, "edges": {}})
    graph["gridPos"].update(h=12)
    by_title["TLS expiry (days)"]["gridPos"].update(x=12, y=41, w=6)
    by_title["Worker heartbeat age"]["gridPos"].update(x=18, y=41, w=6)
    by_title["Server CPU usage"]["gridPos"].update(y=49, w=12)
    by_title["Server memory usage"]["gridPos"].update(x=12, y=49, w=12)
    by_title["Sanitized operational events"]["gridPos"].update(y=54)
    # Remove a duplicate export trend; the top export count is retained.
    panels.remove(by_title["Reviewed document generation · rolling hour"])
    for title in ("Processing attempts failed", "API server errors", "Needs attention — current alerts"):
        by_title[title]["links"] = [
            {"title": "QC alert rules and details", "url": "https://neatparlor1816.grafana.net/alerting/list", "targetBlank": True},
            {"title": "QC operations runbook", "url": "https://github.com/saikamal-replicantsys/replisense-monitoring/blob/main/docs/QC-CLOUD-OPERATIONS.md", "targetBlank": True},
        ]
    return panels


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
            "fieldConfig": {"defaults": {"unit": unit, "noValue": "Awaiting data"}, "overrides": []},
            "options": {"legend": {"displayMode": "list", "placement": "bottom"}},
        })
        if title in ("Public endpoint availability", "Metrics scrape availability", "Dependency availability"):
            panels[-1]["fieldConfig"]["defaults"]["mappings"] = [{
                "type": "value", "options": {
                    "0": {"text": "Unavailable", "color": "red", "index": 0},
                    "1": {"text": "Available", "color": "green", "index": 1},
                },
            }]
            panels[-1]["options"].update(graphMode="none", colorMode="value", reduceOptions={"calcs": ["lastNotNull"], "fields": "", "values": False})

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
    panels[-1]["fieldConfig"]["defaults"].update(unit="suffix: days", decimals=0, color={"mode": "thresholds"},
        thresholds={"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "orange", "value": 14}, {"color": "green", "value": 30}]})
    panels[-1]["options"].update(graphMode="none", colorMode="value", reduceOptions={"calcs": ["lastNotNull"], "fields": "", "values": False})
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
        panel("AI provider calls / hour", f'sum by (provider,outcome) (increase(replisense_llm_requests_total{{{env}}}[1h])) > 0',
              description="Application provider calls, including repeated calls. SDK-internal retries are not counted separately.")
        panel("AI reported tokens / hour", f'sum by (provider,kind) (increase(replisense_llm_tokens_total{{{env},kind=~"input_tokens|output_tokens"}}[1h])) > 0',
              description="Provider-reported input/output usage, not a billing estimate. Overlapping total/cache counts are omitted. Zero-only providers are hidden; other applications sharing credentials are not visible here.")
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
        for item in panels:
            if item["title"] == "Metrics scrape availability":
                item["targets"][0]["legendFormat"] = "{{job}}"
            if item["title"] == "AI provider calls / hour":
                item["targets"][0]["legendFormat"] = "{{provider}} · {{outcome}}"
            if item["title"] == "AI reported tokens / hour":
                item["targets"][0]["legendFormat"] = "{{provider}} · {{kind}}"
            if item["title"] == "Reviewed DOCX exports / hour":
                item["targets"][0]["legendFormat"] = "{{outcome}}"
    panels = manager_layout(panels, datasource, cloud)
    return {
        "uid": "replisense-qc-operations", "title": "RepliSense QC Operations",
        "schemaVersion": 41, "version": 1, "editable": False,
        "description": "Live health at the top; activity uses the selected period. Counts are telemetry estimates, not quotas or database totals. Missing data is never treated as healthy.",
        "tags": ["qc", "RS-1143", "observability"], "refresh": "1m",
        "time": {"from": "now-6h", "to": "now"}, "timezone": "browser",
        "annotations": {"list": [{"name": "QC deployments", "enable": True, "hide": False, "iconColor": "#73BF69",
            "datasource": {"type": "grafana", "uid": "-- Grafana --"}, "target": {"type": "tags", "tags": ["replisense", "qc", "deployment"], "matchAny": False}}]} if cloud else {"list": []},
        "templating": {"list": [{
            "name": "environment", "label": "Environment", "type": "query",
            "datasource": datasource, "query": 'label_values(up{environment="qc"}, environment)' if cloud else "label_values(up, environment)",
            "refresh": 1, "multi": True, "includeAll": True, "allValue": ".*",
            "current": {"selected": True, "text": "qc" if cloud else "All", "value": "qc" if cloud else "$__all"},
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
