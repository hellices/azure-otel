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
                        │                       │
                        │                       └─ (선택) AGFC HTTPRoute
                        │                          ─► AMG 데이터소스
                        └─ profile blocks ─► Azure Blob Storage
                           (AKS Workload Identity 연합 인증)
```

| 구성요소 | 역할 |
|---|---|
| `pyroscope` (Helm, single binary) | 프로파일 수집 + UI `:4040`; 블록은 **Azure Blob Storage** 에 영속화 |
| Azure Blob 컨테이너 `pyroscope` | 내구성 있는 프로파일 저장소 (`storage.backend: azure`) — pod/노드 유실에도 안전, PVC 불필요 |
| User-assigned identity + federated credential | 키 없는 인증: `pyroscope` ServiceAccount 토큰을 Entra ID 로 교환 (`Storage Blob Data Contributor`) |
| `spring-pyroscope-patch.yaml` | `pyroscope.jar` 다운로드 initContainer + JVM/서버 환경변수 |
| (선택) `HTTPRoute` (AGFC 전용) | AGFC 사용 시에만 AMG 접근용 게이트웨이 노출 |

PVC 대신 Blob 에 블록을 저장하는 방식은
[Continuous profiling on AKS with Pyroscope, Blob Storage and Managed Grafana](https://azureglobalblackbelts.com/2026/05/06/continuous-profiling-on-AKS-with-pyroscope-blob-storage-and-managed-grafana/)
(Azure Global Black Belts) 패턴을 따르되, 3-서비스 데모에 충분한
single-binary 모드로 단순화했습니다. 블로그의 microservices 구성은
스케일업 경로로 참고하세요.

`PYROSCOPE_APPLICATION_NAME=spring` 으로 두면 Pyroscope `service_name`
라벨이 02·03 단계 대시보드 `service=spring` 라벨과 같아져 메트릭 ↔
flame graph 점프가 자연스럽습니다.

## 사전 조건

- 01·02·03 단계가 동작 중. Spring deployment 이름은 `azure-otel-spring`.
- AKS pod 가 `github.com` 에 접근 가능해야 함 (기본 egress 열림). egress
  통제 환경이면 `pyroscope.jar` 를 ACR 에 미러하고 initContainer 이미지/URL
  수정.
- 스토리지 계정 / user-assigned identity 생성 권한과 해당 계정에
  `Storage Blob Data Contributor` 를 부여할 권한. 01단계 클러스터는 이미
  `--enable-oidc-issuer` + `--enable-workload-identity` 로 배포되므로
  (`01_deploy_to_aks/infra/resources.bicep`) 클러스터 변경은 불필요.

## 권장 진행 방식 (변경)

아래 순서로 진행하는 것을 기본으로 합니다.

1. 01~03 단계 완료 후 정상 동작 확인
2. 04 단계 점검용 리소스 그룹 생성
3. 04 단계 적용과 동시에 수집/접속 상태 확인

점검용 리소스 그룹 예시:

```bash
az group create -n rg-otel-04-check -l koreacentral
```

01~03 정상 여부 빠른 확인 예시:

```bash
kubectl -n azure-otel get deploy,pod,svc
kubectl -n azure-otel get instrumentation
kubectl -n azure-otel get podmonitor.azmonitoring.coreos.com
```

## 1. Azure Blob 스토리지 백엔드 만들기

Pyroscope 는 프로파일 **블록** 을 object storage 에 영속화합니다. Azure
네이티브 옵션은 Blob (`storage.backend: azure`) — 내구성 있고 저렴하며,
AKS Workload Identity 와 결합하면 계정 키가 전혀 필요 없습니다. PVC 는
만들지 않습니다.

> 아래 모든 명령은 `04_profiling_with_pyroscope/` 디렉토리에서 실행합니다.

```bash
cd 04_profiling_with_pyroscope    # 레포 루트에서

rg=$(azd env get-value AZURE_RESOURCE_GROUP --cwd ../01_deploy_to_aks)
loc=$(az group show -n "$rg" --query location -o tsv)
aks=$(az aks list -g "$rg" --query '[0].name' -o tsv)
sa="stpyro$RANDOM$RANDOM"          # 스토리지 계정 이름은 전역 유일해야 함
echo "$sa" > .storage-account      # 이후 단계 / 정리에서 재사용

# 1a. 스토리지 계정 — shared-key 인증 비활성, RBAC 전용
az storage account create -n "$sa" -g "$rg" -l "$loc" \
  --sku Standard_LRS --kind StorageV2 \
  --allow-shared-key-access false --min-tls-version TLS1_2

# 1b. User-assigned identity + blob RBAC
az identity create -n id-pyroscope -g "$rg"
principalId=$(az identity show -n id-pyroscope -g "$rg" --query principalId -o tsv)
saId=$(az storage account show -n "$sa" -g "$rg" --query id -o tsv)
az role assignment create --assignee-object-id "$principalId" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" --scope "$saId"

# 1c. 차트가 만드는 `pyroscope` ServiceAccount 용 federated credential
oidc=$(az aks show -n "$aks" -g "$rg" --query oidcIssuerProfile.issuerUrl -o tsv)
az identity federated-credential create --name pyroscope-federated \
  --identity-name id-pyroscope -g "$rg" \
  --issuer "$oidc" \
  --subject "system:serviceaccount:azure-otel:pyroscope" \
  --audiences api://AzureADTokenExchange
```

`az storage container create` 는 필요 없습니다 — Pyroscope 가 첫 기동 시
`pyroscope` 컨테이너를 직접 만듭니다 (identity 가 데이터 플레인
Contributor 이므로).

> **왜 Storage Blob Data Contributor?** Pyroscope 는 블록(segment,
> compacted block, tenant index)을 읽고 *쓰기* 때문. Reader 만으로는
> compactor 가 동작하지 않습니다.

## 2. Pyroscope 설치

```bash
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

sa=$(cat .storage-account)
clientId=$(az identity show -n id-pyroscope -g "$rg" --query clientId -o tsv)

helm upgrade --install pyroscope grafana/pyroscope \
  -n azure-otel \
  -f manifests/pyroscope-values.yaml \
  --version 2.2.0 \
  --set pyroscope.structuredConfig.storage.azure.account_name=$sa \
  --set-string "pyroscope.serviceAccount.annotations.azure\.workload\.identity/client-id=$clientId"

kubectl -n azure-otel rollout status statefulset/pyroscope --timeout=180s
```

차트 `--version` 은 고정하세요: 차트 2.x 는 1.x 이미지가 모르는 CLI
플래그를 렌더링하고 (`flag provided but not defined` 크래시),
`pyroscope.image.tag` 는 절대 하드코딩하지 마세요 — 차트 자신의
`appVersion` 이미지가 플래그와 맞는 조합입니다.

Blob 백엔드 정상 여부 확인 (federated 토큰 교환 + 버킷 접근):

```bash
kubectl -n azure-otel logs pyroscope-0 | grep -i "bucket health check"
# 기대값: msg="bucket health check succeeded"
kubectl -n azure-otel exec pyroscope-0 -- env | grep ^AZURE_
# 기대값: AZURE_CLIENT_ID / AZURE_TENANT_ID / AZURE_FEDERATED_TOKEN_FILE
```

`manifests/pyroscope-values.yaml`의 `api.base-url: /pyroscope`는 기본적으로 **주석 처리**되어 있습니다.
AGFC HTTPRoute 등 리버스 프록시를 통해 `/pyroscope` 경로로 노출할 때만 주석을 해제하세요.
port-forward로 직접 접근할 때 이 옵션이 켜져 있으면 UI asset 경로가 깨져 빈 화면이 됩니다.

## 3. Spring deployment 에 Pyroscope Java agent 주입

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

## 4. 인입 확인

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

블록이 Blob Storage 에 실제로 올라가는지도 확인 (부하 중 ~15초 간격 +
종료 시 flush):

```bash
kubectl -n azure-otel logs pyroscope-0 --tail=500 | grep "uploading blob"
# 기대 로그:
#   msg="uploading blob" blob=segments/1/anonymous/<ULID>/block.bin
#   msg="uploading blob" blob=blocks/1/anonymous/<ULID>/block.bin
```

이력이 Blob 에 있으므로 `kubectl delete pod pyroscope-0` 을 해도
프로파일이 사라지지 않습니다 — 재기동 후 같은 flame graph 가 그대로
조회됩니다.

## 5. (선택) AMG 에 Pyroscope 노출

기본 배포 모드가 **AppGW** 인 경우, 이 문서의 `HTTPRoute` 방법은 적용되지 않습니다.
현재 레포의 `manifests/httproute.yaml`은 **AGFC 사용 시 전용**입니다.
AppGW 모드에서는 우선 `kubectl port-forward svc/pyroscope 4040:4040`로 검증하고,
외부 노출이 필요하면 AppGW 백엔드 풀/경로 규칙을 별도로 추가하세요.

### 5a. Gateway 라우팅 (AGFC 전용)

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

### 5b. AMG 데이터소스 등록

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

## 6. (선택, 앱 재빌드 필요) Span Profiles

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

# Blob 쪽 정리 (프로파일은 PVC 가 아니라 스토리지 계정에 있음)
rg=$(azd env get-value AZURE_RESOURCE_GROUP --cwd ../01_deploy_to_aks)
sa=$(cat .storage-account)
az identity federated-credential delete --name pyroscope-federated \
  --identity-name id-pyroscope -g "$rg" --yes
az identity delete -n id-pyroscope -g "$rg"
az storage account delete -n "$sa" -g "$rg" --yes
rm -f .storage-account
```

## 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| Pyroscope pod 로그에 `WorkloadIdentityCredential: no client ID specified` | WI webhook 은 **pod** 에 `azure.workload.identity/use: "true"` 라벨이 있어야만 `AZURE_CLIENT_ID` / `AZURE_FEDERATED_TOKEN_FILE` 을 주입 — ServiceAccount annotation 만으로는 부족. values 의 `pyroscope.extraLabels` 가 이를 처리 (차트에 `podLabels` 없음). 구버전 릴리스 업그레이드 시엔 StatefulSet pod 를 삭제해 재생성 |
| Pyroscope pod 가 `flag provided but not defined: -query-backend.address` 로 크래시 | Helm 차트와 컨테이너 이미지 버전 불일치 (차트 2.x 플래그 vs 1.x 바이너리). `--version` 고정 유지, `pyroscope.image.tag` 하드코딩 금지 |
| Blob 요청이 403 `AuthorizationFailure` | 두 가지: (a) RBAC — identity 에 `Storage Blob Data Contributor` 필요 (Reader 부족); (b) 네트워크 — Azure Policy 가 계정의 `publicNetworkAccess: Disabled` 강제. (b) 는 AKS 서브넷에 `blob` private endpoint + `privatelink.blob.core.windows.net` DNS zone 을 AKS VNet 에 연결 후, pod 에서 `nslookup <sa>.blob.core.windows.net` 이 `10.x` IP 를 반환하는지 확인 |
| Init container 다운로드 실패 | AKS egress 가 `github.com` 차단. `pyroscope.jar` 를 ACR 에 미러 후 initContainer `image`/URL 수정 |
| Spring pod 는 떴는데 UI 에 `spring` 안 보임 | `JAVA_TOOL_OPTIONS` 가 어딘가에서 덮였음. `kubectl exec deploy/azure-otel-spring -- printenv JAVA_TOOL_OPTIONS` 로 두 `-javaagent` 모두 있는지 확인. OTel agent 가 빠졌다면 webhook 미동작 (cert-manager Ready? CR 적용 후 pod restart 했는지?) |
| Spring pod 로그에 `agent attach failed` | JDK 버전 미스매치. Pyroscope Java agent 는 JDK 8/11/17/21 지원. 더 최신 JDK 라면 patch 의 `PYROSCOPE_AGENT_VERSION` 상향 |
| Flame graph 가 거의 `[unknown]` | `async-profiler` (Pyroscope agent 내장) 가 `perf_event_paranoid <= 2` + frame-pointer 친화 라이브러리 필요. AKS Ubuntu 기본값 OK. 그래도 안되면 일회성 DaemonSet 으로 `sysctl -w kernel.perf_event_paranoid=1` |
| alloc / lock profile 안 보임 | `PYROSCOPE_FORMAT` 이 `jfr` 가 아님. 기본 `collapsed` 포맷은 CPU 만. `jfr` 유지 |
| 버전 올렸더니 `failed to load javaagent` | 새 버전 태그가 GitHub release URL 에 없음. <https://github.com/grafana/pyroscope-java/releases> 에서 유효한 태그로 변경 |
| AMG “Add data source” 목록에 Pyroscope 가 안 보임 | UI quirk — 코어 플러그인이지만 해당 타입 datasource 가 하나도 없으면 picker 에서 숨겨짐. step 5b 의 API 로 한 번 생성하면 이후 목록에 나타남 |
| ARM PATCH `grafanaPlugins.grafana-pyroscope-datasource` 가 BadRequest | 정상. 해당 datasource 는 코어 플러그인이라 ARM `listAvailablePlugins` allowlist 에 없음 (Drilldown 용 `grafana-pyroscope-app` 만 있음). ARM 단계 건너뛰고 Grafana API 로 datasource 만 생성 |
