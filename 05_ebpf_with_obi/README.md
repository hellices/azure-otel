# 05 — eBPF auto-instrumentation with OpenTelemetry OBI (formerly Grafana Beyla)

With stages 01·02·03 (or through 04) running, this stage layers
**OpenTelemetry eBPF Instrumentation (OBI)** on top as a DaemonSet.
It captures HTTP / gRPC / SQL spans and RED metrics from the kernel —
**no application code, image, or SDK injection changes required**.

> Korean version: [README_KR.md](./README_KR.md)

OBI is the OpenTelemetry incubating project that absorbed Grafana Beyla
in 2025 (as of 2026-05 the chart and image still ship from the
`grafana/beyla` namespace). It hooks syscalls and OpenSSL/BoringSSL
uprobes (`SSL_read` / `SSL_write`), so plaintext and TLS traffic are
both visible. Output is plain OTLP.

| Aspect | 03 (OTel SDK + Collector) | 05 (OBI eBPF) |
|---|---|---|
| Where it runs | Inside the app process (Operator injects javaagent / `--require` / sitecustomize) | Node kernel hooks (DaemonSet) |
| App restart needed | ✅ when annotations change | ❌ |
| Cost to add a new language | New language-specific autoinstrumentation image | Free, if the runtime is supported |
| Capture fidelity | Function-level spans, custom attributes | HTTP / gRPC / SQL boundaries + Kubernetes metadata |
| TLS visibility | Natural (lives inside the app) | Only when uprobes can resolve OpenSSL / BoringSSL symbols |
| Span context propagation | Full (W3C tracecontext auto-injected and extracted) | **Limited** — incoming headers are read, outbound injection works only on a few runtimes |

→ Run them together (option A, recommended). OBI fills in the gaps that
03 cannot reach (sidecars without an SDK, init containers, external
binaries, control-plane traffic) while the SDK keeps owning trace
propagation.

```
            ┌─────────────────────────────  node ─────────────────────────────┐
            │                                                                 │
[traffic] ──┼──► app pod (OTel SDK injected by 03)                            │
            │       │ OTLP                                                    │
            │       ▼                                                         │
            │   otel-collector ──► AppI / AMW                                 │
            │       ▲                                                         │
            │       │ OTLP (eBPF spans, RED metrics)                          │
            │   obi DaemonSet ──── kernel uprobe / kprobe / tracepoint        │
            └─────────────────────────────────────────────────────────────────┘
```

## Prerequisites

- Stages 01·02·03 are running (`azure-otel` namespace, OTel Collector
  reachable at `otel-collector:4317`).
- AKS node OS = Ubuntu 22.04+ (kernel ≥ 5.15). AzureLinux nodes work
  too if the kernel was built with BTF / CO-RE.
- Stage 04 (Pyroscope) may coexist — see §6.

## Option A — layer OBI on top of 03 (recommended)

03's SDK trace and an OBI eBPF span can both record the same request.
Pick one of the following to deduplicate:

1. **Disable OBI traces, keep metrics only** (the safest default)
   - `BEYLA_TRACES_ENABLED=false`, `BEYLA_METRICS_ENABLED=true`
   - SDK owns traces; OBI owns RED metrics + any workload the SDK does
     not cover.
2. **Keep OBI traces but exclude workloads already covered by 03**
   - Drop nodejs/python/spring deployments from `discovery.services`.
3. **Deduplicate at the collector**
   - Use a `filter` processor to drop spans whose
     `resource.attributes["telemetry.sdk.name"] == "beyla"` and that
     share a trace_id with an SDK span. High cost / complexity —
     prefer option 1.

## Option B — drop 03, run OBI alone

Removing the SDK injection means all three languages are observed the
same way without rebuilding any image. The downside is the last row of
the table above: trace context propagation becomes spotty, so
cross-service traces (especially Node → Python outbound HTTP) may
break.

```bash
# Remove the Instrumentation CR so the OTel Operator stops mutating new pods
kubectl -n azure-otel delete instrumentation azure-otel --ignore-not-found

# Strip the init containers / env from already-running pods by re-applying the chart
helm -n azure-otel upgrade azure-otel ../01_deploy_to_aks/azure-otel
kubectl -n azure-otel rollout restart deploy azure-otel-spring azure-otel-python azure-otel-nodejs
```

Keep 03's collector deployment in place — OBI will use it as its OTLP
endpoint and reuse the AppI / AMW exporter fan-out.

## 1. Install OBI

The values file at [`manifests/obi-values.yaml`](manifests/obi-values.yaml) configures
kernel capabilities, Kubernetes metadata enrichment, namespace discovery,
and OTLP output to the stage-03 collector. Edit the `env:` section to
switch between option A (default) and option B.

> All commands below assume you are inside `05_ebpf_with_obi/`.

```bash
cd 05_ebpf_with_obi    # from repo root

helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

helm upgrade --install obi grafana/beyla \
  -n azure-otel \
  -f manifests/obi-values.yaml

kubectl -n azure-otel rollout status ds/obi --timeout=180s
```

> When the chart migrates to
> `open-telemetry/opentelemetry-ebpf-instrumentation`, swap the repo URL
> and chart name — the values schema is unchanged.

## 2. RBAC

`config.attributes.kubernetes.enable=true` makes OBI watch
Pod / Service / ReplicaSet objects. The chart creates the ClusterRole,
but verify:

```bash
kubectl get clusterrole obi -o yaml | grep -E 'pods|services|replicasets|nodes'
# Expect: get/list/watch on pods, services, replicasets, nodes
```

## 3. Verify ingestion

```bash
alb=$(kubectl -n azure-otel get gateway azure-otel-gw -o 'jsonpath={.status.addresses[0].value}')
for i in $(seq 1 50); do curl -s "http://$alb/api/items" > /dev/null; done

# OBI logs
kubectl -n azure-otel logs ds/obi --tail=30 | grep -iE 'service|trace|metric|discover'

# Collector receiving OBI OTLP
kubectl -n azure-otel logs deploy/otel-collector --tail=50 | grep -iE 'beyla|obi|telemetry.sdk.name'
```

App Insights (option B or A-2) Kusto:

```kusto
requests
| where timestamp > ago(15m)
| where customDimensions["telemetry.sdk.name"] == "beyla"
| summarize count() by cloud_RoleName, name
```

In Grafana the stage-02 RED panels keep working — OBI maps
`k8s.deployment.name` → `service.name`, which is the same label your
dashboards already use.

## 4. Coexisting with Cilium

Stage 01 brings up AKS with **Azure CNI Powered by Cilium**
(`networkPolicy: cilium`, `networkDataplane: cilium`). Up to three
eBPF consumers attach hooks on the same node:

- Cilium agent — `tc`, `cgroup`, `socket` hooks (KPR socket-LB)
- (Optional) Stage 04 Pyroscope async-profiler — `perf_event` sampling
- Stage 05 OBI — uprobes (`SSL_read`, `accept4`, `connect`), kprobes,
  raw tracepoints

### 4a. NetworkPolicy

The OBI DaemonSet's egress must reach `otel-collector:4317`. Stage 01's
`networkpolicy.yaml` runs default-deny in `azure-otel`, so add the OBI
ServiceAccount / pod label to the collector's ingress rule:

```bash
# Inspect the labels Helm gave the OBI pods
kubectl -n azure-otel get pod -l app.kubernetes.io/name=beyla -o 'jsonpath={range .items[*]}{.metadata.labels}{"\n"}{end}'
```

Edit `01_deploy_to_aks/azure-otel/templates/networkpolicy.yaml` to add
the OBI label selector to the collector ingress, then `helm upgrade`.

### 4b. Cilium socket-LB and peer identity

Cilium KPR socket-LB rewrites the destination IP at `connect()` time.
Because OBI hooks the syscall, the peer it sees is the **real Pod IP**,
not the ClusterIP. `service.name` resolution depends entirely on the
Kubernetes metadata enricher — without §2's RBAC, peer service names
fall back to `unknown`.

### 4c. Overlap with Hubble L7 (when applicable)

This repo does not enable Advanced Container Networking Services
(ACNS), but if you turn it on later, Hubble L7 visibility overlaps with
OBI HTTP spans. Recommended split:

- Hubble = L4 flows + policy decisions + security audit
- OBI    = L7 application spans / RED metrics / traces
- Disable the `http` category in Hubble metrics
  (`hubble.metrics.enabled`, drop `httpV2` etc.)

### 4d. eBPF resource limits

All three components share verifier / JIT / `memlock` budgets. Inspect
a node:

```bash
kubectl debug node/<node> -it --image=ubuntu -- bash -c 'ulimit -l; sysctl bpf_jit_limit; bpftool prog show | wc -l'
```

If `memlock` is not `unlimited`, OBI / Pyroscope program loads will
fail with `Operation not permitted`. Stock AKS Ubuntu nodes are fine;
custom nodepools with `AKSCustomNodeConfig` need verification.

## 5. (Optional) Strengthen zero-code propagation

OBI reads the `traceparent` header on incoming requests, but
auto-injection on outbound calls only works on a few runtimes (Go,
some libc paths). To guarantee cross-service trace stitching across
Node / Python / Java, **stay on option A** and let the SDK handle
propagation.

If option B alone is mandatory:

```yaml
env:
  BEYLA_BPF_HTTP_REQUEST_TIMEOUT: "30s"
  # Experimental: force outbound HTTP/HTTPS context propagation
  BEYLA_BPF_TRACK_REQUEST_HEADERS: "true"
```

This setting is only stable on kernel 5.17+ and is known to flake on
some TLS libraries.

## 6. Coexistence with stage 04 (Pyroscope)

No conflict — the Pyroscope Java agent runs in-process
(`async-profiler`), while OBI runs in the node kernel; they hook
different surfaces. To get clean **Profile ↔ Trace ↔ Metric**
navigation in Grafana Drilldown, normalise on a single `service.name`:

- Stage 04 sets `PYROSCOPE_APPLICATION_NAME=spring`.
- Stage 02 / 03 dashboards use the `service=spring` label.
- OBI emits `k8s.deployment.name=azure-otel-spring`. Normalise it in
  the collector:

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

## Cleanup

```bash
helm -n azure-otel uninstall obi
kubectl -n azure-otel delete cm obi-config --ignore-not-found
# To return from option B back to 03:
kubectl apply -f ../03_otel_observability/manifests/instrumentation.yaml
kubectl -n azure-otel rollout restart deploy azure-otel-spring azure-otel-python azure-otel-nodejs
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| OBI pod `CrashLoopBackOff`, log says `failed to load BPF program: permission denied` | Missing capabilities. `BPF`, `PERFMON`, and `SYS_PTRACE` are required. On AzureLinux / Mariner nodes you may also need `privileged: true`. |
| Pod is up but zero spans / metrics | `discovery.services` did not match. Check `kubectl logs ds/obi | grep 'discovered service'`. Label selector / namespace typos are common. |
| Span `service.name` is an IP or `unknown` | RBAC missing — confirm the ClusterRole has get/list/watch on pods, services, replicasets. |
| Collector rejects OBI traffic | Stage 01 NetworkPolicy default-deny. Follow §4a to add the OBI selector to the ingress rule. |
| Each request shows up as two traces (SDK + OBI) | Option A-1 (`BEYLA_TRACES_ENABLED=false`) was not applied. Or the deployment-exclude regex from option A-2 is missing. |
| HTTPS spans missing | OBI cannot resolve OpenSSL / BoringSSL symbols. Common with musl-based (alpine) or statically-linked container images — switch the base image to distroless or Ubuntu. |
| Active-series cardinality explosion | OBI `service.name` × Hubble `destination_workload` × pod labels can blow up AMW active series. Disable Hubble L7 metrics per §4c. |
| Some pods miss instrumentation right after node boot | OBI DaemonSet starts after the workload pods. Add `priorityClassName: system-node-critical` and node tolerations. |
