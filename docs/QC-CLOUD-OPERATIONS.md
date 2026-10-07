# QC Grafana Cloud operations

Scope: `qc.replicantsys.com`, AWS account `336934304897`, Mumbai EC2.
Stack `neatparlor1816`, folder `RepliSense QC`. No production/demo deployment,
new compute, public monitoring port, paid upgrade or Terraform apply.

## Architecture and privacy

Private Node `/metrics` and `/ready`, worker `:9102/metrics`, Python `/metrics`
-> one Alloy container -> Grafana Cloud Prometheus. Alloy probes public frontend/
API HTTPS, internal document-engine and Redis. Node readiness checks MongoDB
connection state and Redis readiness. Host CPU/memory/load use only three
read-only aggregate `/proc` files, not host process environments, the Docker
socket or host root filesystem.

Application code writes explicitly allowlisted events into separate operational
files. Alloy drops other schemas/events and **reconstructs** each outbound log
with just a fixed schema and bounded event name. Quantitative durations, findings
and provider usage are metrics. Raw logs remain AWS-only. Do not point Loki at
Docker's raw logs, document files or prompts. No tenant/document/run IDs,
filenames, exception bodies, secrets, prompts, responses or presigned URLs leave
the host through this collector. Findings are not application incidents.

Worker port 9102 is bearer authenticated and Docker-only; never publish it or
route metrics/readiness through CloudFront/Nginx. Collector ports are not published.

## Credentials

Administration helpers require Python and boto3. Install in a local virtual
environment with `python -m pip install -r requirements-admin.txt`; use that
environment's interpreter for the commands below. Collector credential loading
on EC2 uses the already-installed AWS CLI, not personal AWS keys.

Use a stack-scoped access policy `replisense-qc-telemetry` with ONLY `metrics:write`
and `logs:write`. Store its token directly as SecureString in `ap-south-1`:
`/replisense/qc/GRAFANA_CLOUD_TOKEN`. Interactive `gcx` OAuth is for administration,
not unattended ingestion; do not copy personal OAuth credentials onto EC2.

`python scripts/prepare_qc_credentials.py --execute` creates a dedicated
`/replisense/qc/OBSERVABILITY_TOKEN` SecureString only if missing. It never prints
or overwrites an existing secret. Existing QC instance IAM reads only its own
parameter prefix. These secrets are not Terraform values. The collector reads
only these two values into root-only `/run` files, never MongoDB/JWT/Gemini/origin
secrets. Rotate the ingestion token in SSM then restart the collector; coordinate
application/collector restarts when rotating the scrape token. No tokens in chat/Git.

## Application rollout

Node now exposes worker metrics, calls the previously unused heartbeat, corrects
double in-flight decrements, bounds unmatched route labels, records automatic
export attempts and emits production-safe events. Python records application
LLM invocations/reported usage/errors, safe events and post-routing templates.
No QC engine, quota or retry policy is changed. SDK-internal HTTP retries and
other apps sharing a Gemini key are not independently counted. Use a dedicated
provider project/key and provider billing reports for full cost attribution.

Build immutable SHA images from clean git archives, never a local directory
containing `.env` or documents. The Python observability-patch Dockerfile pins
the deployed base digest; verify pyproject.toml, uv.lock and Dockerfile.gateway
are unchanged from `8b275581be70c580c2a130d679652fe10403024f` before using it.
Normal subsequent releases use the normal gateway Dockerfile.

```powershell
python scripts/deploy_qc_application_observability.py --node-sha <full-SHA> --python-sha <full-SHA>
# Review preflight, then add --execute.
```

Checks account/QC tags and refuses an active QC job. Preserves document-engine,
backs up runtime files, uses the existing health/image-rollback helper. Frontend
does not change. One existing small Gemini deployment preflight request runs.
Runtime source edits affect Terraform user-data; a future plan may propose EC2
replacement due to `user_data_replace_on_change`. Review before any future apply.
This rollout synchronizes runtime files through SSM, not Terraform apply.

## Collector installation and recovery

```powershell
python scripts/deploy_qc_collector.py
# Review target and SecureString metadata, then add --execute.
```

SSM only, no SSH. Pinned Alloy, 384 MiB / 0.35 CPU limit, no public ports/socket,
reduced capabilities, read-only logs/configs and rotated collector logs. Systemd
refetches credentials after reboot and starts after `qc-application.service`.
Docker restart policy handles process restarts. Operational files rotate daily/
at 5 MiB, three rotations, seven-day max age; position/WAL has its own volume.
Reinstall from this repository after EC2 replacement. It is deliberately separate
from demo Terraform. Record the SSM command ID and poll the original command;
a waiter timeout is not proof of failure and must not trigger a duplicate deploy.

The original memory collector dropped its only InstanceId-only metric while
aggregation used the same dimensions. `repair_qc_host_metrics.py --execute`
removes that drop setting, backs up/reloads the existing agent configuration and
installs operational log rotation. No alarm/IAM/architecture change; one memory
custom metric was already part of the approved host monitoring design.

## Grafana dashboard and alerts

```powershell
python scripts/build_dashboard.py
python scripts/build_cloud_alerts.py
gcx resources validate -p grafana/cloud/folder.json
gcx resources push -p grafana/cloud/folder.json --dry-run
gcx resources push -p grafana/cloud/folder.json
gcx alert contact-points create -f grafana/cloud/email.json
```

Create the contact point once; inspect before update. Recipient
`saikamal@replicantsys.com`. AWS SNS is separately confirmed and remains an
independent fallback. After actual metric/log arrival, validate/push
`grafana/cloud/dashboard.json`, snapshot and inspect its PNG visually.

```powershell
python scripts/configure_cloud_alerts.py --execute --paused
# When all three private scrape targets are healthy:
python scripts/configure_cloud_alerts.py --execute
```

Eight QC-owned rules: missing collector/services, public HTTPS, dependencies,
heartbeat, HTTP 5xx, operational failures, Gemini billing/authentication, TLS
expiry. No-data means an outage for availability, but no error events is normal.
Previous rules/policy are backed up under ignored `artifacts/`. Other-team/default
routes remain unchanged; only the QC-labelled email route is added. Group wait
30s, group interval 10m, repeat interval 4h; send resolved notifications.
Do not enable real alerts before telemetry is verified.

Contact-point test uses the Grafana 13 API:

```powershell
gcx api /apis/notifications.alerting.grafana.app/v1beta1/namespaces/stacks-1859509/receivers/UmVwbGlTZW5zZSBRQyBlbWFpbA/test -X POST -d '@grafana/cloud/email-test.json'
```

API send success is not proof of inbox receipt; confirm with the recipient.
Then verify firing, routing and recovery with a labelled non-client synthetic
alert without stopping QC/using an allowance. Remote Grafana missing-series
evaluation and AWS EC2-status alarms cover collector/instance loss; on-host
probes alone do not. Hosted synthetic probes are an optional separate activation,
not assumed deployed or free at arbitrary check frequency.

## Costs and future scope

No additional always-on AWS compute/network. Small filtered telemetry should fit
Grafana Free, but measure ingestion/series and confirm the post-trial plan before
claiming zero cost. 60s scrapes, tiny event-only logs, no traces/profiles/client data.
Marginal ECR storage/outbound data can add charges; images share baseline layers.
Production needs its runtime confirmed and separate collector/config/token scope;
do not weaken origin security or mix `prod`/`qc` labels.

IRM is the maintained escalation/mobile direction; email contact points do not
require a roster. Invite the actual responder using their own account, verify
preferences and acknowledgement/escalation before claiming pager coverage.
Do not deploy archived OnCall OSS/build a custom mobile app for this rollout.
See `RS-1141-ALERTING.md`.

## Rollback

Stop only `replisense-qc-observability`; the application stays running. Restore
collector `.previous` files and validate before restart. Restore alert/policy
backups without overwriting unrelated updates. Restore saved runtime files and
prior Node/Python SHA release if needed. Never delete EIP, certificates, S3,
CloudFront, VPC, client data or Terraform state to roll back monitoring.
