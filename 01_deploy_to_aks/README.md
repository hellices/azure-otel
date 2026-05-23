# 01 — Deploy to AKS (azd + Helm)

Provisions AKS plus the monitoring stack (AMW, Grafana, App Insights, Log
Analytics) and deploys the [`azure-otel/`](./azure-otel) Helm chart.

By default deploys **Application Gateway v2** for L7 path-based routing
(/ → nodejs, /api/* → python) — provisioned in parallel with AKS for fast
deployment (~10 min).

Optionally enables **AGFC** (Application Gateway for Containers) and **AMPLS**
(Azure Monitor Private Link Scope) — both are disabled by default (~30+ min
when enabled).

> Korean version: [README_KR.md](./README_KR.md)

![Architecture](../docs/diagrams/deploy-to-aks-architecture.png)

## Prerequisites

<details open>
<summary><strong>macOS / Linux</strong></summary>

```bash
brew install azure/azd/azd azure-cli kubectl helm
```

</details>

<details open>
<summary><strong>Windows (PowerShell)</strong></summary>

```powershell
winget install Microsoft.Azd Microsoft.AzureCLI Kubernetes.kubectl Helm.Helm
```

</details>

## Steps

> All commands below assume you are inside `01_deploy_to_aks/`
> (where `azure.yaml` lives).

### 1. Login & init env

```bash
cd 01_deploy_to_aks    # from repo root

az login
azd auth login

azd env new dev
azd env set AZURE_LOCATION koreacentral
```

### 2. Provision infra

**Default mode (~10 min)** — AppGW v2 + Internal LB (path-based routing):

```bash
azd up
```

**AGFC mode (~30 min)** — Application Gateway for Containers + AMPLS:

```bash
azd env set ENABLE_AGFC true
azd env set ENABLE_APPGW false
azd env set ENABLE_AMPLS true
azd up
```

### 3. Connect kubectl

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
rg=$(azd env get-value AZURE_RESOURCE_GROUP)
aks=$(azd env get-value AKS_NAME)
az aks get-credentials --resource-group "$rg" --name "$aks" --overwrite-existing
kubectl get nodes
```

</details>

<details open>
<summary><strong>Windows (PowerShell)</strong></summary>

```powershell
$rg = azd env get-value AZURE_RESOURCE_GROUP
$aks = azd env get-value AKS_NAME
az aks get-credentials --resource-group $rg --name $aks --overwrite-existing
kubectl get nodes
```

</details>

### 4. Deploy the Helm chart

**Default mode (AppGW v2):**

```bash
helm upgrade --install azure-otel ./azure-otel --namespace azure-otel --create-namespace --set gateway.enabled=false --set appGw.enabled=true --wait --timeout 5m

kubectl -n azure-otel get pods,svc
```

**AGFC mode:**

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
subnetId=$(azd env get-value AGFC_SUBNET_ID)
helm upgrade --install azure-otel ./azure-otel \
  --namespace azure-otel --create-namespace \
  --set gateway.enabled=true \
  --set "gateway.subnetId=$subnetId" \
  --wait --timeout 10m

kubectl -n azure-otel get pods,svc
```

</details>

<details open>
<summary><strong>Windows (PowerShell)</strong></summary>

```powershell
$subnetId = azd env get-value AGFC_SUBNET_ID
helm upgrade --install azure-otel ./azure-otel `
  --namespace azure-otel --create-namespace `
  --set gateway.enabled=true `
  --set "gateway.subnetId=$subnetId" `
  --wait --timeout 10m

kubectl -n azure-otel get pods,svc
```

</details>

### 4-1. Get the public address

**Default mode (AppGW v2)** — single public IP with path-based routing:

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
addr=$(azd env get-value APPGW_PUBLIC_IP)
echo "http://$addr"
open "http://$addr"    # macOS; use xdg-open on Linux
```

</details>

<details open>
<summary><strong>Windows (PowerShell)</strong></summary>

```powershell
$addr = azd env get-value APPGW_PUBLIC_IP
Write-Host "http://$addr"
Start-Process "http://$addr"
```

</details>

**AGFC mode** — single Gateway address for all routes:

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
addr=$(kubectl -n azure-otel get gateway azure-otel-gw \
  -o 'jsonpath={.status.addresses[0].value}')
echo "http://$addr"
open "http://$addr"
```

</details>

<details open>
<summary><strong>Windows (PowerShell)</strong></summary>

```powershell
$addr = kubectl -n azure-otel get gateway azure-otel-gw `
  -o 'jsonpath={.status.addresses[0].value}'
Write-Host "http://$addr"
Start-Process "http://$addr"
```

</details>

### 5. Open Grafana

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
grafana=$(azd env get-value GRAFANA_ENDPOINT)
echo "$grafana"
open "$grafana"    # macOS; use xdg-open on Linux
```

</details>

<details open>
<summary><strong>Windows (PowerShell)</strong></summary>

```powershell
$grafana = azd env get-value GRAFANA_ENDPOINT
Write-Host $grafana
Start-Process $grafana
```

</details>

### 6. Tear down

```bash
azd down --purge --force
```

---

## Reference

### Resources created

Under resource group `rg-<env>`:

- **VNet** `vnet-otel-*` (10.240.0.0/16) + `aks-subnet` (10.240.0.0/22)
- **AKS** `aks-otel-*` (Standard, 2× `Standard_D4s_v5`, 2–6 autoscale, Azure
  CNI overlay, Cilium + NetworkPolicy, OIDC, Workload Identity, RBAC)
  - Container Insights (`omsagent`) → Log Analytics
  - Managed Prometheus (`azureMonitorProfile.metrics`) → AMW
- **Log Analytics** + **Application Insights** (workspace-based)
- **Azure Monitor Workspace** (managed Prometheus backend)
- **Azure Managed Grafana** (Standard, AMW datasource wired up)
- **ACR** `acrotel*` (Standard, AKS kubelet granted `AcrPull`)
- _(default)_ **Application Gateway v2** `appgw-subnet` (10.240.4.0/24) with
  path-based routing → Internal LB (nodejs 10.240.1.100, python 10.240.1.101)
- _(ENABLE_AGFC=true)_ AGFC subnet `aks-appgateway` (10.240.8.0/24, delegated)
  + ALB add-on enabled via postprovision hook
- _(ENABLE_AMPLS=true)_ **AMPLS** + Private Endpoint into `aks-subnet` + 6
  Private DNS Zones (linked to VNet)

Role assignments (with `principalId` auto-injected):

- Deployer → Grafana Admin / AKS RBAC Cluster Admin + Cluster User
- Grafana MSI → Monitoring Data Reader on AMW

### AMPLS + Private Link architecture

`azd up` creates an **Azure Monitor Private Link Scope (AMPLS)** so that
monitoring traffic between AKS pods and Azure Monitor services stays inside
the VNet. The diagram below shows every resource and how they connect:

```
┌─── AKS VNet ──────────────────────────────────────────────────────────┐
│                                                                       │
│  ama-metrics pod                                                      │
│    ├─ prometheus-collector (MDSD)                                     │
│    │    ├─ reads DCR config via DCE (privatelink DNS → PE)            │
│    │    └─ remote-writes metrics via DCE → AMW                        │
│    └─ MetricsExtension (port 55680)                                   │
│                                                                       │
│  otel-collector pod (step 03)                                         │
│    └─ azuremonitor exporter → App Insights (privatelink DNS → PE)     │
│                                                                       │
│  ┌──── Private Endpoint (pe-ampls-*) ──────────────────────────────┐  │
│  │  NIC in aks-subnet → private IPs for all AMPLS-linked services  │  │
│  └─────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────┘
         │ private IPs resolved via ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │  6 Private DNS Zones (linked to VNet)                          │
   │   • privatelink.monitor.azure.com                              │
   │   • privatelink.oms.opinsights.azure.com                       │
   │   • privatelink.ods.opinsights.azure.com                       │
   │   • privatelink.agentsvc.azure-automation.net                  │
   │   • privatelink.<region>.handler.control.monitor.azure.com     │
   │   • privatelink.<region>.ingest.monitor.azure.com              │
   └─────────────────────────────────────────────────────────────────┘
         │ A records auto-created by PE DNS Zone Group ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │  AMPLS (ampls-*) ── Scoped Resources:                         │
   │   • App Insights  (appi-link)                                  │
   │   • Log Analytics (law-link)                                   │
   │   • DCE           (dce-link)                                   │
   │  Access mode: Open / Open                                     │
   └─────────────────────────────────────────────────────────────────┘
```

**Data Collection resources** (Prometheus metrics pipeline):

| Resource | Name | Purpose |
|---|---|---|
| **DCE** (Data Collection Endpoint) | `dce-*` | Ingestion + config endpoint for ama-metrics. Linked into AMPLS so traffic goes through the PE. |
| **DCR** (Data Collection Rule) | `dcr-*` | Defines `PrometheusForwarder` data source → AMW destination. References the DCE via `dataCollectionEndpointId`. |
| **DCRA** (DCR Association) | `send-to-amw` | Associates the DCR with the AKS cluster. Tells ama-metrics which DCR governs the data flow. |
| **DCRA** (DCE Association) | `configurationAccessEndpoint` | Associates the DCE with the AKS cluster. **Required for private link** — without it, MDSD cannot resolve the DCE endpoint and receives `403 InvalidAccess` from AMCS. |

> **Why two DCRAs?** The DCR DCRA tells ama-metrics *what to collect and
> where to send*. The DCE DCRA (`configurationAccessEndpoint`) tells
> ama-metrics *how to reach the configuration service*. When private DNS
> zones redirect `*.monitor.azure.com` to private IPs, AMCS requires
> DCE-based config access — without the DCE DCRA, `ENDPOINT_FQDN` stays
> empty and MDSD gets a 403.

### What `azd up` does

1. Subscription-scope Bicep creates the RG
2. The RG module creates the VNet, AKS, monitoring, Grafana, ACR, role assignments
3. _(ENABLE_AGFC only)_ `preprovision` hook: installs Azure CLI extensions,
   registers AGFC preview feature/provider (~6 min)
4. `postprovision` hook:
   - **Fast mode**: fetches kubeconfig only
   - **Full mode (ENABLE_AGFC)**: enables AKS Gateway API + AGFC, grants the
     ALB MSI permission on the `aks-appgateway` subnet (~10-15 min)

> Helm install is intentionally split out of the azd lifecycle (see step 4).

### Inspecting azd env values

```bash
azd env get-values | grep -E '^(AKS_|GRAFANA_|APPLICATION_INSIGHTS_|AZURE_MONITOR_|LOG_ANALYTICS_|AZURE_RESOURCE_GROUP|VNET_|AGFC_|ACR_)'
```

### Private cluster

If `infra/main.parameters.json` sets `enablePrivateCluster=true`, you must run
`kubectl` from inside the VNet (bastion/VPN) or via `az aks command invoke`.

### GHCR image permissions

The images (`ghcr.io/hellices/azure-otel:<service>-latest`) being private
will cause `ImagePullBackOff`. Two options:

**A. Make the package public (one-time)**
https://github.com/users/hellices/packages/container/azure-otel/settings → Change visibility → Public

**B. Use a pull secret**

```bash
ghcrUser='hellices'
ghcrToken='<PAT with read:packages>'
kubectl create namespace azure-otel
kubectl -n azure-otel create secret docker-registry ghcr \
  --docker-server=ghcr.io --docker-username="$ghcrUser" --docker-password="$ghcrToken"
# Helm:  --set 'global.imagePullSecrets[0].name=ghcr'
```

### Smoke test without ingress

```bash
helm upgrade --install azure-otel ./azure-otel \
  --namespace azure-otel --set nodejs.pythonPublicBaseUrl=http://localhost:8000

kubectl -n azure-otel port-forward svc/azure-otel-nodejs 3000:3000   # terminal A
kubectl -n azure-otel port-forward svc/azure-otel-python 8000:8000   # terminal B
# http://localhost:3000
```

The public endpoint is created by `azd up` (Gateway API + AGFC) and then by
the Helm chart (step 4) which lays down the `ApplicationLoadBalancer` /
`Gateway` / `HTTPRoute`.

### Tear-down options

`--purge` permanently deletes soft-deletable resources (App Insights, Log
Analytics, Grafana). Drop the flag to keep them.
