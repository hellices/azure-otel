---
applyTo: "base_apps/**,**/instrumentation.yaml,**/values.yaml,**/Dockerfile,01_deploy_to_aks/**,02_metrics_via_podmonitor/**"
description: "OpenTelemetry SDK instrumentation, OTLP endpoints, Alloy/OTel Collector, and Kubernetes OTel Operator with the Grafana stack."
---

# OpenTelemetry with Grafana

## Overview

OpenTelemetry (OTel) is a vendor-neutral framework for collecting observability data (metrics, logs,
traces, profiles). Grafana Labs integrates it as a core strategy, offering a full stack to collect,
ingest, store, analyze, and visualize telemetry data.

### Four-Step Implementation Model

1. **Instrument** - Add telemetry using Grafana SDKs, Beyla (eBPF), or upstream OTel SDKs
2. **Pipeline** - Build processing infrastructure with Grafana Alloy or OTel Collector
3. **Ingest** - Route data to Grafana Cloud OTLP endpoint or self-managed backends
4. **Analyze** - Dashboards, alerts, Application Observability, Drilldown apps

### Grafana Backends

| Signal | Backend |
|--------|---------|
| Metrics | Grafana Mimir |
| Logs | Grafana Loki |
| Traces | Grafana Tempo |
| Profiles | Grafana Pyroscope |

---

## OTLP Endpoint and Authentication

### Grafana Cloud OTLP Endpoint

```
https://otlp-gateway-<region>.grafana.net/otlp
```

Example: `https://otlp-gateway-prod-us-east-0.grafana.net/otlp`

### Authentication - Basic Auth

- **Username**: Grafana Cloud Instance ID (numeric)
- **Password**: Grafana Cloud API token (MetricsPublisher / LogsPublisher / TracesPublisher)

```bash
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic $(echo -n '123456:glc_eyJ...' | base64)"
```

### Direct Send (no collector) - Environment Variables

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-prod-us-east-0.grafana.net/otlp
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <base64(instanceID:apiToken)>"
export OTEL_RESOURCE_ATTRIBUTES="service.name=myapp,service.namespace=myteam,deployment.environment=production"
```

---

## Instrumentation by Language

### Go (1.22+)

```bash
go get "go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp" \
  "go.opentelemetry.io/otel" \
  "go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetrichttp" \
  "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp" \
  "go.opentelemetry.io/otel/sdk" \
  "go.opentelemetry.io/otel/sdk/metric"
```

### Java (Grafana JVM Agent, JDK 8+)

```bash
OTEL_RESOURCE_ATTRIBUTES="service.name=shoppingcart,service.namespace=ecommerce,deployment.environment=production" \
OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-prod-us-east-0.grafana.net/otlp \
OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf" \
OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <base64>" \
java -javaagent:/path/to/grafana-opentelemetry-java.jar -jar myapp.jar
```

Debug:
```bash
export OTEL_JAVAAGENT_DEBUG=true
export OTEL_TRACES_EXPORTER=otlp,console
```

### Node.js

```bash
npm install --save @opentelemetry/api @opentelemetry/auto-instrumentations-node
```

```bash
OTEL_TRACES_EXPORTER="otlp" \
OTEL_METRICS_EXPORTER="otlp" \
OTEL_LOGS_EXPORTER="otlp" \
OTEL_NODE_RESOURCE_DETECTORS="env,host,os" \
OTEL_RESOURCE_ATTRIBUTES="service.name=myapp,deployment.environment=prod" \
OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-prod-us-east-0.grafana.net/otlp \
OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <base64>" \
NODE_OPTIONS="--require @opentelemetry/auto-instrumentations-node/register" \
node app.js
```

**Warning:** Bundlers like `@vercel/ncc` can break auto-instrumentation hooks.

### Python

```bash
pip install "opentelemetry-distro[otlp]"
opentelemetry-bootstrap -a install
opentelemetry-instrument python app.py
```

Multi-process servers (Gunicorn, uWSGI): reinitialize OTel providers in post-fork hooks.

### .NET (6+)

```bash
dotnet add package Grafana.OpenTelemetry
```

```csharp
using Grafana.OpenTelemetry;
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddOpenTelemetry()
    .WithTracing(c => c.UseGrafana())
    .WithMetrics(c => c.UseGrafana());
builder.Logging.AddOpenTelemetry(o => o.UseGrafana());
```

### Beyla (eBPF, language-agnostic)

```bash
docker run --rm -it --privileged \
  -e BEYLA_SERVICE_NAME=myapp \
  -e OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 \
  -v /sys/kernel/security:/sys/kernel/security \
  grafana/beyla
```

---

## Grafana Alloy Collector

| Port | Protocol | Purpose |
|------|----------|---------|
| 4317 | gRPC | OTLP gRPC receiver |
| 4318 | HTTP | OTLP HTTP/protobuf receiver |

Use a collector for cost control (sampling, drops), reliability (buffering), and enrichment (resource attributes, redaction).

---

## Kubernetes Setup

### Option 1: Grafana Kubernetes Monitoring Helm chart (recommended)

Enable "OTLP Receivers" in the Cluster Configuration tab, then point apps to the in-cluster Alloy endpoint.

### Option 2: OpenTelemetry Operator

```yaml
apiVersion: opentelemetry.io/v1alpha1
kind: Instrumentation
metadata:
  name: my-instrumentation
spec:
  exporter:
    endpoint: http://otelcol:4317
  propagators: [tracecontext, baggage]
  java:
    image: us-docker.pkg.dev/grafanalabs-global/docker-grafana-opentelemetry-java-prod/grafana-opentelemetry-java:2.3.0-beta.1
  nodejs: {}
  python: {}
```

Inject via pod annotation:
```yaml
metadata:
  annotations:
    instrumentation.opentelemetry.io/inject-java: "true"
    # or: inject-nodejs, inject-python, inject-dotnet
```

---

## Sampling

### Head-based (probability)

```bash
export OTEL_TRACES_SAMPLER=parentbased_traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.1   # 10% of traces
```

### Tail-based (Alloy)

```alloy
otelcol.processor.tail_sampling "default" {
  decision_wait = "10s"
  policy {
    name = "keep-errors"
    type = "status_code"
    status_code { status_codes = ["ERROR"] }
  }
  policy {
    name = "probabilistic-sample"
    type = "probabilistic"
    probabilistic { sampling_percentage = 10 }
  }
  output { traces = [otelcol.exporter.otlphttp.grafana_cloud.input] }
}
```

---

## Key environment variables

| Variable | Example |
|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `https://otlp-gateway-prod-us-east-0.grafana.net/otlp` |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc` or `http/protobuf` |
| `OTEL_EXPORTER_OTLP_HEADERS` | `Authorization=Basic <base64>` |
| `OTEL_RESOURCE_ATTRIBUTES` | `service.name=myapp,service.namespace=team,deployment.environment=prod` |
| `OTEL_SERVICE_NAME` | `myapp` |
| `OTEL_TRACES_SAMPLER` / `_ARG` | `parentbased_traceidratio` / `0.1` |

### Key resource attributes

| Attribute | Purpose |
|---|---|
| `service.name` | Service identifier |
| `service.namespace` | Groups related services |
| `deployment.environment` | `production`, `staging` |
| `service.version` | App version |

---

## References

Further detail (full SDK code samples, Alloy/Collector YAML) lives in:
- [.agents/skills/opentelemetry/references/instrumentation.md](../../.agents/skills/opentelemetry/references/instrumentation.md)
- [.agents/skills/opentelemetry/references/collector-config.md](../../.agents/skills/opentelemetry/references/collector-config.md)
- Grafana OTel docs: https://grafana.com/docs/opentelemetry/
- Grafana Alloy: https://grafana.com/docs/alloy/
- OTel Operator: https://opentelemetry.io/docs/kubernetes/operator/
