# RepliSense monitoring

Work for RS-1124 (dashboards) and RS-1141 (alerting evaluation). Local checkout is
`replisense-monitoring`; its current Git remote is
`saikamal-replicantsys/replisense-monitoring`, not `Replicant-Systems/replicant-monitoring`.
Confirm repository ownership before pushing. Existing unrelated working-tree
changes are preserved. Grafana Cloud setup and its private QC collector are
documented in [QC Cloud operations](docs/QC-CLOUD-OPERATIONS.md). The QC folder,
email contact point and test send are configured; follow that runbook for live
telemetry validation and alert activation, not the local-only instructions below.

## Start locally

Copy `.env.example` to an ignored `.env`, replace the Grafana password, then run:

```powershell
docker compose up -d
```

Grafana: http://localhost:3001 (admin / your configured password).
Prometheus: http://localhost:9090. Alertmanager: http://localhost:9093.
All published ports bind to loopback only. Never expose these unauthenticated
Prometheus/Alertmanager endpoints publicly. Grafana is not a client-facing app.
The base stack has four services, bounded memory, rotated logs, pinned image
versions, 7-day / 1-GB Prometheus retention, and persistent local data volumes.
To stop: `docker compose down` (preserves data; do not add `-v` casually).

Open **Replisense / RepliSense QC Operations**. The environment selector keeps
local, QC and future production series separate. The older Platform Overview
is retained as a reference; panels for optional/non-QC services can have no data.
The old node dashboard JSON in the provisioning directory is a legacy import
artifact; only files under `grafana/dashboards` are automatically loaded.

Default collection:

| Target | Purpose | Current expectation |
|---|---|---|
| Local Node `:5000/metrics` | HTTP/application metrics | Needs running local Node; token required in production mode |
| Local Python `:8002/metrics` | HTTP/QC gateway metrics | One gateway, not a second QC-agent service |
| Local document-engine `:7001/health` | Health probe | No `/metrics` implementation exists |
| `https://qc.replicantsys.com/` | Public HTTPS availability | Expects 2xx; not a login or QC workflow test |
| QC `/api/auth/refresh` | Edge-to-Node reachability | Expects 401 without a cookie; not a database-readiness test |

Targets are in `prometheus/targets`. Add production public targets only after
`app.replicantsys.com` is deployed; do not alert on an intentionally offline demo.
Local services being down is normal when developers are not running them.
Local alerts are suppressed by the generated email configuration.
Missing metrics are **not** healthy/zero values. Worker counters live in separate
processes without scrape endpoints today. See METRIC_CONTRACT.md and
INSTRUMENTATION_GUIDE.md for the actual contract and remaining application work.

## Can a local dashboard read production/QC?

Yes. A dashboard and the collector do not have to be deployed together.
Prometheus stores **metrics**, not logs. Grafana queries Prometheus for metrics
and CloudWatch/Loki for logs. Website domains do not expose internal telemetry.

QC already configures CloudWatch collection from Docker JSON logs into
`/qc/replisense-qc/application` and bootstrap/certificate logs into
`/qc/replisense-qc/bootstrap`. Whether logs are actually arriving and which
production log groups exist must be verified before rollout.

For local CloudWatch access, create dedicated **read-only, temporary** monitoring
credentials in a separate folder as an AWS shared credentials file with profile
`[monitoring]`. Set `AWS_MONITORING_CREDENTIALS_DIR` and run:

```powershell
docker compose -f docker-compose.yml -f docker-compose.cloudwatch.yml up -d
```

Grafana Explore -> AWS QC CloudWatch -> Logs -> ap-south-1 -> the QC log group.
Use short lookback windows: Logs Insights scans are billed even when Grafana is
local. Do not mount your entire AWS folder or use the Terraform administrator.
Refresh temporary credentials before expiry. Prefer an assumed read-only role;
the account/IAM provisioning is deliberately outside this repository change.
See the IAM policy example under `docs` (not deployed).

For private Prometheus metrics, recommended hosted collection is a small
collector **inside each environment**, scraping its Docker/private network and
remote-writing outward over HTTPS to a central metrics store. No new inbound
EC2 ports, NAT or ALB are needed on the QC public-subnet host. A laptop can query
that store. Alternative: a temporary authenticated SSM/VPN tunnel to a private
collector, with explicit local Docker networking configuration. Do not open
Node/Python/Redis ports, publish `/metrics` via CloudFront, or use an origin secret
as a monitoring credential. Current Docker-only ports cannot simply be reached
by SSM forwarding to the EC2 loopback; a private collector or reviewed loopback
binding is required first. Neither is provisioned by this change.

## Email alerts

Prometheus rules are loaded and delivered to Alertmanager. The default receiver
is deliberately disabled, so starting locally does **not** send email. The
application's old observability webhook only logs and was not a delivery channel.

With your approved SMTP provider (STARTTLS port 587):

```powershell
python scripts/configure_email.py --smtp YOUR_SMTP_HOST:587 --sender YOUR_VERIFIED_SENDER --username YOUR_SMTP_USERNAME
```

Password is prompted without echo and written to ignored `secrets/smtp_password`.
Recipient defaults to `saikamal@replicantsys.com`. Restrict Windows folder ACLs
to your account; POSIX mode bits alone are insufficient on Windows.
On Linux, give the Alertmanager container user (image user `nobody`, typically
UID/GID 65534) read access to the password file using a dedicated group/ACL;
keep it inaccessible to other users. A host-owned mode-0600 file is not readable
by the non-root container until this is configured. Do not solve this by running
Alertmanager as root or making the secret world-readable.
Confirm sender/domain verification, provider limits, credentials and outbound SMTP access.
Do not use personal/application passwords where dedicated SMTP credentials exist.
The generated JSON is valid YAML and contains no password value.

Set `ALERTMANAGER_CONFIG=./alertmanager/email.local.yml` in `.env`, validate, and
recreate Alertmanager. Config changes are not automatically reloaded on file edit:

```powershell
docker compose up -d --force-recreate alertmanager
```

Alerts are grouped by environment/service, repeated every four hours and send
recovery emails. Local and monitoring-heartbeat alerts do not email. Test a
synthetic `MonitoringTest` alert with `environment=qc` through Alertmanager's
API only after notification approval; do NOT stop a client service as a test.
Check receipt, grouping, recovery, provider errors and Alertmanager notification
metrics. Production email delivery is **not configured or tested yet**.

Current rules cover scrape failures, HTTPS/status failures, certificate expiry,
low-traffic 5xx bursts, and future exported worker failures/stale heartbeat. Worker
rules cannot function until their endpoint exists. No-data/collector outages need
an independent always-on detector; `MonitoringAlwaysOn` is a heartbeat hook but
does not monitor itself. QC findings are NOT operational incidents.

## Always-on recommendation / cost

A local dashboard is fine for investigation, but a sleeping laptop cannot deliver
reliable alerts. Recommended: Grafana Cloud Free + IRM for always-on alert evaluation
and notifications, with an outbound-only collector in QC/prod, subject to approval
of the external telemetry destination. Do not export raw pharmaceutical documents,
prompts, names, user identities, tokens or request bodies. Start with sanitized
metrics; keep logs in AWS and inspect through local Grafana until log export is
approved. CloudWatch/SNS can remain an independent AWS infrastructure alarm path.

Grafana's pricing page on 7 October 2026 lists Free: 10k active metric series,
50 GB logs/month, 14-day retention and 3 active IRM users. Check current limits
and escalation-channel coverage before adopting. Free means $0 Grafana within
limits, not zero AWS ingest/query/egress costs. Pro starts at $19/month + usage.
No paid service subscription has been created.

| Option | Incremental fixed cost | Reliability |
|---|---|---|
| Local dashboards + existing CloudWatch | $0 new AWS compute | Investigation only; query/ingest charges remain |
| Cloud Free + small collector on existing host | $0 Grafana within limits; no new EC2 | Preferred; external telemetry approval required |
| Entire stack on existing QC EC2 | $0 additional EC2 if capacity fits | Shares QC failure domain; not sole alert source |
| Separate monitoring VM | New compute/disk/IPv4 costs | Independent host but unnecessary initially |

No NAT, ALB, ECS, paid endpoints, managed Grafana or managed Prometheus are needed
for the initial monitoring approach. Do not resize QC just for dashboards without
measuring collector memory/CPU and checking parsing peak capacity.

## Grafana OnCall / mobile

See docs/RS-1141-ALERTING.md. Do NOT introduce self-hosted Grafana OnCall OSS:
archived 24 March 2026; Cloud-connected phone/SMS/push support ended that day.
Evaluate maintained Grafana Cloud IRM instead. Email now, escalation later.

## Validate

```powershell
python scripts/build_dashboard.py
python -m unittest discover -s tests -v
docker compose config --quiet
docker run --rm --entrypoint promtool -v "${PWD}/prometheus:/etc/prometheus:ro" prom/prometheus:v3.11.2 check config /etc/prometheus/prometheus.yml
docker run --rm --entrypoint promtool -v "${PWD}/prometheus:/etc/prometheus:ro" prom/prometheus:v3.11.2 test rules /etc/prometheus/rule-tests.yml
docker run --rm --entrypoint amtool -v "${PWD}/alertmanager:/etc/alertmanager:ro" prom/alertmanager:v0.32.0 check-config /etc/alertmanager/alertmanager.yml
```

Sources:
- https://grafana.com/pricing/
- https://grafana.com/docs/oncall/latest/set-up/open-source/
- https://grafana.com/docs/grafana/latest/datasources/aws-cloudwatch/aws-authentication/
- https://prometheus.io/docs/alerting/latest/configuration/
