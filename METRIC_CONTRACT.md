# Replisense Metric Contract

## Observed implementation (7 October 2026)

The sections below are a proposed future contract, NOT proof of exported metrics.
Current Node and Python HTTP metrics are:
`replisense_http_requests_total{service,method,route,status_code}` and
`replisense_http_request_duration_seconds_bucket` with those labels plus `le`.
Workers record `replisense_worker_heartbeat_timestamp_seconds`,
`replisense_worker_jobs_{started,completed,failed}_total` and
`replisense_worker_job_duration_seconds_bucket` in their own process registry.
Workers currently expose NO metrics HTTP endpoint. API scraping cannot see them.
Document-engine currently has `/health`, but NO `/metrics` endpoint.
The current Python gateway is one service on port 8002, not two separate QC/gateway processes.
No Gemini token/request/cost metrics exist in these inspected implementations.
Do not promise provider-cost alerts until inference instrumentation is added.
Use an `environment` target label (`local`, `qc`, `prod`) on all collected series.
Do not add tenant/user/document identifiers or source document contents to telemetry.

This file defines the Prometheus metric names the platform should emit so the dashboard and alert rules stay stable as services evolve.

## 1) HTTP services
Applies to:
- node-api
- doc-engine
- python-qc-agent
- any future internal API

Prefer a standard HTTP middleware that emits:
- `http_request_duration_seconds_bucket`
- `http_request_duration_seconds_sum`
- `http_request_duration_seconds_count`

Required labels:
- `method`
- `path`
- `status`
- `service`

Optional labels:
- `tenant`
- `route_group`

## 2) Worker metrics
Applies to:
- qc-worker
- doc-worker

Required metrics:
- `worker_heartbeat_unixtime_seconds` gauge
- `replisense_jobs_started_total{queue,job_type}` counter
- `replisense_jobs_completed_total{queue,job_type}` counter
- `replisense_jobs_failed_total{queue,job_type,error_code}` counter
- `replisense_jobs_retried_total{queue,job_type}` counter
- `replisense_queue_backlog{queue}` gauge
- `replisense_active_jobs{queue}` gauge
- `replisense_job_duration_seconds_bucket{queue,job_type}` histogram

Recommended labels:
- `service`
- `queue`
- `job_type`
- `tenant`
- `error_code` for failed events only

## 3) Business events
Use these for product-level observability.

Metric:
- `replisense_business_events_total{event_name,status,channel,service}` counter

Suggested event names:
- `qc_processed`
- `qc_failed`
- `document_preview_generated`
- `document_preview_failed`
- `document_revision_created`
- `editor_session_created`
- `alert_sent`
- `alert_delivery_failed`
- `login_succeeded`
- `login_failed`
- `password_reset_requested`
- `upload_completed`
- `upload_failed`

Status values:
- `success`
- `failed`
- `partial`

Channel examples:
- `email`
- `sms`
- `in_app`
- `webhook`
- `system`

## 4) Queue lag / freshness
Useful for knowing when the system is behind before the client notices.

Metrics:
- `replisense_oldest_pending_job_age_seconds{queue}` gauge
- `replisense_last_success_unixtime_seconds{service,operation}` gauge

## 5) Domain-specific metrics
Optional but strongly recommended.

QC:
- `replisense_qc_issues_found_total{severity}` counter
- `replisense_qc_runs_total{status}` counter
- `replisense_qc_processing_seconds_bucket{document_type}` histogram

Document processing:
- `replisense_doc_conversion_total{from_format,to_format,status}` counter
- `replisense_doc_conversion_seconds_bucket{from_format,to_format}` histogram
- `replisense_preview_regeneration_total{status}` counter

Alerts:
- `replisense_notifications_sent_total{channel,status}` counter
- `replisense_notification_latency_seconds_bucket{channel}` histogram

## Important rule
Keep metric names and labels stable. Add new labels only when needed. Avoid high-cardinality labels like raw document IDs, email addresses, or full URLs.
