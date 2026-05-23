# 06 — Cilium Hubble 네트워크 관측성 (ACNS)

01단계에서 배포한 AKS 클러스터에 **Azure Advanced Container Networking Services (ACNS)**를
활성화하여 **Cilium Hubble** 네트워크 관측성을 추가합니다.
사이드카, 에이전트, 코드 변경 없이 L3/L4/L7 네트워크 플로우 가시성, DNS 모니터링,
패킷 드롭 분석이 가능합니다.

> English version: [README.md](./README.md)

## 사전 요구 사항

- [01_deploy_to_aks](../01_deploy_to_aks)의 AKS 클러스터 (`networkDataplane: cilium` 사용 중).
- Azure CLI ≥ 2.78.0.

> **비용**: ACNS는 유료 Azure 애드온입니다.
> [ACNS 가격](https://azure.microsoft.com/pricing/details/azure-container-networking-services/)을
> 프로덕션 클러스터에 활성화하기 전에 확인하세요.

## 1. ACNS 활성화

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
cd 06_hubble_network_observability

RG=$(azd env get-value AZURE_RESOURCE_GROUP --cwd ../01_deploy_to_aks)
AKS=$(azd env get-value AKS_NAME --cwd ../01_deploy_to_aks)

az aks update \
  --resource-group "$RG" \
  --name "$AKS" \
  --enable-acns
```

</details>

<details open>
<summary><strong>Windows (PowerShell)</strong></summary>

```powershell
cd 06_hubble_network_observability

$RG = azd env get-value AZURE_RESOURCE_GROUP --cwd ../01_deploy_to_aks
$AKS = azd env get-value AKS_NAME --cwd ../01_deploy_to_aks

az aks update `
  --resource-group $RG `
  --name $AKS `
  --enable-acns
```

</details>

## 2. Hubble 확인

```bash
kubectl -n kube-system get cm cilium-config -o jsonpath='{.data.enable-hubble}'
# true 출력 확인

# Hubble Relay 확인 (서비스 포트 443 → 컨테이너 포트 4245, mTLS)
kubectl -n kube-system get svc hubble-relay
kubectl -n kube-system get pods -l k8s-app=hubble-relay
```

## 3. Hubble 플로우 관찰 (cilium-agent exec 방식 — 가장 간편)

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
CILIUM_POD=$(kubectl -n kube-system get pods -l k8s-app=cilium \
  -o jsonpath='{.items[0].metadata.name}')

# azure-otel 네임스페이스의 최근 20개 플로우 조회
kubectl -n kube-system exec "$CILIUM_POD" -c cilium-agent -- \
  hubble observe -n azure-otel --last 20

# 드롭된 패킷만 필터
kubectl -n kube-system exec "$CILIUM_POD" -c cilium-agent -- \
  hubble observe -n azure-otel --verdict DROPPED
```

</details>

<details open>
<summary><strong>Windows (PowerShell)</strong></summary>

```powershell
$CILIUM_POD = kubectl -n kube-system get pods -l k8s-app=cilium `
  -o jsonpath='{.items[0].metadata.name}'

# azure-otel 네임스페이스의 최근 20개 플로우 조회
kubectl -n kube-system exec $CILIUM_POD -c cilium-agent -- `
  hubble observe -n azure-otel --last 20

# 드롭된 패킷만 필터
kubectl -n kube-system exec $CILIUM_POD -c cilium-agent -- `
  hubble observe -n azure-otel --verdict DROPPED
```

</details>

> **참고**: Hubble Relay는 mTLS를 사용하므로 로컬 `hubble` CLI로 직접 접속하려면
> TLS 인증서 추출이 필요합니다. 상세 방법은 [README.md](./README.md)의 3b 섹션을 참조하세요.

## 4. Hubble UI 배포

웹 기반 플로우 시각화 UI를 배포합니다.

```bash
kubectl apply -f manifests/hubble-ui.yaml
kubectl -n kube-system rollout status deploy/hubble-ui --timeout=90s
```

port-forward로 접속:

```bash
kubectl -n kube-system port-forward svc/hubble-ui 12000:80
# http://localhost:12000 접속
```

> **참고**: AGFC는 포트 80/443만 허용하고, Hubble UI의 React Router는
> sub-path 호스팅을 지원하지 않아 port-forward가 권장 접속 방법입니다.

## 5. Grafana 대시보드

> **주의**: ACNS가 hubble `hubble_*` Prometheus 메트릭을 자동 활성화하지 **않습니다**.
> `hubble-metrics` 설정이 비어 있어, 커뮤니티 대시보드(16613)는 기본 상태에서 빈 패널을 보여줍니다.
> 플로우 관찰은 `hubble observe` 명령으로만 가능합니다.

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
grafana=$(azd env get-value GRAFANA_ENDPOINT --cwd ../01_deploy_to_aks)
token=$(az account get-access-token \
  --resource ce34e7e5-485f-4d76-964f-b3d2b16d1e4f \
  --query accessToken -o tsv)

curl -sS "https://grafana.com/api/dashboards/16613/revisions/latest/download" \
  | jq '{dashboard: (. | .id = null), overwrite: true, folderId: 0}' \
  | curl -sS -X POST "$grafana/api/dashboards/db" \
    -H "Authorization: Bearer $token" \
    -H 'Content-Type: application/json' \
    --data-binary @-
```

</details>

<details open>
<summary><strong>Windows (PowerShell)</strong></summary>

```powershell
$grafana = azd env get-value GRAFANA_ENDPOINT --cwd ../01_deploy_to_aks
$token = az account get-access-token `
  --resource ce34e7e5-485f-4d76-964f-b3d2b16d1e4f `
  --query accessToken -o tsv

$dash = Invoke-RestMethod -Uri "https://grafana.com/api/dashboards/16613/revisions/latest/download"
$dash.id = $null
$body = @{ dashboard=$dash; overwrite=$true; folderId=0 } | ConvertTo-Json -Depth 20
Invoke-RestMethod -Uri "$grafana/api/dashboards/db" -Method Post `
  -Headers @{ Authorization="Bearer $token"; "Content-Type"="application/json" } `
  -Body $body
```

</details>

## 정리

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
az aks update --resource-group "$RG" --name "$AKS" --disable-acns
```

</details>

<details open>
<summary><strong>Windows (PowerShell)</strong></summary>

```powershell
az aks update --resource-group $RG --name $AKS --disable-acns
```

</details>

## 참고

- [Azure ACNS 개요](https://learn.microsoft.com/azure/aks/advanced-container-networking-services-overview)
- [Cilium Hubble 문서](https://docs.cilium.io/en/stable/observability/)
