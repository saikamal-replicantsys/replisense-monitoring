# Instrumentation Guide

## QC instrumentation update (7 October 2026)

The Node/Python branches now implement private worker metrics/heartbeat,
in-flight accounting, bounded route labels, automatic export telemetry, LLM
invocation/token/error telemetry and allowlisted events. See
`docs/QC-CLOUD-OPERATIONS.md` for rollout/verification. Source changes alone are
not proof deployed endpoints are being scraped. Queue age/depth and conversion
metrics remain follow-up items; SDK-internal retries/other apps sharing a model
key are not independently visible.

## Original gap checklist / implementation context

Existing Node/Python HTTP instrumentation should be reused, not replaced with
another middleware. See METRIC_CONTRACT.md for actual names/labels.

1. Expose the QC worker registry on a private Docker-network-only port. Include
   heartbeat, failures/retries, queue length/oldest waiting age and export failures.
   Do not publish it on EC2 or CloudFront; one collector scrapes the container.
2. Document-engine has only a health endpoint. Use health probes now, add bounded
   conversion counters/duration/error codes later.
3. Add bounded provider/model/outcome labels for Gemini requests, retries, token
   usage, throttling and credential/billing errors. Never log keys or prompts.
4. Node's current in-flight gauge decrements on both `finish` and `close` and may
   go negative. Do not use it as an alert until lifecycle accounting is corrected.
5. Raw fallback request paths in Node/Python can produce unbounded labels. Normalize
   unmatched routes before enabling remote telemetry.
6. Review default Python process/GC metrics and all labels before remote-write;
   redact document names, tenant identity, request bodies, prompts and exception
   details. These changes are NOT implemented by the monitoring repository.

Do not treat an empty worker panel as a successful worker health check.

This guide shows the minimum code-level instrumentation needed to make the observability stack truly useful.

## Node API
If We already use `express-prom-bundle`, keep it, but add a stable `service` label and route normalization.

Example:
```js
const promBundle = require("express-prom-bundle");

const metricsMiddleware = promBundle({
  metricsPath: "/metrics",
  includeMethod: true,
  includePath: true,
  includeStatusCode: true,
  promClient: {
    collectDefaultMetrics: {},
  },
  customLabels: {
    service: "node-api",
  },
  transformLabels(labels) {
    labels.service = "node-api";
  },
});

app.use(metricsMiddleware);
```

## Python QC Agent
For FastAPI, use `prometheus_client` and expose `/metrics`.

Suggested metrics:
- HTTP request histogram
- QC runs total
- QC processing duration histogram
- QC issues found counter by severity
- Business events counter

## Workers
Workers need a small HTTP server just for metrics.

In Node worker processes, expose metrics on a sidecar port, for example 9102 / 9103.

Required:
- heartbeat gauge updated every few seconds
- queue backlog gauge
- jobs started/completed/failed counters
- job duration histogram
- retry counter
- oldest pending job age gauge

## Business events
Emit one common metric from all services:
```text
replisense_business_events_total{event_name,status,channel,service}
```

Examples:
- `qc_processed`
- `document_preview_generated`
- `alert_sent`
- `alert_delivery_failed`
- `upload_completed`
- `login_failed`

## Cardinality rules
Never use labels like:
- raw document id
- user email
- full file path
- full exception text
- JWT subject

Prefer these instead:
- `service`
- `queue`
- `status`
- `severity`
- `job_type`
- `channel`
- `error_code`
- `operation`
