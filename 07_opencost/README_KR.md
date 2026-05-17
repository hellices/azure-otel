# 07 — OpenCost: Kubernetes 비용 관측성 (FinOps)

**OpenCost** (CNCF Graduated)를 배포하여 Pod, 네임스페이스, 서비스별
비용 할당을 추적합니다. Kubernetes 리소스 사용량과 Azure 과금 데이터를
결합하여 "이 서비스가 시간당 얼마인지"를 보여줍니다.

> English version: [README.md](./README.md)

## 사전 요구 사항

- [01_deploy_to_aks](../01_deploy_to_aks)의 AKS 클러스터.
- Helm 3.

## 1. 경량 Prometheus 배포

```bash
cd 07_opencost

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm upgrade --install prometheus prometheus-community/prometheus \
  -n prometheus-system --create-namespace \
  -f manifests/prometheus-values.yaml
```

## 2. (선택) Azure 가격 연동

정확한 EA/MCA 요금을 반영하려면 서비스 프린시펄을 생성하고
`azure-service-key` 시크릿을 만드세요. 영문 README의 step 2 참고.

## 3. OpenCost 설치

```bash
helm repo add opencost https://opencost.github.io/opencost-helm-chart
helm upgrade --install opencost opencost/opencost \
  -n opencost --create-namespace \
  -f manifests/opencost-values.yaml
```

## 4. UI 확인

```bash
kubectl -n opencost port-forward svc/opencost 9090:9090
open http://localhost:9090
```

## 5. Grafana 대시보드

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

## 정리

```bash
helm uninstall opencost -n opencost
helm uninstall prometheus -n prometheus-system
kubectl delete ns opencost prometheus-system
```

## 참고

- [OpenCost 문서](https://www.opencost.io/docs/)
- [OpenCost Azure 연동](https://www.opencost.io/docs/configuration/azure)
