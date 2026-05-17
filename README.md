# azure-otel

A reference repo for **monitoring AKS-hosted applications with Azure Monitor +
OpenTelemetry**. The goal is to experiment with and codify a standard pattern
for end-to-end observability on Azure.

The work is split into numbered stages, each building on the previous one:

1. **Provision AKS + monitoring infra** (Bicep + azd)
2. **Metrics first** — SDK Prometheus exporter + AKS managed Prometheus + Grafana
3. **Standardize on OTLP** — OpenTelemetry Collector sending traces to
   Application Insights and metrics to AMW (scraped by ama-metrics), with all
   ingest paths going through AMPLS Private Endpoints.
3-1. **AKS Auto-Instrumentation (Preview)** — alternative to stage 3 using
   the AKS-native `monitor.azure.com/v1` Instrumentation CR, no Collector
   required. Telemetry goes directly to Application Insights.
4. **Continuous profiling (Java)** — Grafana Pyroscope + Pyroscope Java
   agent injected as a sidecar `-javaagent` into the Spring pod, no app
   change.

A Korean version of every README is kept alongside as `README_KR.md`.

## Sample workload (`base_apps/`)

A deliberately polyglot 3-tier app is used to validate the pattern across SDKs.

| Service | Stack | Role | Port |
|---|---|---|---|
| `nodejs` | Next.js (TypeScript) | SPA shell | 3000 |
| `python` | FastAPI | Edge / proxy | 8000 |
| `spring` | Spring Boot (Java) | CRUD + SQLite | 8080 |

Call flow: `browser → nodejs → python → spring`. All services are built as
containers compatible with OpenTelemetry auto-instrumentation.

![base_apps architecture](./docs/diagrams/base-apps-architecture.png)

## Stages

### [`01_deploy_to_aks/`](./01_deploy_to_aks)
Provisions AKS, ACR, Log Analytics, Application Insights, Azure Monitor
Workspace, Managed Grafana, AGFC (Gateway API), and **AMPLS + Private Endpoint
with the 5 required Private DNS Zones** in a single `azd up`. Then deploys the
sample apps with Helm.

### [`02_metrics_via_podmonitor/`](./02_metrics_via_podmonitor)
Installs the OpenTelemetry Operator and an Instrumentation CR so the SDK
exposes `:9464/metrics`, then has ama-metrics scrape it via a `PodMonitor`.
The fastest path to "RED metrics in Grafana".

### [`03_otel_observability/`](./03_otel_observability)
Switches the SDK to OTLP/gRPC only. An in-cluster OTel Collector splits the
signal:
- **traces** → `azuremonitor` exporter → Application Insights (private via AMPLS)
- **metrics** → `prometheus` exporter → ama-metrics scrape → AMW → Grafana

Stage 02 dashboards keep working — the collector's `transform` processor maps
OTel resource attributes back to the Prometheus labels the dashboards expect.

### [`03_1_aks_auto_instrumentation/`](./03_1_aks_auto_instrumentation)
An **alternative** to stage 03 that uses the AKS-native auto-instrumentation
preview (`AzureMonitorAppMonitoringPreview`). The AKS-managed `monitor.azure.com/v1`
Instrumentation CR injects the Azure Monitor distro directly — no OTel Collector
needed. Traces, requests, and dependencies go straight to Application Insights.
Ideal when App Insights is the sole observability backend; stage 02 PromQL
dashboards will not receive data (use App Insights built-in blades instead).

### [`04_profiling_with_pyroscope/`](./04_profiling_with_pyroscope)
Adds the third OTel signal — **profiling** — for the Spring service only.
A strategic-merge patch on the Spring Deployment adds an initContainer that
downloads the official Pyroscope Java agent and an extra `-javaagent`
entry, so the JVM loads OTel + Pyroscope side-by-side. Same `service`
label as step-02/03 dashboards. Python and Node need a process bootstrap
that would touch app code, so they are intentionally out of scope here.
OTel's native profiles signal is still in Development as of 2026-05.

> **(Optional) Browser RUM** — OTel auto-instrumentation only covers the server
> side. To capture page loads / Web Vitals / client-side fetch / JS errors as
> well, plug in the
> [Grafana Faro Web SDK](https://grafana.com/docs/grafana-cloud/monitor-applications/frontend-observability/)
> and ship to the collector (Alloy `faro.receiver`). Faro's tracer is built on
> OTel Web, so `traceparent` flows through to the backend spans end-to-end.

> **(Optional) Stage 05 — eBPF auto-instrumentation with OTel OBI** — see
> [`05_ebpf_with_obi/`](./05_ebpf_with_obi). Runs OpenTelemetry OBI
> (formerly Grafana Beyla) as a DaemonSet so HTTP / gRPC / SQL spans and
> RED metrics are captured from the kernel without any app, image, or SDK
> change. The README covers two layouts (additive on top of stage 03, or
> replacing the SDK injection entirely) and how to coexist with the
> Cilium dataplane and the stage-04 Pyroscope agent on the same nodes.

### [`06_hubble_network_observability/`](./06_hubble_network_observability)
Enables **Cilium Hubble** via Azure Advanced Container Networking Services
(ACNS). Since stage 01 already deploys Cilium as the data plane, a single
`az aks update --enable-acns` unlocks L3/L4/L7 flow visibility, DNS
monitoring, and packet-drop analysis. Hubble metrics are auto-scraped by
ama-metrics — no PodMonitor needed.

### [`07_opencost/`](./07_opencost)
**OpenCost** (CNCF Graduated) for per-pod / per-namespace cost allocation.
Combines Kubernetes resource usage with Azure billing data. Includes a
lightweight in-cluster Prometheus, OpenCost UI, and a Grafana dashboard.

### [`08_slo_monitoring/`](./08_slo_monitoring)
Defines **Service Level Objectives** using [Sloth](https://sloth.dev/) on
top of the RED metrics from stage 02. Generates multi-window multi-burn-rate
recording rules and alerts following the Google SRE workbook pattern.
Answers "are we on track for 99.9% this month?" instead of just "what is
the current error rate?"

## Architecture

```
                                ┌──────────────── private VNet ───────────────┐
                                │                                              │
[Internet] ─► AGFC ─► AKS ─► app pod (OTel SDK, OTLP/gRPC)                     │
                             │                                                 │
                             ▼                                                 │
                      otel-collector ─┬─► Application Insights (via AMPLS PE)  │
                                      │                                        │
                                      └─► :8889 ◄─ ama-metrics ─► AMW ─► Grafana
                                │                                              │
                                └──────────────────────────────────────────────┘
```

See [`docs/diagrams/`](./docs/diagrams) for Excalidraw versions.

## Quick start

```powershell
# 1. Infra + Helm release
cd 01_deploy_to_aks
azd up
# (run the Helm install command from the stage README)

# 2. Metrics pipeline
kubectl apply -f ..\02_metrics_via_podmonitor\manifests\

# 3. Switch to OTLP via the Collector
cd ..\
# Tear down stage 02 outputs and follow 03_otel_observability/README.md

# 3-1. (Alternative) AKS-native auto-instrumentation
# Follow 03_1_aks_auto_instrumentation/README.md instead of step 3

# 4. Continuous profiling (Pyroscope + Alloy eBPF)
# Follow 04_profiling_with_pyroscope/README.md
```

Each stage README has the exact commands and verification steps.

## Tech used

- **Compute / network**: AKS (Azure CNI overlay + Cilium), AGFC (Gateway API), VNet, Private Endpoint
- **Observability**: OpenTelemetry SDK / Operator / Collector, Application Insights, Azure Monitor Workspace (managed Prometheus), Azure Managed Grafana, AMPLS, Grafana Pyroscope (Java agent), Cilium Hubble (ACNS), OpenCost, Sloth (SLO)
- **Build / deploy**: Bicep, Azure Developer CLI (azd), Helm, GitHub Container Registry
