# 03 — OTLP Collector → App Insights (traces) + AMA scrape (metrics)

> English version: [README.md](./README.md)

01·02 단계가 끝난 클러스터에서 SDK가 직접 노출하던 `:9464/metrics` 경로를
**OTel Collector** 한 단계 뒤로 옮깁니다. SDK는 OTLP 만 쓰고, collector가:

- **traces** → `azuremonitor` exporter → Application Insights (AMPLS 경유)
- **metrics** → `prometheus` exporter `:8889` → ama-metrics 스크레이프 → AMW

```
app pod ─OTLP─► otel-collector ─┬─► AppI (private via AMPLS)
                                └─► :8889/metrics ◄─ ama-metrics ─► AMW ─► Grafana
```

언어별 OTLP 프로토콜 (`instrumentation.yaml`):

| 언어 | OTLP 프로토콜 | Collector 포트 |
|---|---|---|
| Java   | gRPC          | 4317 |
| Node   | gRPC          | 4317 |
| Python | HTTP/protobuf | 4318 |

Python만 HTTP를 쓰는 이유: 업스트림 `autoinstrumentation-python` 이미지가
`opentelemetry-exporter-otlp-proto-http`만 번들하고 gRPC exporter는 빼놓았습니다
(무거운 native `grpcio` wheel 회피). `grpc`를 강제하면 부팅 시
`Requested component 'otlp_proto_grpc' not found` 에러가 떨어집니다.

`traces` 파이프라인은 `batch` 앞에서 `filter/drop_healthchecks` 를 거쳐
`/health`, `/healthz`, `/livez`, `/readyz` span을 drop합니다 — probe 트래픽이
App Insights 를 오염시키지 않도록. 헤스체크 **메트릭**은 그대로
남겨둡니다 (Grafana 가용성 패널에 필요).

AMPLS / Private Endpoint / Private DNS Zone 은 01단계 Bicep 에서 이미 만들어
두므로 여기서는 별도 인프라 작업이 없습니다.

## 0. 02단계 정리

```powershell
kubectl -n azure-otel delete podmonitor.azmonitoring.coreos.com azure-otel-apps --ignore-not-found
kubectl -n azure-otel delete instrumentation azure-otel --ignore-not-found
```

## 1. Connection String Secret + 매니페스트 적용

```powershell
kubectl -n azure-otel create secret generic otel-collector-secrets `
  --from-literal=APPLICATIONINSIGHTS_CONNECTION_STRING="$(azd env get-value APPLICATION_INSIGHTS_CONNECTION_STRING)" `
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f .\03_otel_observability\manifests\collector.yaml
kubectl apply -f .\03_otel_observability\manifests\instrumentation.yaml

kubectl -n azure-otel rollout status deploy/otel-collector --timeout=180s
kubectl -n azure-otel rollout restart deploy azure-otel-spring azure-otel-python azure-otel-nodejs
```

ama-metrics가 새 PodMonitor를 못 보면 한 번 재시작:

```powershell
kubectl -n kube-system rollout restart deploy/ama-metrics
```

## 2. 동작 확인

```powershell
kubectl -n azure-otel logs deploy/otel-collector --tail=50

# 메트릭이 :8889/metrics 로 나오는지
kubectl -n azure-otel port-forward deploy/otel-collector 8889:8889
curl.exe -s http://localhost:8889/metrics | Select-String http_server_request_duration_seconds_count -List
```

App Insights → **Transaction search** 또는 Logs:

```kusto
requests | where timestamp > ago(15m)
| summarize count() by cloud_RoleName, name
```

`cloud_RoleName` 으로 `spring`, `python`, `nodejs` 가 보이면 OK. Grafana에서는
02단계 대시보드가 그대로 동작합니다.

## 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| Operator webhook이 init container 안 붙임 | cert-manager / Operator Pod Ready 확인. CR 적용 후 앱 파드는 한 번 restart 필요 |
| Collector 로그에 `connection refused` (azuremonitor) | AMPLS Private DNS 미동작. `kubectl -n azure-otel exec deploy/otel-collector -- nslookup <region>.in.applicationinsights.azure.com` 가 사설 IP 반환해야 함 |
| AppI Live Metrics는 OK인데 Transaction 비어있음 | Connection String Secret 미반영 — Secret 재생성 후 collector restart |
| Grafana에 메트릭 0 | ama-metrics가 새 PodMonitor 인식 못함. `kubectl -n kube-system rollout restart deploy/ama-metrics` |
| 메트릭 라벨(`service`, `k8s_pod`) 누락 | OTel SDK 버전 차이. `:8889/metrics` raw 출력 보고 `transform/prom_labels` 매핑 조정 |
| Python pod 로그에 `Requested component 'otlp_proto_grpc' not found` | Python auto-instrument 이미지에 gRPC exporter가 없음. `instrumentation.yaml` 의 python 블록은 `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` + `:4318` 으로 유지 |
| App Insights에 여전히 health-check span이 보임 | 앱이 비표준 probe path를 쓰는 경우. `collector.yaml` 의 `filter/drop_healthchecks` 정규식에 해당 path 추가 |
