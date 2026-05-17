# 03-1 — AKS 자동 계측 → App Insights (컬렉터 불필요)

[03_otel_observability](../03_otel_observability)의 대안으로, 별도의 OpenTelemetry
Collector 배포 대신 **AKS 네이티브 자동 계측 프리뷰 기능**을 사용합니다.

AKS가 **Azure Monitor OpenTelemetry Distro**를 애플리케이션 파드에 직접 주입하고,
클러스터의 Azure Monitor Agent(AMA)를 통해 **Application Insights**로 전달합니다.
컬렉터나 오퍼레이터 설치가 필요 없습니다.

```
app pod ─OTLP/HTTP─► AMA (Azure Monitor Agent) ─► Application Insights
                                                    └─► Live Metrics / App Map / Failures
```

## 03 vs 03-1 비교

| 항목 | 03 (OTel Collector) | 03-1 (AKS 자동 계측) |
|---|---|---|
| 컬렉터 | 자체 관리 OTel Collector (2 replicas) | 없음 — AMA가 OTLP 처리 |
| 오퍼레이터 | 업스트림 OTel Operator + cert-manager | AKS 관리형 (내장 webhook) |
| Python 지원 | 완전 지원 (OTLP/HTTP) | 제한적 프리뷰 (비공개 어노테이션) |
| 트레이스 목적지 | `azuremonitor` 익스포터 → App Insights | AMA → App Insights |
| 메트릭 목적지 | `prometheus` 익스포터 → ama-metrics → AMW | App Insights (OTLP) |
| 인프라 오버헤드 | Collector 파드 + Operator 파드 | 제로 (기존 AMA 재사용) |

## 사전 요구 사항

- [01_deploy_to_aks](../01_deploy_to_aks)의 AKS 클러스터 (step 01 완료)
- Step 02 적용됨 (또는 Helm 차트만 배포된 상태)
- Azure CLI ≥ 2.78.0 + `aks-preview` 확장

## 0. 프리뷰 기능 등록

> 등록에 수 분 소요됩니다. 구독당 한 번만 실행하면 됩니다.

```bash
# AKS 자동 계측
az feature register \
  --namespace "Microsoft.ContainerService" \
  --name "AzureMonitorAppMonitoringPreview"

# (선택) Application Insights OTLP 수집
az feature register \
  --namespace "Microsoft.Insights" \
  --name "OtlpApplicationInsights"

# 등록 대기
az feature list -o table \
  --query "[?contains(name, 'AzureMonitorAppMonitoringPreview')].{Name:name,State:properties.state}"

# 전파
az provider register --namespace "Microsoft.ContainerService"
az provider register --namespace "Microsoft.Insights"
```

## 1. Step 02 / 03 정리

OTel Operator의 Instrumentation CR과 step 03 컬렉터를 제거합니다.
Step 02의 PodMonitor는 Prometheus 메트릭용으로 독립 동작하므로 유지합니다.

```bash
cd 03_1_aks_auto_instrumentation    # 저장소 루트에서

# Step 02/03 Instrumentation CR (OTel Operator) 삭제
kubectl -n azure-otel delete instrumentation.opentelemetry.io azure-otel --ignore-not-found

# Step 03 Collector 삭제 (적용된 경우)
kubectl -n azure-otel delete opentelemetrycollector otel --ignore-not-found
kubectl -n azure-otel delete secret otel-collector-secrets --ignore-not-found
```

## 2. AKS 자동 계측 활성화

```bash
RG=$(azd env get-value AZURE_RESOURCE_GROUP --cwd ../01_deploy_to_aks)
AKS=$(azd env get-value AKS_NAME --cwd ../01_deploy_to_aks)

az aks update \
  --resource-group "$RG" \
  --name "$AKS" \
  --enable-azure-monitor-app-monitoring
```

확인:

```bash
kubectl get crd instrumentations.monitor.azure.com
```

## 3. AKS Instrumentation CR 생성

```bash
CONN_STR=$(azd env get-value APPLICATION_INSIGHTS_CONNECTION_STRING --cwd ../01_deploy_to_aks)

sed "s|\${APPLICATION_INSIGHTS_CONNECTION_STRING}|${CONN_STR}|" \
  manifests/instrumentation.yaml | kubectl apply -f -

kubectl -n azure-otel get instrumentation.monitor.azure.com
```

## 4. Python 디플로이먼트 패치 (제한적 프리뷰)

Python 자동 계측은 제한적 프리뷰이며 별도의 비공개 어노테이션이 필요합니다.

```bash
kubectl patch deploy azure-otel-python -n azure-otel \
  --type merge --patch-file manifests/python-patch.yaml
```

> Python 제한적 프리뷰 접근 권한이 없는 경우 이 단계를 건너뛰세요.

## 5. 디플로이먼트 재시작

```bash
kubectl -n azure-otel rollout restart deploy \
  azure-otel-spring azure-otel-python azure-otel-nodejs

kubectl -n azure-otel rollout status deploy/azure-otel-spring  --timeout=180s
kubectl -n azure-otel rollout status deploy/azure-otel-python  --timeout=180s
kubectl -n azure-otel rollout status deploy/azure-otel-nodejs  --timeout=180s
```

## 6. 확인

### A. Init 컨테이너 확인

```bash
kubectl -n azure-otel get pods \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .spec.initContainers[*]}{.name}{", "}{end}{"\n"}{end}'
```

### B. App Insights 텔레메트리 확인

트래픽을 생성하고 2-3분 대기 후 Azure Portal의 Application Insights에서 확인합니다.

## 제한 사항 (프리뷰)

- **Windows 노드 풀**: 미지원
- **Python / .NET**: 제한적 프리뷰 (비공개 어노테이션 필요)
- **OTLP 형식**: OTLP/HTTP + binary Protobuf만 지원 (JSON, gRPC 미지원)
- **압축**: SDK 익스포터 압축 미지원
- **Istio mTLS**: 미지원

## 참고 자료

- [AKS 앱 OTLP 모니터링 (프리뷰)](https://learn.microsoft.com/azure/azure-monitor/containers/kubernetes-open-protocol)
- [AKS 앱 자동 계측](https://learn.microsoft.com/azure/azure-monitor/containers/kubernetes-codeless)
- [Python / .NET 제한적 프리뷰](https://learn.microsoft.com/azure/azure-monitor/containers/kubernetes-codeless-python-net)
