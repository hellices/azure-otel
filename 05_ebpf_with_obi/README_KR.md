# 05 — eBPF 자동 계측 (OpenTelemetry OBI, 구 Grafana Beyla)

01·02·03 (또는 04) 까지 끝난 상태에서 **OpenTelemetry eBPF
Instrumentation (OBI)** 을 DaemonSet 으로 얹어, **앱 코드/이미지/SDK
주입 어느 것도 건드리지 않고** HTTP·gRPC·SQL span 과 RED 메트릭을
커널 레벨에서 추가로 뽑아냅니다.

> English version: [README.md](./README.md)

OBI 는 2025년 Grafana Beyla 가 OpenTelemetry 로 기증되어 incubating
단계에 들어간 프로젝트입니다 (2026-05 기준 chart/이미지는 여전히
`grafana/beyla` 네임스페이스에서 배포). syscall uprobe + TLS 가시성
(`SSL_read`/`SSL_write` uprobe) 으로 plaintext 와 TLS 트래픽 모두
관측 가능하고, 출력 형식은 OTLP 표준입니다.

| 항목 | 03 (OTel SDK + Collector) | 05 (OBI eBPF) |
|---|---|---|
| 위치 | 앱 프로세스 안 (Operator 가 javaagent/`--require`/sitecustomize 주입) | 노드 커널 hook (DaemonSet) |
| 앱 재시작 필요 | ✅ (annotation 변경 시) | ❌ |
| 새 언어 추가 비용 | language-specific autoinstrumentation 이미지 필요 | 없음 (커버되는 런타임이면 자동) |
| 캡처 정밀도 | function-level span, custom attribute | HTTP/gRPC/SQL boundary + Kubernetes 메타데이터 |
| TLS 내부 가시성 | 자연스러움 (앱 안에서 보니까) | uprobe 가 OpenSSL/BoringSSL 심볼 잡을 때만 |
| Span context propagation | 완전 (W3C tracecontext 자동 inject/extract) | **제한적** — 들어오는 헤더는 읽지만 outbound inject 는 일부 런타임만 |

→ 공존시키는 게 정석입니다 (옵션 A). 03 이 못 따라가는 경계
(SDK 가 없는 사이드카, init container, 외부 바이너리, k8s 컨트롤
플레인 트래픽) 를 OBI 가 메우고, traces 의 propagation 은 SDK 가
담당.

```
            ┌─────────────────────────────  node ─────────────────────────────┐
            │                                                                 │
[traffic] ──┼──► app pod (OTel SDK, 03이 주입)                                 │
            │       │ OTLP                                                    │
            │       ▼                                                         │
            │   otel-collector ──► AppI / AMW                                 │
            │       ▲                                                         │
            │       │ OTLP (eBPF spans, RED metrics)                          │
            │   obi DaemonSet ──── 커널 uprobe/kprobe/tracepoint              │
            └─────────────────────────────────────────────────────────────────┘
```

## 사전 조건

- 01·02·03 단계가 동작 중 (`azure-otel` 네임스페이스, OTel Collector
  서비스 `otel-collector:4317`).
- AKS 노드 OS = Ubuntu 22.04+ (kernel ≥ 5.15). AzureLinux 노드도
  지원되지만 BTF/CO-RE 활성 커널 빌드여야 함.
- 클러스터에 04 의 Pyroscope 가 함께 떠 있어도 무방 (아래 §6 참고).

## 옵션 A — 03 위에 얹기 (권장)

03 의 SDK trace 와 OBI eBPF span 은 같은 요청을 두 번 기록합니다.
다음 중 하나로 정리:

1. **OBI traces 끄고 metrics 만** (가장 안전한 디폴트)
   - `BEYLA_TRACES_ENABLED=false`, `BEYLA_METRICS_ENABLED=true`
   - SDK 가 trace 를, OBI 가 RED metric / 미계측 워크로드만 담당
2. **OBI traces 켜되 03 이 커버한 워크로드 제외**
   - `discovery.services` 의 매칭에서 nodejs/python/spring deployment 빼기
3. **Collector 단에서 디듀프**
   - `processor: filter` 로 `resource.attributes["telemetry.sdk.name"] == "beyla"` 인 span 중 03 SDK 와 같은 trace_id 를 가진 것 drop. 비용/복잡도 큼 — 1 번을 권장.

## 옵션 B — 03 빼고 OBI 단독

SDK 주입을 제거하면 노드/파이썬/자바 이미지 빌드 변경 없이 **세 언어
모두 동일한 방식** 으로 관측됩니다. 다만 위 표 마지막 줄 처럼
trace context propagation 이 약해져 cross-service trace 연결이
끊어질 수 있습니다 (특히 Node → Python 같은 outbound HTTP 호출).

```bash
# 03 의 Instrumentation CR 제거 → OTel Operator webhook 이 더 이상 주입 안 함
kubectl -n azure-otel delete instrumentation azure-otel --ignore-not-found

# 이미 주입된 pod 의 init container/env 를 떨어내려면 helm 차트 재적용
helm -n azure-otel upgrade azure-otel ../01_deploy_to_aks/azure-otel
kubectl -n azure-otel rollout restart deploy azure-otel-spring azure-otel-python azure-otel-nodejs
```

03 의 collector 자체는 그대로 두는 게 좋습니다 — OBI 의 OTLP egress
타깃이 되어 주고, AppI/AMW exporter 분기를 그대로 재사용합니다.

## 1. OBI 설치

[`manifests/obi-values.yaml`](manifests/obi-values.yaml) 에 커널
capability, Kubernetes 메타데이터 enrichment, namespace discovery, OTLP
출력 설정이 들어 있습니다. 옵션 A (디폴트) ↔ B 전환은 `env:` 섹션에서.

> 아래 모든 명령은 `05_ebpf_with_obi/` 디렉토리에서 실행합니다.

```bash
cd 05_ebpf_with_obi    # 레포 루트에서

helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

helm upgrade --install obi grafana/beyla \
  -n azure-otel \
  -f manifests/obi-values.yaml

kubectl -n azure-otel rollout status ds/obi --timeout=180s
```

> chart 가 `open-telemetry/opentelemetry-ebpf-instrumentation` 으로
> 옮겨가면 `helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts`
> 후 chart 이름만 바꿔주면 됩니다. value schema 는 동일.

## 2. RBAC

`config.attributes.kubernetes.enable=true` 가 켜져 있으면 OBI 가
Pod/Service/ReplicaSet 을 watch 합니다. 기본 chart 가 ClusterRole 을
만들지만 명시 확인:

```bash
kubectl get clusterrole obi -o yaml | grep -E 'pods|services|replicasets|nodes'
# 기대값: get/list/watch on pods, services, replicasets, nodes
```

## 3. 인입 확인

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
alb=$(kubectl -n azure-otel get gateway azure-otel-gw -o 'jsonpath={.status.addresses[0].value}')
for i in $(seq 1 50); do curl -s "http://$alb/api/items" > /dev/null; done

# OBI 로그
kubectl -n azure-otel logs ds/obi --tail=30 | grep -iE 'service|trace|metric|discover'

# Collector 가 OBI 로부터 OTLP 를 받고 있는지
kubectl -n azure-otel logs deploy/otel-collector --tail=50 | grep -iE 'beyla|obi|telemetry.sdk.name'
```

</details>

<details open>
<summary><strong>Windows (PowerShell)</strong></summary>

```powershell
$alb = kubectl -n azure-otel get gateway azure-otel-gw -o 'jsonpath={.status.addresses[0].value}'
1..50 | ForEach-Object { Invoke-WebRequest -Uri "http://$alb/api/items" -UseBasicParsing | Out-Null }

# OBI 로그
kubectl -n azure-otel logs ds/obi --tail=30 | Select-String -Pattern 'service|trace|metric|discover'

# Collector 가 OBI 로부터 OTLP 를 받고 있는지
kubectl -n azure-otel logs deploy/otel-collector --tail=50 | Select-String -Pattern 'beyla|obi|telemetry.sdk.name'
```

</details>

App Insights (옵션 B 또는 옵션 A-2) Kusto:

```kusto
requests
| where timestamp > ago(15m)
| where customDimensions["telemetry.sdk.name"] == "beyla"
| summarize count() by cloud_RoleName, name
```

Grafana — 02 단계 대시보드의 RED 패널이 `service_name` 라벨로 그대로
잡힙니다 (OBI 가 `k8s.deployment.name` → `service.name` 매핑).

## 4. Cilium 과의 공존 정리

01 의 AKS 는 **Azure CNI Powered by Cilium** 으로 떠 있습니다
(`networkPolicy: cilium`, `networkDataplane: cilium`). eBPF 슬롯/네임스페이스가
같은 노드에서 다음 셋이 동시에 hook 을 답니다:

- Cilium agent — `tc`, `cgroup`, `socket` hooks (KPR socket-LB 포함)
- (선택) 04 Pyroscope 의 async-profiler — `perf_event` 샘플링
- 05 OBI — uprobe(`SSL_read`, `accept4`, `connect`), kprobe, raw tracepoint

### 4a. NetworkPolicy

OBI DaemonSet egress 가 `otel-collector:4317` 로 나갈 수 있어야 합니다.
01 의 `networkpolicy.yaml` 가 azure-otel 네임스페이스에 default-deny 를
걸어 두므로, OBI ServiceAccount/Pod label 을 collector 의 ingress 룰에
명시 추가:

```bash
# 어떤 label 로 떴는지 확인
kubectl -n azure-otel get pod -l app.kubernetes.io/name=beyla -o 'jsonpath={range .items[*]}{.metadata.labels}{"\n"}{end}'
```

`01_deploy_to_aks/azure-otel/templates/networkpolicy.yaml` 의 collector
ingress 에 OBI label selector 추가 후 `helm upgrade`.

### 4b. Cilium socket-LB 와 peer 식별

Cilium KPR socket-LB 는 `connect()` syscall 시점에 dest IP 를 backend
Pod IP 로 치환합니다. OBI 가 syscall 을 hook 하므로 보이는 peer 는
ClusterIP 가 아닌 **실제 Pod IP**. `service.name` 매칭은 OBI 의
Kubernetes metadata enricher 에 의존하므로 §2 의 RBAC 가 빠지면
spans 의 peer.service 가 `unknown` 이 됩니다.

### 4c. Hubble L7 와 중복 (해당될 때)

본 레포는 Advanced Container Networking Services (ACNS) 를 켜지
않지만, 추후 켤 경우 Hubble L7 visibility 와 OBI HTTP span 이
중복됩니다. 권장:

- Hubble = L4 flow + 정책 결정 + 보안 감사
- OBI    = L7 application span / RED metric / trace
- Hubble metrics 에서 `http` 카테고리 끄기 (`hubble.metrics.enabled` 에서 `httpV2` 등 제거)

### 4d. eBPF 리소스 한도

세 컴포넌트가 verifier/JIT/`memlock` 한도를 공유합니다. 노드에서:

```bash
kubectl debug node/<node> -it --image=ubuntu -- bash -c 'ulimit -l; sysctl bpf_jit_limit; bpftool prog show | wc -l'
```

`memlock` 이 `unlimited` 가 아니면 OBI/Pyroscope program load 가
`Operation not permitted` 로 떨어집니다. AKS Ubuntu 노드 기본은 OK
지만, 커스텀 nodepool/`AKSCustomNodeConfig` 사용 중이면 확인.

## 5. (옵션) zero-code propagation 보강

OBI 가 incoming 요청에서 `traceparent` 헤더를 읽기는 해도 outbound
호출에 자동 inject 하는 건 일부 런타임만 (Go runtime, 일부 libc
경로). Node/Python/Java 의 cross-service trace 연결을 보장하려면
**옵션 A 를 유지** (SDK 가 propagation 을 담당) 가 정답입니다.

옵션 B 단독으로 가야 하는 사정이 있다면:

```yaml
env:
  BEYLA_BPF_HTTP_REQUEST_TIMEOUT: "30s"
  # 실험적: outbound HTTP/HTTPS context propagation 강제
  BEYLA_BPF_TRACK_REQUEST_HEADERS: "true"
```

이 옵션은 커널 5.17+ 에서만 안정적이며 일부 TLS 라이브러리에서
flake 가 보고됩니다.

## 6. 04 (Pyroscope) 와의 공존

문제 없음. Pyroscope Java agent 는 in-process(`async-profiler`),
OBI 는 노드 커널 — hook 영역이 다릅니다. 단, 두 시그널을 같은
`service.name` 으로 묶어 두면 Grafana Drilldown 에서 **Profile ↔
Trace ↔ Metric** 점프가 자연스럽습니다:

- 04 의 `PYROSCOPE_APPLICATION_NAME=spring`
- 02·03 의 `service` 라벨 = `spring`
- OBI 의 `k8s.deployment.name` = `azure-otel-spring` →
  `service.name=spring` 으로 정규화하려면 collector 에서 transform:

```yaml
processors:
  transform/obi_service_name:
    metric_statements:
      - context: resource
        statements:
          - replace_pattern(attributes["service.name"], "^azure-otel-", "")
    trace_statements:
      - context: resource
        statements:
          - replace_pattern(attributes["service.name"], "^azure-otel-", "")
```

## 정리

```bash
helm -n azure-otel uninstall obi
kubectl -n azure-otel delete cm obi-config --ignore-not-found
# (옵션 B 로 갔다가 03 으로 복귀하려면)
kubectl apply -f ../03_otel_observability/manifests/instrumentation.yaml
kubectl -n azure-otel rollout restart deploy azure-otel-spring azure-otel-python azure-otel-nodejs
```

## 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| OBI pod `CrashLoopBackOff`, 로그에 `failed to load BPF program: permission denied` | securityContext 의 capability 빠짐. `BPF`, `PERFMON`, `SYS_PTRACE` 필수. AzureLinux/Mariner 노드면 `privileged: true` 필요할 수도 |
| pod 는 떴는데 span/metric 이 0 | `discovery.services` 매칭 안 됨. `kubectl logs ds/obi -- | grep 'discovered service'` 로 확인. label selector / namespace 오타 흔함 |
| span 의 `service.name` 이 IP 또는 `unknown` | RBAC 누락 — ClusterRole 에 pods/services/replicasets get/list/watch 있는지 확인 |
| Collector 가 OBI 트래픽을 거부 | 01 networkpolicy default-deny. §4a 대로 ingress 룰에 OBI selector 추가 |
| 같은 요청에 trace 가 두 개 (SDK + OBI) | 옵션 A-1 (`BEYLA_TRACES_ENABLED=false`) 미적용. 또는 A-2 의 deployment exclude 정규식 누락 |
| HTTPS 트래픽 span 누락 | OBI 가 OpenSSL/BoringSSL 심볼을 못 잡음. 컨테이너 베이스 이미지가 musl (alpine) 이거나 statically-linked 일 때 자주 발생. distroless/Ubuntu 로 베이스 변경 |
| Cilium hubble metrics 와 라벨 카디널리티 폭발 | OBI `service.name` × Hubble `destination_workload` × pod label → AMW active series 폭증. §4c 대로 Hubble L7 끄기 |
| 노드 부팅 직후 일부 pod 만 안 잡힘 | OBI DS 가 노드의 다른 Pod 보다 늦게 뜸 — `priorityClassName: system-node-critical` + `tolerations` 추가 |
