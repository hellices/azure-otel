---
applyTo: "**/podmonitor.yaml,**/ama-metrics-prometheus-config.toml,02_metrics_via_podmonitor/**,**/recording*.yaml"
description: "Prometheus / Grafana Mimir / Azure Managed Prometheus overview, scraping, alerting, and recording rules."
---

# Metrics with Prometheus and Grafana

## Value proposition

Prometheus is an open-source monitoring and alerting toolkit for cloud-native environments. With Grafana Cloud Metrics (powered by Grafana Mimir) — or Azure Managed Prometheus in this repo — it becomes a fully managed, Prometheus-compatible service with long-term storage and global query performance.

**Key differentiators**: pull-based model, dimensional data model with labels, PromQL, automatic service discovery, scales to billions of active series.

## PromQL quick reference

### Instant vector selectors

```promql
http_requests_total
http_requests_total{job="api-server"}
http_requests_total{job="api-server", method="GET"}
http_requests_total{job=~"api.*", status=~"5.."}
http_requests_total{status!="200"}
```

### Range vectors and rates

```promql
rate(http_requests_total[5m])
increase(http_requests_total[1h])
irate(http_requests_total[5m])
rate(http_requests_total[5m] offset 5m)
```

### Aggregations

```promql
sum by (job) (rate(http_requests_total[5m]))
avg by (instance) (node_cpu_seconds_total)
topk(5, rate(http_requests_total[5m]))
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))
count(up{job="api"})
```

### Common patterns

```promql
# Error rate %
sum(rate(http_requests_total{status=~"5.."}[5m]))
  / sum(rate(http_requests_total[5m])) * 100

# CPU saturation %
100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# Predict disk full
predict_linear(node_filesystem_free_bytes[6h], 24*3600) < 0
```

## Metrics Drilldown

Queryless Prometheus exploration (Grafana 12+): browse metrics, smart segmentation, anomaly detection, telemetry pivoting.

## Alerting

- **Prometheus Alertmanager** — route, group, silence, deduplicate. Multi-destination routing (PagerDuty, Slack, Email, webhooks).
- **Grafana Alerting** — unified alerting across data sources, multi-dimensional alerts.
- **Recording rules** — pre-compute expensive PromQL for dashboard performance:

```yaml
groups:
  - name: api_rules
    rules:
      - record: job:http_requests:rate5m
        expr: sum by (job) (rate(http_requests_total[5m]))
```

## Architecture

- Pull-based scraping at configured intervals
- Service discovery (K8s, EC2, Consul)
- Push gateway for short-lived jobs
- Remote write/read to Mimir / Grafana Cloud / Azure Managed Prometheus
- Local TSDB

## References

- [Prometheus docs](https://prometheus.io/docs/)
- [PromQL reference](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Grafana Mimir](https://grafana.com/docs/mimir/latest/)
- [Azure Managed Prometheus](https://learn.microsoft.com/en-us/azure/azure-monitor/essentials/prometheus-metrics-overview)
