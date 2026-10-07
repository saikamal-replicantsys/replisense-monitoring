# QC observability activation — 7 October 2026

Grafana context: `replisense`, stack `neatparlor1816`, folder `RepliSense QC`.
Dashboard: https://neatparlor1816.grafana.net/d/replisense-qc-operations

## Verified live

- Ingestion credential exists as a SecureString; no credential value printed.
- Private Alloy installation succeeded via SSM command
  `48d0edb6-9a98-4f06-ae04-9dbf68229c08` after fixing named-volume permissions
  and selecting IPv4 for public probes.
- Node API, QC worker and Python scrape targets report `up=1`; host scrape is up.
- All five probes pass: frontend, unauthenticated API (expected 401), Node
  MongoDB/Redis readiness, document-engine HTTP health and Redis TCP.
- Worker heartbeat is fresh. Loki receives reconstructed schema/event-only logs.
- Private verification command `4c3c4a3a-7643-432c-923e-cd6b54312a80` succeeded:
  protected endpoints 200 with credentials, 403 without credentials; MongoDB
  and Redis ready; Python metrics and document-engine healthy.
- Six application containers remain running. Alloy is the only additional
  collector; it publishes no host ports. Nginx remains the only public binding.
- Eight real QC alert rules are enabled, healthy and inactive. The synthetic
  setup-only rule reached firing, recovered to inactive, then was paused.
- Grafana contact-point test returned success for `saikamal@replicantsys.com`.
  Recipient inbox receipt remains a human verification step, not an API guarantee.
- Dashboard schema validation and upload succeeded. The rendered PNG was
  inspected and improved: clear service names, IPv4 probe correction, green
  195-day TLS expiry, explicit awaiting-data display and shorter Gemini legends.
- Nine monitoring configuration tests pass. Final screenshot is generated under
  ignored `artifacts/snapshots/replisense-qc-operations.png`.

## Boundaries and follow-up

No Terraform apply, production/demo changes, paid-plan upgrade, new EC2/network
resources, application outage, test document or Gemini invocation was needed
for this activation. Existing application telemetry was deployed previously.
QC lifecycle/findings/duration panels require fresh evaluation activity; historical
jobs are not backfilled. Provider usage reflects application invocations and
reported tokens, not SDK-internal retries or other applications sharing a key.

Collector startup observed approximately 510 QC metric series; this is an initial
measurement, not a monthly bill guarantee. Track ongoing series/log ingestion
and the post-trial plan. Reinstall the collector after instance replacement using
the operations runbook. Production onboarding and IRM responder/mobile setup
remain separate work; email alerts are active for QC now.
