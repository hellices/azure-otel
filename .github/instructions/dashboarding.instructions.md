---
applyTo: "**/dashboards/**/*.json,**/*dashboard*.json"
description: "Grafana dashboard JSON authoring: panels, variables, transformations, links, annotations, and the dashboards API."
---

# Grafana Dashboard Authoring

Dashboards are JSON documents with panels, variables, time range, and refresh settings. Understanding the schema lets you programmatically create and modify dashboards via the API.

---

## Dashboard JSON structure

```json
{
  "title": "My Dashboard",
  "uid": "my-dashboard-v1",
  "tags": ["service", "production"],
  "time": { "from": "now-1h", "to": "now" },
  "refresh": "30s",
  "timezone": "browser",
  "schemaVersion": 41,
  "templating": { "list": [] },
  "annotations": { "list": [] },
  "panels": []
}
```

- `uid` — stable identifier; keep short and meaningful
- `schemaVersion` — `41` for Grafana 11+
- `time.from` / `to` — supports relative (`now-1h`) and absolute ISO timestamps
- `refresh` — `"30s"`, `"1m"`, `""` (off)

---

## Panel types

| Panel | Use case |
|---|---|
| **Time series** | Default for any metric over time |
| **Stat** | Single current value with optional sparkline |
| **Gauge** | Percent or value against min/max |
| **Bar gauge** | Compare multiple values side by side |
| **Table** | Multi-column data |
| **Heatmap** | Distribution over time |
| **Logs** | Loki streams |
| **Traces** | Tempo trace search |
| **Text** | Markdown documentation |
| **Node graph** | Service dependency graphs |

---

## Panel JSON

```json
{
  "id": 1,
  "type": "timeseries",
  "title": "Request Rate",
  "gridPos": { "x": 0, "y": 0, "w": 12, "h": 8 },
  "datasource": { "type": "prometheus", "uid": "${datasource}" },
  "targets": [
    {
      "expr": "sum(rate(http_requests_total{job=\"$job\"}[5m])) by (status_code)",
      "legendFormat": "{{status_code}}",
      "refId": "A"
    }
  ],
  "fieldConfig": {
    "defaults": {
      "unit": "reqps",
      "thresholds": {
        "mode": "absolute",
        "steps": [
          { "color": "green", "value": null },
          { "color": "yellow", "value": 1000 },
          { "color": "red", "value": 5000 }
        ]
      }
    },
    "overrides": []
  },
  "options": {
    "legend": { "calcs": ["mean", "max", "last"], "displayMode": "table", "placement": "bottom" },
    "tooltip": { "mode": "multi", "sort": "desc" }
  }
}
```

`gridPos`: 24-column grid. Common widths: full=24, half=12, third=8, quarter=6. Height in grid units (≈30px each).

---

## Useful units

```
# Rates
reqps, ops, Bps, percentunit
# Storage
bytes, decbytes
# Time
ms, s, dtdurationms
# Counts
short, none
```

Full list in **Panel > Field > Unit** dropdown.

---

## Template variables

**Query variable:**

```json
{
  "name": "job",
  "type": "query",
  "datasource": { "type": "prometheus", "uid": "prometheus" },
  "query": { "query": "label_values(up, job)", "refId": "A" },
  "refresh": 2,
  "includeAll": true,
  "multi": true,
  "label": "Service"
}
```

**Constant:**

```json
{ "name": "cluster", "type": "constant", "query": "production", "label": "Cluster" }
```

**Datasource:**

```json
{ "name": "datasource", "type": "datasource", "pluginId": "prometheus", "label": "Prometheus" }
```

**Use in queries:** multi-value variables expand to regex OR — `$job = ["api","worker"]` becomes `job=~"api|worker"`.

```promql
rate(http_requests_total{job=~"$job"}[5m])
```

**Chained variable:**

```json
{ "name": "pod", "query": "label_values(kube_pod_info{namespace=\"$namespace\"}, pod)" }
```

---

## Transformations

Run client-side after queries, reshape without changing PromQL.

```json
"transformations": [
  { "id": "merge", "options": {} },
  {
    "id": "organize",
    "options": {
      "renameByName": { "Value #A": "Request Rate", "Value #B": "Error Rate" },
      "excludeByName": { "Time": true }
    }
  },
  {
    "id": "calculateField",
    "options": {
      "alias": "Error %",
      "mode": "reduceRow",
      "reduce": { "reducer": "last" },
      "binary": { "left": "errors", "right": "total", "operator": "/" }
    }
  },
  {
    "id": "filterByValue",
    "options": {
      "filters": [{ "fieldName": "Error %", "config": { "id": "greater", "options": { "value": 0.01 } } }],
      "type": "include",
      "match": "any"
    }
  }
]
```

Common IDs: `merge`, `organize`, `rename`, `calculateField`, `filterByValue`, `groupBy`, `sortBy`, `limit`, `labelsToFields`, `seriesToRows`, `partitionByValues`.

---

## Dashboard linking

**Panel link:**

```json
"links": [
  { "title": "Go to details",
    "url": "/d/details-dashboard?var-service=${__field.labels.service}",
    "targetBlank": false }
]
```

**Built-in variables:** `${__value.raw}`, `${__field.labels.job}`, `${__url.params}`, `${__from}` / `${__to}`.

---

## Annotations

**Loki:**

```json
{
  "datasource": { "type": "loki", "uid": "loki" },
  "expr": "{job=\"deployments\"} |= \"deployed\"",
  "name": "Deployments",
  "iconColor": "blue",
  "titleFormat": "{{service}} deployed",
  "textFormat": "{{version}} by {{author}}"
}
```

**Prometheus:**

```json
{
  "datasource": { "type": "prometheus", "uid": "prometheus" },
  "expr": "changes(kube_deployment_status_observed_generation{namespace=\"production\"}[5m]) > 0",
  "step": "60s",
  "name": "Deployments",
  "iconColor": "blue",
  "titleFormat": "Deploy: {{deployment}}"
}
```

---

## Dashboard via API

```bash
# Create or update
curl -s -X POST \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  "https://myorg.grafana.net/api/dashboards/db" \
  -d '{ "dashboard": { ... }, "folderUid": "my-folder", "overwrite": true }'

# Get by UID
curl -s -H "Authorization: Bearer <API_KEY>" \
  "https://myorg.grafana.net/api/dashboards/uid/my-dashboard-v1" | jq '.dashboard'

# Search
curl -s -H "Authorization: Bearer <API_KEY>" \
  "https://myorg.grafana.net/api/search?query=kubernetes&type=dash-db"
```

---

## References

- [Grafana dashboards](https://grafana.com/docs/grafana/latest/dashboards/)
- [Panel types](https://grafana.com/docs/grafana/latest/panels-visualizations/)
- [Dashboard HTTP API](https://grafana.com/docs/grafana/latest/developers/http_api/dashboard/)
- [Variables](https://grafana.com/docs/grafana/latest/dashboards/variables/)
- [Transformations](https://grafana.com/docs/grafana/latest/panels-visualizations/query-transform-data/transform-data/)
