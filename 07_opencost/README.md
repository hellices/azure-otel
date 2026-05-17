# 07 — OpenCost: Kubernetes cost observability (FinOps)

Deploys **OpenCost** (CNCF Graduated) to track per-pod, per-namespace, and
per-service cost allocation. Combines Kubernetes resource usage with Azure
billing data to answer "how much does this service cost per hour?"

> Korean version: [README_KR.md](./README_KR.md)

```
    kubelet ─── cadvisor metrics ──►  Prometheus (lightweight)
                                          │
    kube-state-metrics ────────────►      │
                                          │
                                          ▼
                                     OpenCost exporter
                                       │        │
                         usage metrics ─┘        └── Azure Billing API
                                                         (pricing data)
                                          │
                                          ▼
                                    OpenCost UI (:9090)
                                    Grafana dashboard
```

## Comparison with cloud billing

| Aspect | Azure Cost Management | OpenCost |
|---|---|---|
| Granularity | Resource-level (VM, disk) | Pod / container / namespace / label |
| Latency | 24–48 hours | Real-time (< 1 min) |
| Kubernetes awareness | Limited | Full (knows deployments, labels, owners) |
| Idle cost allocation | Not applicable | Splits unallocated resources by share |
| Cost | Free | Free (CNCF Graduated) |

## Prerequisites

- AKS cluster from [01_deploy_to_aks](../01_deploy_to_aks).
- Helm 3.

## 1. Deploy a lightweight Prometheus

OpenCost needs a Prometheus-compatible query endpoint for resource usage
metrics. Since Azure Managed Prometheus (AMA) requires Azure AD auth for
queries, we deploy a minimal in-cluster Prometheus that only scrapes
kubelet (cadvisor) and kube-state-metrics.

```bash
cd 07_opencost    # from repo root

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm upgrade --install prometheus prometheus-community/prometheus \
  -n prometheus-system --create-namespace \
  -f manifests/prometheus-values.yaml

kubectl -n prometheus-system rollout status deploy/prometheus-server --timeout=180s
```

## 2. (Optional) Configure Azure pricing

Without Azure pricing, OpenCost uses public on-demand list prices (reasonably
accurate for most use cases). For precise billing with your EA/MCA rates:

### A. Create a service principal

```bash
SUB_ID=$(az account show --query id -o tsv)

# Create custom role
az role definition create --role-definition '{
  "Name": "OpenCost Billing Reader",
  "Actions": [
    "Microsoft.Compute/virtualMachines/vmSizes/read",
    "Microsoft.Resources/subscriptions/locations/read",
    "Microsoft.Resources/providers/read",
    "Microsoft.ContainerService/containerServices/read",
    "Microsoft.Commerce/RateCard/read"
  ],
  "AssignableScopes": ["/subscriptions/'"$SUB_ID"'"]
}'

# Create SP and capture credentials
az ad sp create-for-rbac --name "OpenCostAccess" \
  --role "OpenCost Billing Reader" \
  --scopes "/subscriptions/$SUB_ID" \
  -o json > /tmp/opencost-sp.json
```

### B. Create the Kubernetes secret

```bash
TENANT=$(jq -r .tenant /tmp/opencost-sp.json)
APP_ID=$(jq -r .appId /tmp/opencost-sp.json)
PASSWORD=$(jq -r .password /tmp/opencost-sp.json)

kubectl create secret generic azure-service-key -n opencost \
  --from-literal=service-key.json="{
    \"subscriptionId\": \"$SUB_ID\",
    \"serviceKey\": {
      \"appId\": \"$APP_ID\",
      \"displayName\": \"OpenCostAccess\",
      \"password\": \"$PASSWORD\",
      \"tenant\": \"$TENANT\"
    }
  }"

rm -f /tmp/opencost-sp.json
```

## 3. Install OpenCost

```bash
helm repo add opencost https://opencost.github.io/opencost-helm-chart
helm upgrade --install opencost opencost/opencost \
  -n opencost --create-namespace \
  -f manifests/opencost-values.yaml

kubectl -n opencost rollout status deploy/opencost --timeout=180s
```

## 4. Access the UI

```bash
# Port-forward
kubectl -n opencost port-forward svc/opencost 9090:9090 &
open http://localhost:9090
```

Or expose via AGFC (demo only — add auth for production):

```bash
kubectl apply -f manifests/httproute.yaml
```

## 5. Import Grafana dashboard

```bash
grafana=$(azd env get-value GRAFANA_ENDPOINT --cwd ../01_deploy_to_aks)
token=$(az account get-access-token \
  --resource ce34e7e5-485f-4d76-964f-b3d2b16d1e4f \
  --query accessToken -o tsv)

curl -sS "https://grafana.com/api/dashboards/15714/revisions/latest/download" \
  | jq '{dashboard: (. | .id = null), overwrite: true, folderId: 0}' \
  | curl -sS -X POST "$grafana/api/dashboards/db" \
    -H "Authorization: Bearer $token" \
    -H 'Content-Type: application/json' \
    --data-binary @-
```

## 6. Verify cost data

```bash
# Query the OpenCost API for namespace costs (last 1 hour)
kubectl -n opencost port-forward svc/opencost 9003:9003 &

curl -s 'http://localhost:9003/allocation/compute?window=1h&aggregate=namespace' \
  | jq '.data[] | to_entries[] | {namespace: .key, cpuCost: .value.cpuCost, ramCost: .value.ramCost, totalCost: .value.totalCost}'
```

## 7. Key OpenCost metrics

OpenCost exports Prometheus metrics on `:9003/metrics`:

```promql
# Monthly cost by namespace
sum by (namespace) (opencost_allocation_cost_total{namespace="azure-otel"})

# CPU cost by container
opencost_container_cpu_cost_hourly{namespace="azure-otel"}

# Memory cost by container
opencost_container_memory_cost_hourly{namespace="azure-otel"}

# Total cluster cost
sum(opencost_allocation_cost_total)
```

## Cleanup

```bash
helm uninstall opencost -n opencost
helm uninstall prometheus -n prometheus-system
kubectl delete ns opencost prometheus-system
```

## References

- [OpenCost documentation](https://www.opencost.io/docs/)
- [OpenCost Azure integration](https://www.opencost.io/docs/configuration/azure)
- [CNCF OpenCost](https://www.cncf.io/projects/opencost/)
