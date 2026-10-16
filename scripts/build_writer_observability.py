"""Writer-only assets. Generating files does not publish dashboards or enable alerts."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = 'environment=~"$environment"'


def dashboard():
    definitions = [
        ("Generation worker heartbeat age", f'time() - replisense_worker_heartbeat_timestamp_seconds{{{ENV},worker="writer-worker"}}', "s", 8, 4, "Live heartbeat age. Missing data means not reporting, not healthy."),
        ("Waiting to generate", f'replisense_writer_generation_jobs{{{ENV},job="replisense-writer-worker",status="queued"}} and on(environment) (time() - replisense_writer_queue_snapshot_timestamp_seconds{{{ENV},job="replisense-writer-worker"}} < 180)', "short", 8, 4, "Latest durable job per document, including delayed partial retries. Not document quota."),
        ("Oldest queued job", f'replisense_writer_generation_oldest_queued_seconds{{{ENV},job="replisense-writer-worker"}} and on(environment) (time() - replisense_writer_queue_snapshot_timestamp_seconds{{{ENV},job="replisense-writer-worker"}} < 180)', "s", 8, 4, "Includes delayed section resumes. Check snapshot freshness before interpreting."),
        ("Generation outcomes", f'sum by(outcome) (increase(replisense_writer_operations_total{{{ENV},operation="generation"}}[$__range]))', "short", 12, 6, "Sampled attempt counts, including partial outcomes; not unique documents."),
        ("Export outcomes", f'sum by(operation,outcome) (increase(replisense_writer_operations_total{{{ENV},operation=~"export_.*"}}[$__range]))', "short", 12, 6, "Actual export processing outcomes, not submissions or downloads."),
        ("Generation duration · p95", f'histogram_quantile(0.95,sum by(le) (rate(replisense_writer_operation_duration_seconds_bucket{{{ENV},operation="generation",outcome="success"}}[1h])))', "s", 12, 6, "Estimated p95 over one hour. Sparse samples are not an SLA."),
        ("Reported AI tokens", f'sum by(type) (increase(replisense_writer_reported_tokens_total{{{ENV}}}[$__range]))', "short", 12, 6, "Upstream-reported input/output tokens. Excludes unreported failed calls; not a billing total."),
        ("Preview outcomes", f'sum by(outcome) (increase(replisense_writer_operations_total{{{ENV},operation="preview"}}[$__range]))', "short", 12, 6, "Shared revision-preview processing attempts."),
        ("Queue snapshot age", f'time() - replisense_writer_queue_snapshot_timestamp_seconds{{{ENV},job="replisense-writer-worker"}}', "s", 12, 6, "A stale/missing snapshot invalidates queue-count interpretation."),
    ]
    panels = []
    x = 0
    y = 0
    for index, (title, expression, unit, width, height, description) in enumerate(definitions, 1):
        if x + width > 24:
            x = 0
            y += panels[-1]["gridPos"]["h"]
        panels.append({"id": index, "title": title, "description": description, "type": "stat" if height == 4 else "timeseries",
                       "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"},
                       "gridPos": {"x": x, "y": y, "w": width, "h": height},
                       "targets": [{"refId": "A", "expr": expression, "legendFormat": "{{operation}} {{outcome}} {{type}}", "instant": height == 4}],
                       "fieldConfig": {"defaults": {"unit": unit, "noValue": "Not reporting"}, "overrides": []}, "options": {}})
        x += width
    return {"uid": "replisense-writer-operations", "title": "RepliSense Writer Operations", "schemaVersion": 39, "version": 1,
            "tags": ["replisense", "writer"], "refresh": "1m", "time": {"from": "now-6h", "to": "now"},
            "templating": {"list": [{"name": "DS_PROMETHEUS", "type": "datasource", "query": "prometheus"},
                                      {"name": "environment", "type": "custom", "query": "local,demo,prod", "current": {"text": "local", "value": "local"}}]}, "panels": panels}


def alert_rules():
    # Writer is not deployed in qc-evaluation: explicitly gate all alerts on its scrape target.
    gate = 'and on(environment) (max by(environment) (up{job="replisense-writer-worker"}) == 1)'
    rules = [
        {"alert": "WriterWorkerUnavailable", "expr": 'up{job="replisense-writer-worker"} == 0', "for": "3m"},
        {"alert": "WriterHeartbeatStale", "expr": '(time() - replisense_worker_heartbeat_timestamp_seconds{worker="writer-worker"} > 120) ' + gate, "for": "2m"},
        {"alert": "WriterQueueSnapshotStale", "expr": '(time() - replisense_writer_queue_snapshot_timestamp_seconds{job="replisense-writer-worker"} > 180) ' + gate, "for": "2m"},
        {"alert": "WriterGenerationQueueDelayed", "expr": '(replisense_writer_generation_oldest_queued_seconds{job="replisense-writer-worker"} > 1800) and on(environment) (time() - replisense_writer_queue_snapshot_timestamp_seconds{job="replisense-writer-worker"} < 180) ' + gate, "for": "5m"},
        {"alert": "WriterGenerationInterrupted", "expr": '(replisense_writer_generation_jobs{job="replisense-writer-worker",status="interrupted"} > 0) and on(environment) (time() - replisense_writer_queue_snapshot_timestamp_seconds{job="replisense-writer-worker"} < 180) ' + gate, "for": "2m"},
        {"alert": "WriterProcessingFailures", "expr": 'sum by(environment) (increase(replisense_writer_operations_total{outcome=~"failed|partial",operation=~"generation|export_.*|preview"}[15m])) > 0', "for": "0m"},
    ]
    for rule in rules:
        rule["labels"] = {"severity": "warning", "module": "writer"}
        rule["annotations"] = {"summary": rule["alert"], "description": "Inspect the Writer dashboard, collector freshness and sanitised diagnostics. Never include source content or credentials in incident messages."}
    return {"groups": [{"name": "replisense-writer", "interval": "1m", "rules": rules}]}


def rule_tests():
    definitions = alert_rules()["groups"][0]["rules"]
    by_name = {rule["alert"]: rule for rule in definitions}

    def expected(name, labels):
        return {"exp_labels": {**labels, **by_name[name]["labels"]}, "exp_annotations": by_name[name]["annotations"]}

    fresh = [
        {"series": 'up{environment="demo",job="replisense-writer-worker"}', "values": "1x6"},
        {"series": 'replisense_worker_heartbeat_timestamp_seconds{environment="demo",worker="writer-worker"}', "values": "0+60x6"},
        {"series": 'replisense_writer_queue_snapshot_timestamp_seconds{environment="demo",job="replisense-writer-worker"}', "values": "0+60x6"},
        # Loaded API registries also contain uninitialised queue gauges. They must not alert.
        {"series": 'replisense_writer_queue_snapshot_timestamp_seconds{environment="demo",job="replisense-node-api"}', "values": "0x6"},
    ]
    cases = [
        ([{"series": 'up{environment="qc",job="replisense-node-api"}', "values": "1x6"}], {}),
        ([{"series": 'up{environment="demo",job="replisense-writer-worker"}', "values": "0x6"}],
         {"WriterWorkerUnavailable": [expected("WriterWorkerUnavailable", {"environment": "demo", "job": "replisense-writer-worker"})]}),
        (fresh, {}),
        (fresh[:2] + [{"series": 'replisense_writer_queue_snapshot_timestamp_seconds{environment="demo",job="replisense-writer-worker"}', "values": "0x6"}] + fresh[3:],
         {"WriterQueueSnapshotStale": [expected("WriterQueueSnapshotStale", {"environment": "demo", "job": "replisense-writer-worker"})]}),
        (fresh + [{"series": 'replisense_writer_generation_oldest_queued_seconds{environment="demo",job="replisense-writer-worker"}', "values": "2000x6"}],
         {"WriterGenerationQueueDelayed": [expected("WriterGenerationQueueDelayed", {"environment": "demo", "job": "replisense-writer-worker"})]}),
        (fresh + [{"series": 'replisense_writer_generation_jobs{environment="demo",job="replisense-writer-worker",status="interrupted"}', "values": "1x6"}],
         {"WriterGenerationInterrupted": [expected("WriterGenerationInterrupted", {"environment": "demo", "job": "replisense-writer-worker", "status": "interrupted"})]}),
        (fresh + [{"series": 'replisense_writer_operations_total{environment="demo",job="replisense-writer-worker",operation="generation",outcome="partial"}', "values": "0 1 1 1 1 1 1"}],
         {"WriterProcessingFailures": [expected("WriterProcessingFailures", {"environment": "demo"})]}),
    ]
    return {"rule_files": ["rules/writer-alerts.json"], "evaluation_interval": "1m", "tests": [
        {"interval": "1m", "input_series": series, "alert_rule_test": [
            {"eval_time": "6m", "alertname": rule["alert"], "exp_alerts": alerts.get(rule["alert"], [])}
            for rule in definitions]}
        for series, alerts in cases]}


if __name__ == "__main__":
    (ROOT / "grafana/dashboards/writer-operations.json").write_text(json.dumps(dashboard(), indent=2) + "\n")
    # JSON is valid YAML; usable as a Prometheus rule file without PyYAML.
    (ROOT / "prometheus/rules/writer-alerts.json").write_text(json.dumps(alert_rules(), indent=2) + "\n")
    (ROOT / "prometheus/writer-rule-tests.json").write_text(json.dumps(rule_tests(), indent=2) + "\n")
