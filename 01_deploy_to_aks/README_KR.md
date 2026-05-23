# 01 — Deploy to AKS (azd + Helm)

> English version: [README.md](./README.md)

AKS + 모니터링 스택(AMW, Grafana, App Insights, Log Analytics)을 프로비저닝하고
[`azure-otel/`](./azure-otel) Helm 차트를 배포합니다.

기본적으로 **Application Gateway v2**를 사용해 L7 경로 기반 라우팅
(/ → nodejs, /api/* → python)을 제공하며, AKS와 병렬로 프로비저닝되어
빠른 배포가 가능합니다 (~10분).

**AGFC**(Application Gateway for Containers)와 **AMPLS**(Azure Monitor Private
Link Scope)는 선택 사항으로, 활성화 시 ~30분 이상 소요됩니다.

![아키텍처](../docs/diagrams/deploy-to-aks-architecture.png)

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

## 실행 순서

> 아래 모든 명령은 `01_deploy_to_aks/` 디렉토리에서 실행합니다
> (`azure.yaml`이 있는 위치).

### 1. 로그인 & 환경 초기화

```bash
cd 01_deploy_to_aks    # 레포 루트에서

az login
azd auth login

azd env new dev
azd env set AZURE_LOCATION koreacentral
```

### 2. 인프라 프로비저닝

**기본 모드 (~10분)** — AppGW v2 + Internal LB (경로 기반 라우팅):

```bash
azd up
```

**AGFC 모드 (~30분)** — Application Gateway for Containers + AMPLS:

```bash
azd env set ENABLE_AGFC true
azd env set ENABLE_APPGW false
azd env set ENABLE_AMPLS true
azd up
```

### 3. kubectl 연결

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

### 4. Helm 차트 배포

**기본 모드 (AppGW v2):**

```bash
helm upgrade --install azure-otel ./azure-otel --namespace azure-otel --create-namespace --set gateway.enabled=false --set appGw.enabled=true --wait --timeout 5m

kubectl -n azure-otel get pods,svc
```

**AGFC 모드:**

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

### 4-1. Public 주소 확인

**기본 모드 (AppGW v2)** — 단일 공인 IP + 경로 기반 라우팅:

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
addr=$(azd env get-value APPGW_PUBLIC_IP)
echo "http://$addr"
open "http://$addr"    # macOS; Linux에서는 xdg-open
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

**AGFC 모드** — 단일 Gateway 주소로 모든 경로 라우팅:

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

### 5. Grafana 열기

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
grafana=$(azd env get-value GRAFANA_ENDPOINT)
echo "$grafana"
open "$grafana"    # macOS; Linux에서는 xdg-open
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

### 6. 정리

```bash
azd down --purge --force
```

---

## 참고

### 생성되는 리소스

리소스 그룹 `rg-<env>` 하위:

- **VNet** `vnet-otel-*` (10.240.0.0/16) + `aks-subnet` (10.240.0.0/22)
- **AKS** `aks-otel-*` (Standard, 2× `Standard_D4s_v5` 2–6 autoscale, Azure CNI overlay,
  Cilium + NetworkPolicy, OIDC, Workload Identity, RBAC)
  - Container Insights (`omsagent`) → Log Analytics
  - Managed Prometheus (`azureMonitorProfile.metrics`) → AMW
- **Log Analytics** + **Application Insights** (workspace-based)
- **Azure Monitor Workspace** (managed Prometheus 백엔드)
- **Azure Managed Grafana** (Standard, AMW 데이터소스 연결)
- **ACR** `acrotel*` (Standard, AKS kubelet에 `AcrPull` 부여)
- _(기본)_ **Application Gateway v2** `appgw-subnet` (10.240.4.0/24),
  경로 기반 라우팅 → Internal LB (nodejs 10.240.1.100, python 10.240.1.101)
- _(ENABLE_AGFC=true)_ AGFC 서브넷 `aks-appgateway` (10.240.8.0/24, 위임) +
  postprovision hook에서 ALB add-on 활성화
- _(ENABLE_AMPLS=true)_ **AMPLS** + Private Endpoint (`aks-subnet`) + 6개
  Private DNS Zone (VNet 연결)

Role assignments (`principalId` 자동 주입):

- Deployer → Grafana Admin / AKS RBAC Cluster Admin + Cluster User
- Grafana MSI → Monitoring Data Reader on AMW

### AMPLS + Private Link 아키텍처

`azd up`은 **Azure Monitor Private Link Scope (AMPLS)** 를 만들어 AKS pod ↔
Azure Monitor 간 모니터링 트래픽이 VNet 안에서만 흐르게 합니다. 아래 다이어그램에
생성되는 리소스와 연결 관계를 정리합니다:

```
┌─── AKS VNet ──────────────────────────────────────────────────────────┐
│                                                                       │
│  ama-metrics pod                                                      │
│    ├─ prometheus-collector (MDSD)                                     │
│    │    ├─ DCE 경유로 DCR 설정 읽기 (privatelink DNS → PE)              │
│    │    └─ DCE 경유로 메트릭 remote-write → AMW                        │
│    └─ MetricsExtension (port 55680)                                   │
│                                                                       │
│  otel-collector pod (03 단계)                                          │
│    └─ azuremonitor exporter → App Insights (privatelink DNS → PE)     │
│                                                                       │
│  ┌──── Private Endpoint (pe-ampls-*) ──────────────────────────────┐  │
│  │  aks-subnet 의 NIC → AMPLS 연결 서비스의 사설 IP                  │  │
│  └─────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────┘
         │ 사설 IP 는 아래 DNS 존이 해석 ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │  6 개 Private DNS Zone (VNet 에 링크)                           │
   │   • privatelink.monitor.azure.com                              │
   │   • privatelink.oms.opinsights.azure.com                       │
   │   • privatelink.ods.opinsights.azure.com                       │
   │   • privatelink.agentsvc.azure-automation.net                  │
   │   • privatelink.<region>.handler.control.monitor.azure.com     │
   │   • privatelink.<region>.ingest.monitor.azure.com              │
   └─────────────────────────────────────────────────────────────────┘
         │ A 레코드는 PE DNS Zone Group 이 자동 생성 ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │  AMPLS (ampls-*) ── Scoped Resources:                         │
   │   • App Insights  (appi-link)                                  │
   │   • Log Analytics (law-link)                                   │
   │   • DCE           (dce-link)                                   │
   │  Access mode: Open / Open                                     │
   └─────────────────────────────────────────────────────────────────┘
```

**Data Collection 리소스** (Prometheus 메트릭 파이프라인):

| 리소스 | 이름 | 역할 |
|---|---|---|
| **DCE** (Data Collection Endpoint) | `dce-*` | ama-metrics 의 인입 + 설정 엔드포인트. AMPLS 에 링크되어 트래픽이 PE 를 경유. |
| **DCR** (Data Collection Rule) | `dcr-*` | `PrometheusForwarder` 데이터 소스 → AMW 대상 정의. `dataCollectionEndpointId` 로 DCE 참조. |
| **DCRA** (DCR Association) | `send-to-amw` | DCR 을 AKS 클러스터에 연결. ama-metrics 에게 어떤 DCR 이 데이터 흐름을 정의하는지 알려줌. |
| **DCRA** (DCE Association) | `configurationAccessEndpoint` | DCE 를 AKS 클러스터에 연결. **Private link 필수** — 없으면 MDSD 가 DCE endpoint 를 모르고, AMCS 에서 `403 InvalidAccess` 발생. |

> **왜 DCRA 가 두 개?** DCR DCRA 는 *무엇을 수집해서 어디로 보낼지*, DCE
> DCRA (`configurationAccessEndpoint`) 는 *설정 서비스에 어떻게 접근할지*를
> 알려줍니다. Private DNS 존이 `*.monitor.azure.com` 을 사설 IP 로 해석하면
> AMCS 는 DCE 경유 설정 접근을 요구합니다 — DCE DCRA 가 없으면
> `ENDPOINT_FQDN` 이 비어서 MDSD 가 403 을 받습니다.

### `azd up`이 수행하는 단계

1. Subscription-scope Bicep으로 RG 생성
2. RG 모듈로 VNet, AKS, 모니터링, Grafana, role assignment 생성
3. `preprovision` hook: Azure CLI 확장 설치, AGFC preview feature/provider 등록
4. `postprovision` hook: AKS Gateway API + AGFC 활성화, ALB MSI에 `aks-appgateway`
   서브넷 권한 부여

> Helm 차트 설치는 azd 사이클에서 분리되어 있습니다 (위 4단계 참고).

### azd 환경 값 확인

```bash
azd env get-values | grep -E '^(AKS_|GRAFANA_|APPLICATION_INSIGHTS_|AZURE_MONITOR_|LOG_ANALYTICS_|AZURE_RESOURCE_GROUP|VNET_|AGFC_|ACR_)'
```

### Private cluster

`infra/main.parameters.json`에서 `enablePrivateCluster=true`이면 VNet 내부
(bastion/VPN) 또는 `az aks command invoke`를 통해 `kubectl`을 실행해야 합니다.

### GHCR 이미지 권한

이미지(`ghcr.io/hellices/azure-otel:<service>-latest`)가 private이면
`ImagePullBackOff`가 발생합니다. 둘 중 하나로 해결:

**A. 패키지를 Public으로 변경 (1회)**
https://github.com/users/hellices/packages/container/azure-otel/settings → Change visibility → Public

**B. Pull secret 사용**

```bash
ghcrUser='hellices'
ghcrToken='<PAT with read:packages>'
kubectl create namespace azure-otel
kubectl -n azure-otel create secret docker-registry ghcr \
  --docker-server=ghcr.io --docker-username="$ghcrUser" --docker-password="$ghcrToken"
# Helm:  --set 'global.imagePullSecrets[0].name=ghcr'
```

### Ingress 없이 스모크 테스트

```bash
helm upgrade --install azure-otel ./azure-otel \
  --namespace azure-otel --set nodejs.pythonPublicBaseUrl=http://localhost:8000

kubectl -n azure-otel port-forward svc/azure-otel-nodejs 3000:3000   # 터미널 A
kubectl -n azure-otel port-forward svc/azure-otel-python 8000:8000   # 터미널 B
# http://localhost:3000
```

공인 엔드포인트는 `azd up`이 Gateway API + AGFC를 자동 구성하며, 그 다음
Helm 차트(4단계)가 `ApplicationLoadBalancer` / `Gateway` / `HTTPRoute`를 생성합니다.

### Tear down 옵션

`--purge`는 soft-delete 가능한 리소스(App Insights, Log Analytics, Grafana)를
영구 삭제합니다. 보존하려면 생략하세요.
