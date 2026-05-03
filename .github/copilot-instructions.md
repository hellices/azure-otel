# azure-otel — Copilot repo instructions

This repo demonstrates running observability for apps on **AKS** with **Azure Managed Prometheus**, **OpenTelemetry**, and **Grafana**-style dashboards.

## Repository layout

- `01_deploy_to_aks/` — Bicep + Helm chart that provisions AKS, AGFC ingress, AMW/AMG, and deploys the sample apps.
- `02_metrics_via_podmonitor/` — `PodMonitor`, AMA scrape config, OTel `Instrumentation` CR, and Grafana dashboard JSON for the sample apps.
- `03_otel_observability/` — OTel Collector + Instrumentation CR; SDKs use OTLP only, collector splits traces → App Insights and metrics → ama-metrics.
- `04_profiling_with_pyroscope/` — Grafana Pyroscope + Java agent injected as an extra `-javaagent` into the Spring pod via a strategic-merge patch; no app code or image change.
- `base_apps/` — sample apps in Node.js (Next.js), Python (FastAPI), and Java (Spring Boot) that expose `/metrics` and accept OTel auto-instrumentation.
- `docs/diagrams/` — Excalidraw architecture diagrams.

## Domain knowledge (auto-loaded by `applyTo`)

Detailed guidance lives in `.github/instructions/` and is auto-attached when working on matching files:

| Domain | File pattern triggers |
|---|---|
| OpenTelemetry (SDK / OTLP / Alloy / Operator) | `base_apps/**`, `**/instrumentation.yaml`, `**/values.yaml`, `**/Dockerfile` |
| Prometheus (scraping / Mimir / AMW) | `**/podmonitor.yaml`, `**/ama-metrics-prometheus-config.toml`, `02_metrics_via_podmonitor/**` |
| PromQL (query patterns / recording rules / cardinality) | `**/dashboards/**/*.json`, `**/podmonitor.yaml`, `**/recording*.yaml` |
| Grafana dashboarding (panels / variables / transformations) | `**/dashboards/**/*.json` |

When the task fits one of these domains, follow the rules in the matching `.github/instructions/*.instructions.md` file even if it is not auto-attached.

## Conventions

- All app workloads live in the `azure-otel` namespace.
- Sample apps must keep exposing Prometheus metrics on the same port/path that `02_metrics_via_podmonitor/manifests/podmonitor.yaml` scrapes.
- Dashboards are committed as JSON under `02_metrics_via_podmonitor/dashboards/` and imported into Azure Managed Grafana.
- Prefer editing existing Helm values / manifests over introducing new ones.
- PowerShell is the default shell on Windows; chain commands with `;`, never `&&`.
