# Replisense Monitoring

This repository contains the complete infrastructure to monitor the Replisense backend using **Prometheus** and **Grafana**, containerized using **Docker Compose**.

---

## 🔧 Architecture Overview

![Monitoring Architecture](./assets/replisense%20monitoring%20architecture.png)

This monitoring system includes:

- **Prometheus** – pulls and stores metrics from services like our Node.js backend.
- **Grafana** – visualizes data from Prometheus via dashboards.
- **Alertmanager** (future scope) – used to send notifications when alerts are triggered.
- **Docker Compose** – simplifies deployment of the stack.

---

## 📁 Folder Structure

```
replisense-monitoring/
├── docker-compose.yml                 # Defines Prometheus + Grafana containers
├── prometheus/
│   └── prometheus.yml                # Scrape config for Prometheus
├── grafana/
│   └── provisioning/
│       ├── datasources/
│       │   └── prometheus.yml        # Auto-loads Prometheus data source
│       └── dashboards/
│           └── node-backend-dashboard.json # Pre-built Grafana dashboard
├── replisense monitoring architecture.png   # Architecture diagram
└── README.md
```

---

## 🐳 Quick Start

### Prerequisites
- Docker Desktop installed and running
- Backend app running at `http://localhost:5000/metrics`

### Start Monitoring Stack

```bash
docker compose up -d
```

- Prometheus UI: [http://localhost:9090](http://localhost:9090)
- Grafana UI: [http://localhost:3001](http://localhost:3001)

---

## 🔍 Metrics Source (Backend Setup)

The Node.js app uses [`express-prom-bundle`](https://www.npmjs.com/package/express-prom-bundle):

```js
const promBundle = require('express-prom-bundle');
app.use(promBundle({ metricsPath: '/metrics', collectDefaultMetrics: true }));
```

---

## 📈 Grafana Dashboard Highlights

- ✅ Total HTTP requests
- 📊 Request rate by route & status
- 🐢 Latency (p50, p95)
- 📦 Request/response sizes
- 🛠 Fully customizable and extendable

Preloaded from `grafana/provisioning/dashboards/node-backend-dashboard.json`.

---

## 🚨 Alerting Rules (Manual Setup)

> You can configure alerts via the Grafana UI.

**Examples:**

| Condition | PromQL |
|----------|--------|
| High 5xx Error Rate | `sum(rate(http_request_duration_seconds_count{status=~"5.."}[1m])) > 1` |
| High Latency (p95) | `histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le)) > 2` |
| Backend Down | `up{job="replisense-backend"} == 0` |

---

## 🛠 Testing & Debugging

Trigger metrics by calling backend routes:

```bash
curl http://localhost:5000/api/projects
curl http://localhost:5000/api/devices
```

Then visit Prometheus or Grafana to confirm live data.

---

## Future Enhancements

- [ ] Integrate **Alertmanager** for Slack/email alerts
- [ ] Add **Node Exporter** for server metrics
- [ ] Enable **long-term storage** via Thanos or Cortex

---

## 🛠️ Built With

- [Prometheus](https://prometheus.io/)
- [Grafana](https://grafana.com/)
- [Docker Compose](https://docs.docker.com/compose/)
- [express-prom-bundle](https://www.npmjs.com/package/express-prom-bundle)

---

## 📬 Support

For issues or improvements, please open an [issue](https://github.com/saikamal-replicantsys/replisense-monitoring/issues).
