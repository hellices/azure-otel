# 08 — SLO monitoring with Sloth

Defines **Service Level Objectives** for the azure-otel sample apps and
generates Prometheus recording rules + multi-window multi-burn-rate alerts
using [Sloth](https://github.com/slok/sloth).

> Korean version: [README_KR.md](./README_KR.md)

```
SLO YAML ──► sloth generate ──► PrometheusRule YAML
                                       │
                                       ▼
                             Prometheus recording rules
                               slo:sli_error:ratio_rate5m
                               slo:sli_error:ratio_rate30m
                               slo:sli_error:ratio_rate1h
                               slo:error_budget:ratio
                               slo:current_burn_rate:ratio
                                       │
                                       ▼
                             Multi-burn-rate alerts
                               ┌─ Page (critical): 14.4× burn / 5m + 6× / 30m
                               └─ Ticket (warning):  3× burn / 2h + 1× / 1d
                                       │
                                       ▼
                             Grafana SLO dashboard (ID: 14348)
```

## SLO vs RED — they are different

| Concept | RED method | SLO monitoring |
|---|---|---|
| **What** | Metrics methodology (Rate, Errors, Duration) | Target framework + burn-rate alerting |
| **Answers** | "What is the current error rate?" | "Are we on track for 99.9% this month?" |
| **Output** | Dashboard panels | Error budget remaining, burn-rate alerts |
| **Alerts** | Threshold-based (e.g., error rate > 5%) | Budget-based (e.g., burning 14× too fast) |

SLO monitoring is built **on top of** RED metrics. This stage uses the same
`http_request_duration_seconds_*` metrics from step 02 to define SLOs.

## SLOs defined

| SLO | Objective | SLI (bad events) |
|---|---|---|
| `http-availability` | 99.9% | HTTP 5xx responses across all services |
| `http-latency-p99` | 99% | Requests slower than 500ms |
| `spring-availability` | 99.5% | HTTP 5xx from the Spring backend only |

## Prerequisites

- Stages 01 + 02 running (Prometheus metrics flowing).
- [Sloth CLI](https://github.com/slok/sloth/releases) installed:
  ```bash
  # macOS
  brew install slok/sloth/sloth
  # or binary download
  curl -sSL https://github.com/slok/sloth/releases/latest/download/sloth-darwin-arm64 \
    -o /usr/local/bin/sloth && chmod +x /usr/local/bin/sloth
  ```

## 1. Review the SLO definitions

```bash
cd 08_slo_monitoring    # from repo root
cat manifests/slo.yaml
```

Each SLO specifies:
- **objective**: target percentage (e.g., 99.9%)
- **error_query**: PromQL counting bad events
- **total_query**: PromQL counting all events
- **alerting**: page (critical, fast burn) and ticket (warning, slow burn) alerts

## 2. Generate Prometheus rules

```bash
sloth generate -i manifests/slo.yaml -o manifests/generated-rules.yaml
```

This produces:
- **Recording rules**: SLI error ratios at 7 time windows (5m → 30d), error
  budget remaining, current burn rate.
- **Alert rules**: 4 multi-window multi-burn-rate alert conditions per SLO,
  following the Google SRE workbook pattern.

## 3. Apply the rules

### Option A: In-cluster Prometheus (with Prometheus Operator)

If you have the Prometheus Operator running (e.g., from step 07's Prometheus):

```bash
kubectl apply -f manifests/generated-rules.yaml
```

### Option B: Azure Managed Prometheus (AMW)

AMW uses Azure Monitor rule groups, not PrometheusRule CRDs. Convert:

```bash
RG=$(azd env get-value AZURE_RESOURCE_GROUP --cwd ../01_deploy_to_aks)
AMW=$(azd env get-value MONITOR_WORKSPACE_NAME --cwd ../01_deploy_to_aks)
AMW_ID=$(az monitor account show -g "$RG" -n "$AMW" --query id -o tsv)

# Extract rule groups from generated YAML and create AMW rule group
# (manual step — see Azure docs for prometheus-rule-group CLI)
az monitor account prometheus-rule-group create \
  --resource-group "$RG" \
  --rule-group-name "slo-azure-otel" \
  --scopes "$AMW_ID" \
  --rules @manifests/generated-rules.yaml \
  --interval "PT1M" \
  --enabled true
```

> **Note**: The generated YAML may need format conversion for the
> `az monitor account prometheus-rule-group` command. See
> [Azure Prometheus rule groups](https://learn.microsoft.com/azure/azure-monitor/essentials/prometheus-rule-groups).

## 4. Import Grafana dashboard

```bash
grafana=$(azd env get-value GRAFANA_ENDPOINT --cwd ../01_deploy_to_aks)
token=$(az account get-access-token \
  --resource ce34e7e5-485f-4d76-964f-b3d2b16d1e4f \
  --query accessToken -o tsv)

# Sloth SLO dashboard
curl -sS "https://grafana.com/api/dashboards/14348/revisions/latest/download" \
  | jq '{dashboard: (. | .id = null), overwrite: true, folderId: 0}' \
  | curl -sS -X POST "$grafana/api/dashboards/db" \
    -H "Authorization: Bearer $token" \
    -H 'Content-Type: application/json' \
    --data-binary @-
```

The dashboard shows:
- **Error budget remaining** per SLO (e.g., "72% of monthly budget left")
- **Burn rate** over time (current vs sustainable)
- **SLO compliance** (are you meeting your objective?)
- **Time until budget exhaustion** at current burn rate

## 5. Verify

```bash
# Generate some traffic
AGFC=$(azd env get-value AGFC_URL --cwd ../01_deploy_to_aks 2>/dev/null || \
       kubectl get gateway azure-otel-gateway -n azure-otel \
         -o jsonpath='{.status.addresses[0].value}' 2>/dev/null)

for i in $(seq 1 50); do curl -s "http://${AGFC}/api/items" > /dev/null; done

# Check recording rules are producing data (wait 2-3 minutes)
# In Grafana, query:
#   slo:sli_error:ratio_rate5m{sloth_service="azure-otel-apps"}
#   slo:error_budget:ratio{sloth_service="azure-otel-apps"}
#   slo:current_burn_rate:ratio{sloth_service="azure-otel-apps"}
```

## 6. Understanding the alerts

Sloth generates **multi-window multi-burn-rate** alerts per Google's SRE workbook:

| Alert | Condition | Meaning |
|---|---|---|
| **Page** (critical) | 14.4× burn over 5m **AND** 6× over 30m | Major incident — you'll exhaust the monthly budget in < 1 hour |
| **Page** (critical) | 6× burn over 30m **AND** 3× over 1h | Significant issue — budget exhaustion in < 4 hours |
| **Ticket** (warning) | 3× burn over 2h **AND** 1× over 1d | Degradation — budget exhaustion in < 10 days |
| **Ticket** (warning) | 1× burn over 6h **AND** 0.5× over 3d | Slow burn — budget on pace to exhaust within the window |

## 7. Customizing SLOs

Edit `manifests/slo.yaml` and re-generate:

```bash
# Change objective from 99.9% to 99.95%
# Add new SLO for a different service
vim manifests/slo.yaml

# Regenerate
sloth generate -i manifests/slo.yaml -o manifests/generated-rules.yaml

# Re-apply
kubectl apply -f manifests/generated-rules.yaml
```

## References

- [Sloth documentation](https://sloth.dev/)
- [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
- [OpenSLO specification](https://openslo.com/)
- [Azure Prometheus rule groups](https://learn.microsoft.com/azure/azure-monitor/essentials/prometheus-rule-groups)
