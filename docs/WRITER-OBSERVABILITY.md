# RS-1169: Writer observability

Assets are opt-in for the full Writer platform. Nothing in this branch deploys
services, changes Grafana Cloud, adds billable users or modifies the QC collector.

## Enable

1. Deploy the coordinated backend reliability/metrics PR.
2. Configure the existing Writer worker with `WRITER_WORKER_METRICS_PORT=9103`
   and the existing `OBSERVABILITY_TOKEN`. Do not publish 9103 on the host.
3. Local Prometheus: copy `prometheus/writer-targets.example.yml` to
   `prometheus/targets/writer/<environment>.yml`, select the correct private target
   and environment, and mount `secrets/observability_token` (never commit it).
   The existing Compose mounts include these targets and generated rules.
4. Grafana Cloud: the existing full-platform Alloy collector may include
   `alloy/writer-optional.alloy`; its existing remote-write external environment
   label MUST match the actual platform. Never append it to QC's collector.
5. Import `grafana/dashboards/writer-operations.json`; select the existing
   Prometheus/Cloud Metrics datasource. The default environment is local.
6. Load `prometheus/rules/writer-alerts.json` through local Prometheus/Alertmanager,
   or import equivalent PromQL expressions as Grafana-managed rules using the
   existing datasource and approved email contact point. The generated rule file
   is Prometheus format, NOT Grafana's managed-rule HTTP provisioning format.
   Scope each cloud rule to the intended platform environment during import.
7. Verify private scrape success, heartbeat/snapshot freshness, one synthetic
   completion, one safe failure and a controlled alert/resolution email. Do not
   deliberately break production dependencies to test alerts.

## Meaning and safeguards

- Attempt outcomes and reported tokens are sampled telemetry, not quota or billing.
- Missing data is displayed as Not reporting, never silently healthy/zero.
- Interpret queue counts only with a fresh queue snapshot. Interrupted jobs need
  investigation/manual retry; they are not automatically repeated model calls.
- Alerts cover worker availability, stale heartbeat/snapshot, queue delay,
  interrupted generation and processing failures. No document content appears in
  notifications. Existing routing/contact points/free-plan access remain unchanged.
- One-minute scrapes and bounded labels reuse existing compute and storage.
  This adds small telemetry volume, not new always-on infrastructure; monitor the
  existing Grafana free-tier ingestion allowance rather than promising zero usage.

Regenerate assets: `python scripts/build_writer_observability.py`.
Validate: `python -m unittest discover -s tests -v` and
`promtool check rules prometheus/rules/writer-alerts.json`.
Behaviour tests: `promtool test rules prometheus/writer-rule-tests.json`.

Rollback: remove the opt-in Writer target/fragment and imported Writer assets;
leave existing QC dashboards, contact points and collectors intact. Disable the
Writer metrics port only after scraping is removed to avoid expected alerts.
