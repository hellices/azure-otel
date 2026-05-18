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
    │         hubble flow logs     gRPC metrics (:9965)           │
    │           │                      │                          │
    └───────────┼──────────────────────┼──────────────────────────┘
                │                      │
        hubble observe            Prometheus scrape
        (via cilium-agent)        (gRPC server stats)
```

> **Note**: ACNS enables Hubble **flow observation** (the `hubble observe`
> command), but does NOT automatically enable `hubble_*` Prometheus metrics
> like `hubble_flows_processed_total` or `hubble_dns_responses_total`.
> The `hubble-metrics` config key is empty by default on AKS.
> Port 9965 exposes gRPC server stats only.

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
- **Container Network Observability** — Hubble flow logs via `hubble observe`.
- **Container Network Security** — FQDN filtering, TLS inspection, mTLS (optional).

## 2. Verify Hubble is running

```bash
# Check cilium-agent pods are updated (should show 3/3 Running)
kubectl -n kube-system get pods -l k8s-app=cilium -o wide

# Verify Hubble is enabled in cilium config
kubectl -n kube-system get cm cilium-config -o jsonpath='{.data.enable-hubble}'
# Should output: true

# Verify Hubble Relay is running (service port 443 → container port 4245)
kubectl -n kube-system get svc hubble-relay
kubectl -n kube-system get pods -l k8s-app=hubble-relay
```

<!-- DEBUG: If cilium pods aren't restarting after --enable-acns,
     the ACNS feature may still be rolling out. Wait 2-3 min.
     Check: az aks show -g $RG -n $AKS \
       -\-query "networkProfile.advancedNetworking" -o json -->

## 3. Observe flows (recommended: via cilium-agent exec)

The simplest way to observe flows on AKS — no TLS certs needed:

```bash
# Pick any cilium-agent pod
CILIUM_POD=$(kubectl -n kube-system get pods -l k8s-app=cilium \
  -o jsonpath='{.items[0].metadata.name}')

# Observe all flows in the azure-otel namespace
kubectl -n kube-system exec "$CILIUM_POD" -c cilium-agent -- \
  hubble observe -n azure-otel --last 20

# Filter: only dropped packets
kubectl -n kube-system exec "$CILIUM_POD" -c cilium-agent -- \
  hubble observe -n azure-otel --verdict DROPPED
```

<!-- DEBUG: If "hubble observe" returns nothing, generate traffic first (step 4)
     or check if the cilium-agent has finished restarting. -->

### 3b. (Alternative) Local hubble CLI with TLS certs

Hubble Relay uses **mTLS**. To connect from your machine:

```bash
brew install hubble

# Extract client TLS certs from the cluster
mkdir -p /tmp/hubble-tls
kubectl -n kube-system get secret hubble-relay-client-certs \
  -o jsonpath='{.data.ca\.crt}' | base64 -d > /tmp/hubble-tls/ca.crt
kubectl -n kube-system get secret hubble-relay-client-certs \
  -o jsonpath='{.data.tls\.crt}' | base64 -d > /tmp/hubble-tls/tls.crt
kubectl -n kube-system get secret hubble-relay-client-certs \
  -o jsonpath='{.data.tls\.key}' | base64 -d > /tmp/hubble-tls/tls.key

# Port-forward to the relay pod (not svc — avoids port mapping issues)
RELAY_POD=$(kubectl -n kube-system get pods -l k8s-app=hubble-relay \
  -o jsonpath='{.items[0].metadata.name}')
kubectl -n kube-system port-forward "pod/$RELAY_POD" 4245:4245 &

# Connect with TLS
hubble observe --server localhost:4245 \
  --tls --tls-ca-cert-files /tmp/hubble-tls/ca.crt \
  --tls-client-cert-file /tmp/hubble-tls/tls.crt \
  --tls-client-key-file /tmp/hubble-tls/tls.key \
  --tls-server-name "*.hubble-relay.cilium.io" \
  -n azure-otel
```

<!-- DEBUG: If "DeadlineExceeded" on hubble status/observe with TLS certs,
     verify openssl handshake works first:
       openssl s_client -connect localhost:4245 \
         -cert /tmp/hubble-tls/tls.crt -key /tmp/hubble-tls/tls.key \
         -CAfile /tmp/hubble-tls/ca.crt \
         -servername "*.hubble-relay.cilium.io" </dev/null
     If TLS handshake succeeds but gRPC fails, it's a hubble CLI version
     compatibility issue. Use the cilium-agent exec method instead. -->

## 4. Generate traffic and explore

```bash
AGFC=$(kubectl get gateway azure-otel-gw -n azure-otel \
  -o jsonpath='{.status.addresses[0].value}')

# Generate cross-service traffic
for i in $(seq 1 30); do curl -s "http://${AGFC}/api/items" > /dev/null; done

# Watch the flows (via cilium-agent — simplest method)
CILIUM_POD=$(kubectl -n kube-system get pods -l k8s-app=cilium \
  -o jsonpath='{.items[0].metadata.name}')
kubectl -n kube-system exec "$CILIUM_POD" -c cilium-agent -- \
  hubble observe -n azure-otel --last 50
```

You should see the full call chain: `AGFC → nodejs → python → spring`,
with HTTP method, status codes, and latency for each hop.

## 5. Deploy Hubble UI

Hubble UI provides a web-based flow visualization. It connects to
Hubble Relay using mTLS (certs from `hubble-relay-client-certs` secret).

```bash
kubectl apply -f manifests/hubble-ui.yaml
kubectl -n kube-system rollout status deploy/hubble-ui --timeout=90s
```

Expose via AGFC gateway at `/hubble`:

```bash
kubectl apply -f manifests/httproute.yaml

# Verify route is accepted
kubectl get httproute hubble-ui -n azure-otel
```

Access:
```bash
AGFC=$(kubectl get gateway azure-otel-gw -n azure-otel \
  -o jsonpath='{.status.addresses[0].value}')
echo "http://${AGFC}/hubble"
```

<!-- DEBUG: If 503 → AGFC health probe hasn't converged yet (wait 30s).
     If 404 → nginx config not mounted (check ConfigMap hubble-ui-nginx).
     If RefNotPermitted → ReferenceGrant missing in kube-system. -->

## 6. Import Grafana dashboards

ACNS integrates with Azure Managed Grafana for Container Network Observability.
The Cilium community also provides dashboards (require `hubble-metrics` to be
configured — see note below):

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

> **Note**: The community Hubble dashboards (16613 etc.) query `hubble_*`
> Prometheus metrics that require the `hubble-metrics` config to list
> specific collectors (e.g., `dns`, `drop`, `tcp`, `flow`, `http`).
> On AKS with ACNS, this config is **empty by default** — only flow
> observation via `hubble observe` works out of the box.
> The dashboards will show empty panels unless you configure hubble-metrics
> separately.

## 7. Hubble diagnostic metrics

The cilium-agent exposes Prometheus metrics on port `:9962`.
Hubble-specific subsystem errors show up here:

```promql
# Hubble subsystem errors (from cilium-agent :9962)
cilium_errors_warnings_total{subsystem="hubble"}
```

Port `:9965` is the Hubble gRPC metrics server (gRPC call stats only —
not flow/DNS/drop metrics).

## 8. (Optional) Network policy auditing

With ACNS enabled, Cilium network policies get richer:

```bash
CILIUM_POD=$(kubectl -n kube-system get pods -l k8s-app=cilium \
  -o jsonpath='{.items[0].metadata.name}')

# See which flows are being denied by NetworkPolicy
kubectl -n kube-system exec "$CILIUM_POD" -c cilium-agent -- \
  hubble observe -n azure-otel --verdict DROPPED --type policy-verdict

# Export flows as JSON for audit
kubectl -n kube-system exec "$CILIUM_POD" -c cilium-agent -- \
  hubble observe -n azure-otel --output json --last 100 > flows.json
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
