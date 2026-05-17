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

```bash
cd 06_hubble_network_observability

RG=$(azd env get-value AZURE_RESOURCE_GROUP --cwd ../01_deploy_to_aks)
AKS=$(azd env get-value AKS_NAME --cwd ../01_deploy_to_aks)

az aks update \
  --resource-group "$RG" \
  --name "$AKS" \
  --enable-acns
```

## 2. Hubble 확인

```bash
kubectl -n kube-system get cm cilium-config -o jsonpath='{.data.enable-hubble}'
# true 출력 확인
```

## 3. Hubble CLI로 플로우 관찰

```bash
brew install hubble
kubectl -n kube-system port-forward svc/hubble-relay 4245:80 &
hubble status --server localhost:4245
hubble observe --server localhost:4245 -n azure-otel
```

## 4. Grafana 대시보드

ACNS가 ama-metrics를 통해 Hubble 메트릭을 자동 스크레이핑합니다.
Cilium 커뮤니티 대시보드(ID: 16613)를 Azure Managed Grafana에 임포트하세요.

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

## 정리

```bash
az aks update --resource-group "$RG" --name "$AKS" --disable-acns
```

## 참고

- [Azure ACNS 개요](https://learn.microsoft.com/azure/aks/advanced-container-networking-services-overview)
- [Cilium Hubble 문서](https://docs.cilium.io/en/stable/observability/)
