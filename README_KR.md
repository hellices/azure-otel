# azure-otel

> English version: [README.md](./README.md)

AKS 위에서 동작하는 multi-language 애플리케이션을 **Azure Monitor + OpenTelemetry**
스택으로 관측하는 방식의 **표준 패턴을 실험·정리**하는 레포입니다.

다음 세 가지 주제를 단계별로 다룹니다:

1. **AKS + 모니터링 인프라 프로비저닝** (Bicep + azd)
2. **메트릭만 먼저** — SDK Prometheus exporter + AKS managed Prometheus + Grafana
3. **OTLP 표준화** — OpenTelemetry Collector로 traces는 App Insights, metrics는
   AMA scrape, 모든 인입은 AMPLS Private Endpoint 경유

각 단계는 자체 README를 갖고 있고, 앞 단계 산출물 위에 그대로 쌓이는 구조입니다.

## 샘플 워크로드 (`base_apps/`)

표준을 검증하기 위해 의도적으로 언어를 섞은 3-tier 앱을 사용합니다.

| 서비스 | 언어 / 프레임워크 | 역할 | 포트 |
|---|---|---|---|
| `nodejs` | Next.js (TypeScript) | SPA shell | 3000 |
| `python` | FastAPI | Edge / proxy | 8000 |
| `spring` | Spring Boot (Java) | CRUD + SQLite | 8080 |

호출 흐름: `브라우저 → nodejs → python → spring`. 모든 서비스는
OpenTelemetry auto-instrumentation 호환 컨테이너로 빌드됩니다.

## 단계별 가이드

### [`01_deploy_to_aks/`](./01_deploy_to_aks)
azd + Bicep으로 AKS · ACR · Log Analytics · Application Insights · Azure Monitor
Workspace · Managed Grafana · AGFC (Gateway API) · **AMPLS + Private Endpoint
(5개 Private DNS Zone 포함)** 까지 한 번에 프로비저닝하고 Helm으로 샘플 앱을
배포합니다.

### [`02_metrics_via_podmonitor/`](./02_metrics_via_podmonitor)
OpenTelemetry Operator + Instrumentation CR로 SDK가 `:9464/metrics` 를 노출하게
만들고 `PodMonitor` 로 ama-metrics 가 직접 스크레이프하게 합니다. 가장 빨리
"Grafana 에 RED 메트릭 띄우기" 가 목표.

### [`03_otel_observability/`](./03_otel_observability)
SDK는 OTLP/gRPC만 쓰고 클러스터 안의 OTel Collector 가 분기:
- **traces** → `azuremonitor` exporter → Application Insights (AMPLS 경유, private)
- **metrics** → `prometheus` exporter → ama-metrics scrape → AMW → Grafana

02단계 대시보드는 그대로 재사용 (라벨 매핑은 collector 의 `transform` 프로세서가 처리).

## 전체 아키텍처

```
                                 ┌──────────────── private VNet ───────────────┐
                                 │                                              │
[Internet] ─► AGFC ─► AKS ─► app pod (OTel SDK, OTLP/gRPC)                      │
                              │                                                 │
                              ▼                                                 │
                       otel-collector ─┬─► Application Insights (via AMPLS PE)  │
                                       │                                        │
                                       └─► :8889 ◄─ ama-metrics ─► AMW ─► Grafana
                                 │                                              │
                                 └──────────────────────────────────────────────┘
```

자세한 그림은 [`docs/diagrams/`](./docs/diagrams) 참고 (Excalidraw).

## 빠른 시작

```powershell
# 1. 인프라 + Helm 배포
cd 01_deploy_to_aks
azd up
# (README의 Helm install 명령 실행)

# 2. 메트릭 파이프라인
kubectl apply -f ..\02_metrics_via_podmonitor\manifests\

# 3. OTLP / Collector 로 전환
cd ..\
# 02단계 산출물 정리 후 03_otel_observability/README.md 따라 진행
```

각 단계 README가 정확한 명령과 검증 방법을 포함합니다.

## 사용 기술

- **Compute / Network**: AKS (Azure CNI overlay + Cilium), AGFC (Gateway API), VNet, Private Endpoint
- **Observability**: OpenTelemetry SDK / Operator / Collector, Application Insights, Azure Monitor Workspace (managed Prometheus), Azure Managed Grafana, AMPLS
- **Build / Deploy**: Bicep, Azure Developer CLI (azd), Helm, GitHub Container Registry
