---
applyTo: "**/dashboards/**/*.json,**/podmonitor.yaml,**/recording*.yaml,**/*.promql"
description: "Write, validate and optimise PromQL: rates, aggregation, histogram quantiles, recording rules, cardinality."
---

# PromQL Query Patterns

PromQL returns either an **instant vector** (one value per label set), a **range vector** (sliding window of samples), or a **scalar**.

**Golden rule:** `rate()` and `increase()` always require a range vector. The range must be at least 4× the scrape interval to avoid gaps. For a 60s scrape interval, use `[5m]` minimum.

---

## Rate and counter queries

```promql
rate(http_requests_total[5m])

# CORRECT: rate first, then aggregate
sum(rate(http_requests_total{job="api"}[5m])) by (status_code)

# WRONG: sum destroys counter monotonicity
# sum(http_requests_total) by (status_code)   -- never rate() this

increase(http_requests_total[1h])
```

**`irate` vs `rate`:** `rate()` smooths over the window — use for dashboards/alerts. `irate()` uses the last two samples — only when you need to capture spikes. Never use `irate()` for alerting.

---

## Filtering with label matchers

```promql
http_requests_total{job="api", status_code="200"}
http_requests_total{status_code=~"5.."}
http_requests_total{status_code!~"2.."}
http_requests_total{env=~"staging|production"}
```

---

## Aggregation operators

Always aggregate after `rate()`:

```promql
sum(rate(http_requests_total[5m])) by (service)
avg(node_cpu_seconds_total{mode="idle"}) by (instance)

histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le, service)
)

topk(5, sum(rate(http_requests_total[5m])) by (service))
count(count(up) by (job)) by ()
```

**`without` vs `by`:**

```promql
sum(rate(http_requests_total[5m])) by (service, status_code)
sum(rate(http_requests_total[5m])) without (instance, pod)
```

---

## Histogram quantiles

**Classic histograms** (`_bucket` suffix):

```promql
histogram_quantile(0.99,
  sum(rate(http_request_duration_seconds_bucket{job="api"}[5m])) by (le)
)
```

**Common mistake:** forgetting `by (le)` in the inner aggregation drops bucket boundaries — `histogram_quantile` returns wrong values or NaN.

**Native histograms** (Prometheus 2.40+):

```promql
histogram_quantile(0.95, sum(rate(http_request_duration_seconds[5m])))
```

---

## Ratio and error rate

```promql
sum(rate(http_requests_total{status_code=~"5.."}[5m]))
/
sum(rate(http_requests_total[5m]))

# Avoid divide-by-zero
sum(rate(errors_total[5m]))
/
(sum(rate(requests_total[5m])) > 0)
```

---

## Absence and staleness

```promql
absent(up{job="api"})
changes(up{job="api"}[5m]) == 0
count_over_time(up{job="api"}[5m]) > 0
```

---

## Time functions and offsets

```promql
rate(http_requests_total[5m]) - rate(http_requests_total[5m] offset 1h)
rate(http_requests_total[5m]) / rate(http_requests_total[5m] offset 1d)
predict_linear(node_filesystem_avail_bytes[1h], 2 * 3600)
```

---

## Recording rules

Pre-compute expensive queries to speed dashboards and reduce query load.

```yaml
groups:
  - name: http_request_rates
    interval: 1m
    rules:
      - record: job:http_requests_total:rate5m
        expr: sum(rate(http_requests_total[5m])) by (job)

      - record: job:http_errors:ratio5m
        expr: |
          sum(rate(http_requests_total{status_code=~"5.."}[5m])) by (job)
          /
          sum(rate(http_requests_total[5m])) by (job)

      - record: job:http_request_duration_p95:rate5m
        expr: |
          histogram_quantile(0.95,
            sum(rate(http_request_duration_seconds_bucket[5m])) by (le, job)
          )
```

**Naming convention:** `<aggregation_level>:<metric_name>:<operation_and_window>`

---

## SLO queries

```promql
1 - (
  sum(increase(http_requests_total{status_code=~"5.."}[30d]))
  /
  sum(increase(http_requests_total[30d]))
)

# Burn rate (alert when burning > 14.4× allowed)
(
  sum(rate(http_requests_total{status_code=~"5.."}[1h]))
  /
  sum(rate(http_requests_total[1h]))
)
/
(1 - 0.999)
```

---

## Cardinality and performance

High-cardinality labels (UUIDs, user IDs, URLs) make queries slow and storage expensive.

```promql
topk(10, count by (__name__)({__name__=~".+"}))
count(http_requests_total)
count(count by (user_id)(http_requests_total))
```

**Rules:**
- Never put high-cardinality values (request IDs, user IDs, emails) in label values
- Group URLs into route patterns: `/api/users/123` → `/api/users/{id}`
- Use `relabel_configs` to drop labels at scrape time

```alloy
prometheus.scrape "api" {
  targets = [...]
  rule {
    source_labels = ["user_id"]
    action        = "labeldrop"
  }
}
```

---

## Common patterns

```promql
# Service availability
avg_over_time(up{job="api"}[5m]) < 0.9

# Disk filling up
predict_linear(node_filesystem_avail_bytes{mountpoint="/"}[1h], 4 * 3600) < 0

# Throughput spike (current > 3× 1h average)
rate(http_requests_total[5m])
>
3 * avg_over_time(rate(http_requests_total[5m])[1h:5m])
```

---

## References

- [Prometheus querying basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Prometheus best practices](https://prometheus.io/docs/practices/naming/)
- [Grafana Mimir docs](https://grafana.com/docs/mimir/latest/)
