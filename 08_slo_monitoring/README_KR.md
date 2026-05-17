# 08 — Sloth를 이용한 SLO 모니터링

azure-otel 샘플 앱에 대한 **Service Level Objectives (SLO)**를 정의하고,
[Sloth](https://github.com/slok/sloth)로 Prometheus recording rules +
multi-window multi-burn-rate alert를 자동 생성합니다.

> English version: [README.md](./README.md)

## SLO vs RED — 다릅니다

| 개념 | RED 메서드 | SLO 모니터링 |
|---|---|---|
| **무엇** | 메트릭 방법론 (Rate, Errors, Duration) | 목표 프레임워크 + 예산 기반 알림 |
| **답하는 질문** | "지금 에러율이 얼마야?" | "이번 달 99.9% 목표를 지킬 수 있을까?" |
| **출력** | 대시보드 패널 | 에러 버짓 잔량, burn-rate 알림 |

## 정의된 SLO

| SLO | 목표 | SLI (나쁜 이벤트) |
|---|---|---|
| `http-availability` | 99.9% | 전체 서비스 HTTP 5xx (Node.js/Python + Spring 메트릭 결합) |
| `http-latency-p99` | 99% | 500ms 초과 요청 (Node.js + Python만, 밀리초 메트릭) |
| `spring-availability` | 99.5% | Spring 백엔드 HTTP 5xx |

## 사전 요구 사항

- 01 + 02단계 실행 중 (Prometheus 메트릭 수집 중).
- Sloth CLI 설치 (brew tap 사용 불가, 바이너리 직접 다운로드):
  ```bash
  curl -sSL https://github.com/slok/sloth/releases/latest/download/sloth-darwin-arm64 \
    -o /usr/local/bin/sloth && chmod +x /usr/local/bin/sloth
  ```

## 1. 규칙 생성

```bash
cd 08_slo_monitoring
sloth generate -i manifests/slo.yaml -o manifests/generated-rules.yaml
```

## 2. 규칙 적용

```bash
kubectl apply -f manifests/generated-rules.yaml
```

## 3. Grafana 대시보드 임포트

```bash
grafana=$(azd env get-value GRAFANA_ENDPOINT --cwd ../01_deploy_to_aks)
token=$(az account get-access-token \
  --resource ce34e7e5-485f-4d76-964f-b3d2b16d1e4f \
  --query accessToken -o tsv)

curl -sS "https://grafana.com/api/dashboards/14348/revisions/latest/download" \
  | jq '{dashboard: (. | .id = null), overwrite: true, folderId: 0}' \
  | curl -sS -X POST "$grafana/api/dashboards/db" \
    -H "Authorization: Bearer $token" \
    -H 'Content-Type: application/json' \
    --data-binary @-
```

## 알림 이해

| 알림 | 조건 | 의미 |
|---|---|---|
| **Page** (critical) | 14.4× burn / 5m + 6× / 30m | 1시간 내 월간 예산 소진 |
| **Ticket** (warning) | 3× burn / 2h + 1× / 1d | 10일 내 예산 소진 |

## 참고

- [Sloth 문서](https://sloth.dev/)
- [Google SRE Workbook — SLO 알림](https://sre.google/workbook/alerting-on-slos/)
