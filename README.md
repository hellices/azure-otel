# azure-otel

A reference repo for **monitoring AKS-hosted applications with Azure Monitor +
OpenTelemetry**. The goal is to experiment with and codify a standard pattern
for end-to-end observability on Azure.

The work is split into three numbered stages, each building on the previous one:

1. **Provision AKS + monitoring infra** (Bicep + azd)
2. **Metrics first** — SDK Prometheus exporter + AKS managed Prometheus + Grafana
3. **Standardize on OTLP** — OpenTelemetry Collector sending traces to
   Application Insights and metrics to AMW (scraped by ama-metrics), with all
   ingest paths going through AMPLS Private Endpoints.

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
```

Each stage README has the exact commands and verification steps.

## Tech used

- **Compute / network**: AKS (Azure CNI overlay + Cilium), AGFC (Gateway API), VNet, Private Endpoint
- **Observability**: OpenTelemetry SDK / Operator / Collector, Application Insights, Azure Monitor Workspace (managed Prometheus), Azure Managed Grafana, AMPLS
- **Build / deploy**: Bicep, Azure Developer CLI (azd), Helm, GitHub Container Registry
