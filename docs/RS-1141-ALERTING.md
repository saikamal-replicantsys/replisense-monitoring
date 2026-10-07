# RS-1141: evaluate maintained incident alerting, not archived OnCall OSS

Decision proposal (7 October 2026): keep Prometheus-compatible rules and stable
environment/service/severity labels; email first; evaluate Grafana Cloud IRM.
Grafana Cloud is connected; the QC email contact point and its send test are
configured. See `QC-CLOUD-OPERATIONS.md` for rollout, privacy and verification.
A contact point alone is not verified end-to-end incident delivery.

## Two layers

1. Detection: metrics/probes/log-derived events create operational alerts.
2. Delivery/escalation: independent Alertmanager SMTP or hosted IRM groups,
   notifies, acknowledges and resolves them. Do not rely on Node to notify when
   Node is down. The application's logging webhook is not an incident manager.

Grafana OnCall OSS was archived on 24 March 2026 and its cloud-linked calling,
SMS and push functions ceased. See official notice:
https://grafana.com/docs/oncall/latest/set-up/open-source/
IRM is maintained; https://grafana.com/products/cloud/irm/ and
https://grafana.com/pricing/ list 3 free monthly active IRM users. Verify actual
email/mobile/phone channel limits during evaluation, not by assumption.

## Acceptance checks

- One approved recipient receives a synthetic incident and recovery email.
- QC/public API unreachable, low-volume 5xx, stale/failed QC jobs and failed
  DOCX exports have actionable rules. Remaining worker/export/provider telemetry
  gaps are tracked separately; do not mark these checks complete yet.
- Labels segregate prod/QC; planned demo shutdown is muted, not a critical incident.
- Repeat alerts grouped; acknowledgements stop escalation; recovery resolves.
- Monitoring failure is detected from an independent location/heartbeat service.
- Alert payloads contain only environment, service, severity, bounded error code,
  timestamp, summary and protected runbook/dashboard link. No document content,
  filenames, tenant identity, prompt text, credentials or presigned URLs.
- Credentials stored outside Git, narrow API scopes, access review and rotation.
- Free-tier usage/limits measured before a subscription is approved.

## Future lightweight mobile pager

Use a stable incident interface, not a phone directly polling Prometheus and not
shipping Grafana/AWS/SMTP secrets inside the app:

Detection -> incident backend / IRM -> authenticated webhook adapter -> APNs/FCM
-> mobile app -> authenticated acknowledge/resolve -> incident backend.

Required: incident ID/deduplication, delivery retries, scheduled escalation,
acknowledgement timeout, push token management, device revocation and audit log.
A push notification is not guaranteed to ring or bypass Do Not Disturb. iOS
critical alerts require platform entitlement and user permission; Android has
notification permission/channel and background restrictions. Evaluate existing
IRM mobile apps before building a bespoke pager. Implement neither custom mobile
backend nor unreliable alert-polling architecture as part of this ticket.

## Suggested rollout

1. Local dashboard/config validation (this repository).
2. Approve SMTP or Cloud Free/IRM, destination and data policy.
3. Instrument missing private worker/provider/export metrics in separate changes.
4. Deploy outbound-only collector; independent public probe/heartbeat.
5. Controlled synthetic email/recovery/escalation tests; then enable real alerts.
6. Re-evaluate mobile product after alert volume and escalation needs are known.
