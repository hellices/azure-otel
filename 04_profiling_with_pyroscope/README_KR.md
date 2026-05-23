# 04 — Pyroscope SDK 로 Java 연속 프로파일링 (앱 무수정)

01·02·03 단계까지 끝나면 metrics + traces 가 모입니다. 이 단계에서는
**Spring Boot 서비스에 한정해서** 세 번째 시그널인 **profiling** 을
공식 [Pyroscope Java agent](https://github.com/grafana/pyroscope-java) 를
`-javaagent` 로 사이드카 주입하여 추가합니다 — 애플리케이션 이미지·소스
모두 무수정.

> English version: [README.md](./README.md)

![Pyroscope 플로우](../docs/diagrams/pyroscope-java-flow.png)

OpenTelemetry profiling 시그널은 2026-05 기준 아직 **Development** 단계
(OTLP `profiles` 데이터 모델은 있지만 SDK + spec 안정화 미완). Pyroscope
자체 SDK 가 현실적인 대안이고, 본 레포의 세 언어 중 **앱 수정 0 으로
주입 가능한 것은 Java 하나** 입니다:

| 서비스 | 코드 변경 없이 SDK 주입 가능? |
|---|---|
| Spring (Java) | ✅ `-javaagent` + 환경변수 (본 단계) |
| FastAPI (Python) | ❌ 부팅 시 `pyroscope.configure(...)` 호출 필요 |
| Next.js (Node) | ⚠️ `--require` 부트스트랩 스크립트 필요 |

Python·Node 는 본 레포 규칙(앱 무수정)에 맞지 않아 본 단계에서는 제외.
필요해지면 eBPF (Grafana Alloy `pyroscope.ebpf`) 나 `pyroscope-otel`
브릿지로 후속 단계에서 추가 가능.

```
spring pod (OTel javaagent + Pyroscope javaagent)
    │
    └─ HTTP push ─► pyroscope (클러스터 내) ─► UI :4040
                                                │
                                                └─ (선택) AGFC HTTPRoute
                                                   ─► AMG 데이터소스
```

| 구성요소 | 역할 |
|---|---|
| `pyroscope` (Helm, single binary) | 프로파일 저장소 + UI `:4040` |
| `spring-pyroscope-patch.yaml` | `pyroscope.jar` 다운로드 initContainer + JVM/서버 환경변수 |
| (선택) `HTTPRoute` (AGFC) | AMG 가 접근할 수 있게 게이트웨이 노출 |

`PYROSCOPE_APPLICATION_NAME=spring` 으로 두면 Pyroscope `service_name`
라벨이 02·03 단계 대시보드 `service=spring` 라벨과 같아져 메트릭 ↔
flame graph 점프가 자연스럽습니다.

## 사전 조건

- 01·02·03 단계가 동작 중. Spring deployment 이름은 `azure-otel-spring`.
- AKS pod 가 `github.com` 에 접근 가능해야 함 (기본 egress 열림). egress
  통제 환경이면 `pyroscope.jar` 를 ACR 에 미러하고 initContainer 이미지/URL
  수정.

## 1. Pyroscope 설치

> 아래 모든 명령은 `04_profiling_with_pyroscope/` 디렉토리에서 실행합니다.

```bash
cd 04_profiling_with_pyroscope    # 레포 루트에서

helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

helm upgrade --install pyroscope grafana/pyroscope \
  -n azure-otel \
  -f manifests/pyroscope-values.yaml

kubectl -n azure-otel rollout status statefulset/pyroscope --timeout=180s
```

## 2. Spring deployment 에 Pyroscope Java agent 주입

```bash
kubectl -n azure-otel patch deploy azure-otel-spring \
  --patch-file manifests/spring-pyroscope-patch.yaml
kubectl -n azure-otel rollout status deploy/azure-otel-spring --timeout=180s
```

두 javaagent 모두 로드됐는지 확인:

```bash
kubectl -n azure-otel logs deploy/azure-otel-spring --tail=20 | grep -iE 'pyroscope|javaagent|otel'
kubectl -n azure-otel exec deploy/azure-otel-spring -- printenv JAVA_TOOL_OPTIONS
# 기대값:
#   -javaagent:/pyroscope/pyroscope.jar -javaagent:/otel-auto-instrumentation-java/javaagent.jar
```

OTel Operator 의 mutating webhook 은 기존 `JAVA_TOOL_OPTIONS` 를 **보존하고
자기 javaagent 를 append** 하므로 두 agent 모두 충돌 없이 로드됩니다.

## 3. 인입 확인

CPU 부하 만들기:

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
alb=$(kubectl -n azure-otel get gateway azure-otel-gw -o 'jsonpath={.status.addresses[0].value}')
for i in $(seq 1 200); do curl -s "http://$alb/api/items" > /dev/null; done
```

</details>

<details open>
<summary><strong>Windows (PowerShell)</strong></summary>

```powershell
$alb = kubectl -n azure-otel get gateway azure-otel-gw -o 'jsonpath={.status.addresses[0].value}'
1..200 | ForEach-Object { Invoke-WebRequest -Uri "http://$alb/api/items" -UseBasicParsing | Out-Null }
```

</details>

Pyroscope UI port-forward:

```bash
kubectl -n azure-otel port-forward svc/pyroscope 4040:4040
# 브라우저: http://localhost:4040
```

UI 확인 포인트:

1. **Explore profiles** → `service_name = spring` 표시.
2. 사용 가능한 profile type (`PYROSCOPE_FORMAT=jfr` 덕분에):
   - `process_cpu / cpu (nanoseconds)` — on-CPU 샘플러 (`itimer`)
   - `memory / alloc_in_new_tlab_bytes` — 할당
   - `mutex / lock_count` — contended lock
3. Flame graph 에 `org.springframework.web.servlet.*`,
   `org.apache.tomcat.*`, `ItemController.list`, SQLite JDBC 드라이버
   같은 프레임이 보임.

## 4. (선택) AMG 에 Pyroscope 노출

### 4a. Gateway 라우팅

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
kubectl apply -f manifests/httproute.yaml
alb=$(kubectl -n azure-otel get gateway azure-otel-gw -o 'jsonpath={.status.addresses[0].value}')
echo "Pyroscope URL: http://$alb/pyroscope"
```

</details>

<details open>
<summary><strong>Windows (PowerShell)</strong></summary>

```powershell
kubectl apply -f manifests/httproute.yaml
$alb = kubectl -n azure-otel get gateway azure-otel-gw -o 'jsonpath={.status.addresses[0].value}'
Write-Host "Pyroscope URL: http://$alb/pyroscope"
```

</details>

### 4b. AMG 데이터소스 등록

`grafana-pyroscope-datasource` 는 AMG Standard (Grafana 12) 에 **코어
플러그인** 으로 이미 포함되어 있습니다. 별도 플러그인 설치 나
ARM `grafanaPlugins` 속성 설정 불필요 — Grafana HTTP API 로
데이터소스만 만들면 끝:

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
rg=$(azd env get-value AZURE_RESOURCE_GROUP --cwd ../01_deploy_to_aks)
gfn=$(az resource list -g "$rg" --resource-type Microsoft.Dashboard/grafana --query "[0].name" -o tsv)
gfEndpoint=$(az grafana show -n "$gfn" -g "$rg" --query properties.endpoint -o tsv)
alb=$(kubectl -n azure-otel get gateway azure-otel-gw -o 'jsonpath={.status.addresses[0].value}')
tok=$(az account get-access-token --resource "https://grafana.azure.com" --query accessToken -o tsv)

curl -sS -X POST "$gfEndpoint/api/datasources" \
  -H "Authorization: Bearer $tok" -H 'Content-Type: application/json' \
  -d "$(jq -n --arg url "http://$alb/pyroscope" '{
    name: "Pyroscope",
    type: "grafana-pyroscope-datasource",
    access: "proxy",
    url: $url
  }')"

# Health check
dsUid=$(curl -sS -H "Authorization: Bearer $tok" "$gfEndpoint/api/datasources/name/Pyroscope" | jq -r .uid)
curl -sS -H "Authorization: Bearer $tok" "$gfEndpoint/api/datasources/uid/$dsUid/health"
# 예상: status = OK, message = "Data source is working"
```

</details>

<details open>
<summary><strong>Windows (PowerShell)</strong></summary>

```powershell
$rg = azd env get-value AZURE_RESOURCE_GROUP --cwd ../01_deploy_to_aks
$gfn = az resource list -g $rg --resource-type Microsoft.Dashboard/grafana --query "[0].name" -o tsv
$gfEndpoint = az grafana show -n $gfn -g $rg --query properties.endpoint -o tsv
$alb = kubectl -n azure-otel get gateway azure-otel-gw -o 'jsonpath={.status.addresses[0].value}'
$tok = az account get-access-token --resource "https://grafana.azure.com" --query accessToken -o tsv

$body = @{ name="Pyroscope"; type="grafana-pyroscope-datasource"; access="proxy"; url="http://$alb/pyroscope" } | ConvertTo-Json
Invoke-RestMethod -Uri "$gfEndpoint/api/datasources" -Method Post `
  -Headers @{ Authorization="Bearer $tok"; "Content-Type"="application/json" } `
  -Body $body

# Health check
$ds = Invoke-RestMethod -Uri "$gfEndpoint/api/datasources/name/Pyroscope" `
  -Headers @{ Authorization="Bearer $tok" }
Invoke-RestMethod -Uri "$gfEndpoint/api/datasources/uid/$($ds.uid)/health" `
  -Headers @{ Authorization="Bearer $tok" }
```

</details>

UI 로 하려면: Grafana → **Connections → Add new data source → Pyroscope**
→ URL `http://<ALB>/pyroscope`.

Pyroscope OSS 는 자체 인증 없음 — 데모 외 환경에서는
[AMG Managed Private Endpoint](https://learn.microsoft.com/azure/managed-grafana/how-to-connect-to-data-source-privately)
또는 OAuth proxy 권장.

## 5. (선택, 앱 재빌드 필요) Span Profiles

span 단위 flame graph 는
[`pyroscope-otel`](https://github.com/grafana/otel-profiling-java)
javaagent 확장을 OTel agent 와 함께 로드해야 합니다
(`OTEL_JAVAAGENT_EXTENSIONS=/path/to/pyroscope-otel.jar`). 이를 위해선
03단계 `Instrumentation` CR 의 `spec.java.extensions` 를 확장해야 하므로
본 단계 범위 밖.

## 정리

```bash
# Patch 제거: 차트 재적용으로 deployment 원복
helm -n azure-otel upgrade azure-otel ../01_deploy_to_aks/azure-otel
kubectl delete -f manifests/httproute.yaml --ignore-not-found
helm -n azure-otel uninstall pyroscope
kubectl -n azure-otel delete pvc -l app.kubernetes.io/name=pyroscope
```

## 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| Init container 다운로드 실패 | AKS egress 가 `github.com` 차단. `pyroscope.jar` 를 ACR 에 미러 후 initContainer `image`/URL 수정 |
| Spring pod 는 떴는데 UI 에 `spring` 안 보임 | `JAVA_TOOL_OPTIONS` 가 어딘가에서 덮였음. `kubectl exec deploy/azure-otel-spring -- printenv JAVA_TOOL_OPTIONS` 로 두 `-javaagent` 모두 있는지 확인. OTel agent 가 빠졌다면 webhook 미동작 (cert-manager Ready? CR 적용 후 pod restart 했는지?) |
| Spring pod 로그에 `agent attach failed` | JDK 버전 미스매치. Pyroscope Java agent 는 JDK 8/11/17/21 지원. 더 최신 JDK 라면 patch 의 `PYROSCOPE_AGENT_VERSION` 상향 |
| Flame graph 가 거의 `[unknown]` | `async-profiler` (Pyroscope agent 내장) 가 `perf_event_paranoid <= 2` + frame-pointer 친화 라이브러리 필요. AKS Ubuntu 기본값 OK. 그래도 안되면 일회성 DaemonSet 으로 `sysctl -w kernel.perf_event_paranoid=1` |
| alloc / lock profile 안 보임 | `PYROSCOPE_FORMAT` 이 `jfr` 가 아님. 기본 `collapsed` 포맷은 CPU 만. `jfr` 유지 |
| 버전 올렸더니 `failed to load javaagent` | 새 버전 태그가 GitHub release URL 에 없음. <https://github.com/grafana/pyroscope-java/releases> 에서 유효한 태그로 변경 |
| AMG “Add data source” 목록에 Pyroscope 가 안 보임 | UI quirk — 코어 플러그인이지만 해당 타입 datasource 가 하나도 없으면 picker 에서 숨겨짐. step 4b 의 API 로 한 번 생성하면 이후 목록에 나타남 |
| ARM PATCH `grafanaPlugins.grafana-pyroscope-datasource` 가 BadRequest | 정상. 해당 datasource 는 코어 플러그인이라 ARM `listAvailablePlugins` allowlist 에 없음 (Drilldown 용 `grafana-pyroscope-app` 만 있음). ARM 단계 건너뛰고 Grafana API 로 datasource 만 생성 |
