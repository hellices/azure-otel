# 06 — Cilium Hubble network observability (ACNS)

Stage 06 enables **Cilium Hubble** on the AKS cluster via
**Azure Advanced Container Networking Services (ACNS)**.
This gives L3/L4/L7 network flow visibility, DNS monitoring, and
packet-drop analysis — all without sidecars, agents, or code changes.

> Korean version: [README_KR.md](./README_KR.md)

Since stage 01 already deploys AKS with `networkDataplane: cilium`,
the Cilium data plane is running. ACNS simply unlocks the Hubble
observability layer on top of it.

```
    ┌────────────────────────── AKS node ─────────────────────────┐
    │                                                             │
    │  app pod ◄──────────────────────► app pod                   │
    │       │           traffic              │                    │
    │       └──────────┐   ┌─────────────────┘                    │
    │                  ▼   ▼                                      │
    │          cilium-agent (eBPF)                                 │
    │                  │                                          │
    │    hubble_* metrics (:9965)    flow logs                    │
    │           │                      │                          │
    └───────────┼──────────────────────┼──────────────────────────┘
                │                      │
         ama-metrics scrape       hubble observe
                │
                ▼
     Azure Managed Prometheus  ──►  Azure Managed Grafana
```

## What Hubble shows

| Signal | Example |
|---|---|
| **L3/L4 flows** | Pod-to-pod, pod-to-external traffic with verdict (forwarded / dropped) |
| **L7 HTTP** | Request method, status code, latency per flow |
| **DNS** | Queries, responses, NXDOMAINs, response latency |
| **Packet drops** | Drop reason (policy denied, no route, conntrack, etc.) |
| **TCP flags** | SYN/FIN/RST counts per connection |

## Prerequisites

- AKS cluster from [01_deploy_to_aks](../01_deploy_to_aks) with `networkDataplane: cilium`.
- Azure CLI ≥ 2.78.0.

> **Pricing**: ACNS is a paid Azure add-on. Check
> [Azure ACNS pricing](https://azure.microsoft.com/pricing/details/azure-container-networking-services/)
> before enabling on production clusters.

## 1. Enable ACNS on the cluster

```bash
cd 06_hubble_network_observability    # from repo root

RG=$(azd env get-value AZURE_RESOURCE_GROUP --cwd ../01_deploy_to_aks)
AKS=$(azd env get-value AKS_NAME --cwd ../01_deploy_to_aks)

az aks update \
  --resource-group "$RG" \
  --name "$AKS" \
  --enable-acns
```

This enables:
- **Container Network Observability** — Hubble metrics + flow logs.
- **Container Network Security** — FQDN filtering, TLS inspection, mTLS (optional).
- Hubble metrics are **automatically scraped** by ama-metrics — no PodMonitor needed.

## 2. Verify Hubble is running

```bash
# Check cilium-agent pods are updated
kubectl -n kube-system get pods -l k8s-app=cilium -o wide

# Verify Hubble is enabled in cilium config
kubectl -n kube-system get cm cilium-config -o jsonpath='{.data.enable-hubble}'
# Should output: true
```

## 3. Install the Hubble CLI and observe flows

```bash
# macOS
brew install hubble

# Port-forward Hubble Relay
kubectl -n kube-system port-forward svc/hubble-relay 4245:80 &

# Check status
hubble status --server localhost:4245

# Observe all flows in the azure-otel namespace
hubble observe --server localhost:4245 -n azure-otel

# Filter: only HTTP flows
hubble observe --server localhost:4245 -n azure-otel --protocol http

# Filter: only DNS queries
hubble observe --server localhost:4245 -n azure-otel --type l7 --protocol dns

# Filter: dropped packets only
hubble observe --server localhost:4245 -n azure-otel --verdict DROPPED
```

## 4. Generate traffic and explore

```bash
AGFC=$(azd env get-value AGFC_URL --cwd ../01_deploy_to_aks 2>/dev/null || \
       kubectl get gateway azure-otel-gateway -n azure-otel \
         -o jsonpath='{.status.addresses[0].value}' 2>/dev/null)

# Generate cross-service traffic
for i in $(seq 1 30); do curl -s "http://${AGFC}/api/items" > /dev/null; done

# Watch the flows
hubble observe --server localhost:4245 -n azure-otel --last 50
```

You should see the full call chain: `AGFC → nodejs → python → spring`,
with HTTP method, status codes, and latency for each hop.

## 5. Import Grafana dashboards

ACNS integrates with Azure Managed Grafana automatically. Additionally, the
Cilium community provides dashboards:

| Dashboard | Grafana.com ID | Content |
|---|---|---|
| Hubble | 16613 | L7 flows, DNS, drops |
| Cilium Agent | 16611 | BPF map pressure, endpoint health |
| Cilium Operator | 16612 | Operator health, CRD sync |

To import manually:

```bash
grafana=$(azd env get-value GRAFANA_ENDPOINT --cwd ../01_deploy_to_aks)
token=$(az account get-access-token \
  --resource ce34e7e5-485f-4d76-964f-b3d2b16d1e4f \
  --query accessToken -o tsv)

# Download and import the Hubble dashboard
curl -sS "https://grafana.com/api/dashboards/16613/revisions/latest/download" \
  | jq '{dashboard: (. | .id = null), overwrite: true, folderId: 0}' \
  | curl -sS -X POST "$grafana/api/dashboards/db" \
    -H "Authorization: Bearer $token" \
    -H 'Content-Type: application/json' \
    --data-binary @-
```

## 6. Key Hubble metrics

All metrics are prefixed `hubble_` and scraped from port `9965`:

```promql
# HTTP request rate by source/destination
sum by (source, destination) (rate(hubble_http_requests_total{namespace="azure-otel"}[5m]))

# DNS query failures (NXDOMAIN, SERVFAIL)
sum by (query, rcode) (rate(hubble_dns_responses_total{rcode!="No Error"}[5m]))

# Packet drop rate by reason
sum by (reason) (rate(hubble_drop_total[5m]))

# TCP RST rate (connection issues)
sum by (source, destination) (rate(hubble_tcp_flags_total{flag="RST"}[5m]))
```

## 7. (Optional) Network policy auditing

With ACNS enabled, Cilium network policies get richer:

```bash
# See which flows are being denied by NetworkPolicy
hubble observe --server localhost:4245 \
  -n azure-otel --verdict DROPPED --type policy-verdict

# Export flows as JSON for audit
hubble observe --server localhost:4245 \
  -n azure-otel --output json > flows.json
```

## Cleanup

ACNS can be disabled without affecting application workloads:

```bash
az aks update \
  --resource-group "$RG" \
  --name "$AKS" \
  --disable-acns
```

## References

- [Azure ACNS overview](https://learn.microsoft.com/azure/aks/advanced-container-networking-services-overview)
- [Container Network Observability](https://learn.microsoft.com/azure/aks/container-network-observability-concepts)
- [Cilium Hubble documentation](https://docs.cilium.io/en/stable/observability/)
