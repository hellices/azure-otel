# 01 — Deploy to AKS (azd + Helm)

Provisions AKS plus the monitoring stack (AMW, Grafana, App Insights, Log
Analytics, **AMPLS + Private Endpoint + 5 Private DNS Zones**) and deploys the
[`azure-otel/`](./azure-otel) Helm chart.

> Korean version: [README_KR.md](./README_KR.md)

## Prerequisites

```powershell
winget install --id Microsoft.Azd        --silent --accept-source-agreements --accept-package-agreements
winget install --id Microsoft.AzureCLI   --silent --accept-source-agreements --accept-package-agreements
winget install --id Kubernetes.kubectl   --silent --accept-source-agreements --accept-package-agreements
winget install --id Helm.Helm            --silent --accept-source-agreements --accept-package-agreements
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
```

## Steps

### 1. Login & init env

```powershell
cd c:\Users\inhwanhwang\vscode\azure-otel\01_deploy_to_aks

az login
azd auth login

azd env new dev
azd env set AZURE_LOCATION koreacentral
```

### 2. Provision infra

```powershell
azd up
```

`azd up` creates the AKS / monitoring stack via Bicep and runs the
postprovision hook to enable Gateway API + ALB add-on and grant the AGFC subnet
permissions. **The Helm release is not part of this hook.**

### 3. Connect kubectl

```powershell
$rg  = (azd env get-value AZURE_RESOURCE_GROUP)
$aks = (azd env get-value AKS_NAME)
az aks get-credentials --resource-group $rg --name $aks --overwrite-existing
kubectl get nodes
```

### 4. Deploy the Helm chart

```powershell
cd c:\Users\inhwanhwang\vscode\azure-otel
$subnetId = (azd env get-value AGFC_SUBNET_ID)
helm upgrade --install azure-otel .\01_deploy_to_aks\azure-otel `
  --namespace azure-otel --create-namespace `
  --set "gateway.subnetId=$subnetId" `
  --wait --timeout 10m

kubectl -n azure-otel get pods,svc
```

### 4-1. Get the AGFC public address

The Gateway typically gets its public IP/FQDN within 1–3 minutes after the
chart is deployed.

```powershell
# One-shot
kubectl -n azure-otel get gateway azure-otel-gw `
  -o 'jsonpath={.status.addresses[0].value}'

# Wait until ready (kubectl 1.23+)
kubectl -n azure-otel wait gateway/azure-otel-gw `
  --for=jsonpath='{.status.addresses[0].value}' --timeout=5m

# Capture and open
$addr = kubectl -n azure-otel get gateway azure-otel-gw `
          -o 'jsonpath={.status.addresses[0].value}'
"http://$addr"
Start-Process "http://$addr"
```

The `Gateway` / `HTTPRoute` are created by the Helm chart; the AGFC controller
then populates `.status.addresses[0].value` with the Application Gateway for
Containers frontend.

### 5. Open Grafana

```powershell
$grafana = (azd env get-value GRAFANA_ENDPOINT)
$grafana                                  # check the URL
Start-Process "msedge.exe" $grafana       # or chrome.exe / iexplore.exe
```

If `Start-Process (azd env get-value GRAFANA_ENDPOINT)` fails it usually means
azd printed a warning that turned the value into an array, or PS5 URL handling
quirks kicked in. Capturing into a variable first or using `-FilePath` is
reliable.

### 6. Tear down

```powershell
azd down --purge --force
```

---

## Reference

### Resources created

Under resource group `rg-<env>`:

- **VNet** `aotel-vnet-*` (10.240.0.0/16) + private `aks-subnet` (10.240.0.0/22)
- **AKS** `aotel-aks-*` (Standard, 3× `Standard_D4s_v5`, 3–5 autoscale, Azure
  CNI overlay, Cilium + NetworkPolicy, OIDC, Workload Identity, RBAC)
  - Container Insights (`omsagent`) → Log Analytics
  - Managed Prometheus (`azureMonitorProfile.metrics`) → AMW
- **Log Analytics** + **Application Insights** (workspace-based)
- **Azure Monitor Workspace** (managed Prometheus backend)
- **Azure Managed Grafana** (Standard, AMW datasource wired up)
- **ACR** `aotelacr*` (Standard, AKS kubelet granted `AcrPull`)
- **AMPLS** + Private Endpoint into `aks-subnet` + 5 Private DNS Zones (linked
  to the VNet) so step 03's collector can reach App Insights privately.

Role assignments (with `principalId` auto-injected):

- Deployer → Grafana Admin / AKS RBAC Cluster Admin + Cluster User
- Grafana MSI → Monitoring Data Reader on AMW

### What `azd up` does

1. Subscription-scope Bicep creates the RG
2. The RG module creates the VNet, AKS, monitoring, Grafana, AMPLS, role assignments
3. `preprovision` hook: installs Azure CLI extensions, registers AGFC preview
   feature/provider
4. `postprovision` hook: enables AKS Gateway API + AGFC, grants the ALB MSI
   permission on the `aks-appgateway` subnet

> Helm install is intentionally split out of the azd lifecycle (see step 4).

### Inspecting azd env values

```powershell
azd env get-values | Select-String -Pattern '^(AKS_|GRAFANA_|APPLICATION_INSIGHTS_|AZURE_MONITOR_|LOG_ANALYTICS_|AZURE_RESOURCE_GROUP|VNET_|AGFC_|ACR_)'
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

```powershell
$ghcrUser  = 'hellices'
$ghcrToken = '<PAT with read:packages>'
kubectl create namespace azure-otel
kubectl -n azure-otel create secret docker-registry ghcr `
  --docker-server=ghcr.io --docker-username=$ghcrUser --docker-password=$ghcrToken
# Helm:  --set 'global.imagePullSecrets[0].name=ghcr'
```

### Smoke test without ingress

```powershell
helm upgrade --install azure-otel .\01_deploy_to_aks\azure-otel `
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
