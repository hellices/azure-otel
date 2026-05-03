# 02 — OTel auto-instrumentation + PodMonitor + Grafana dashboards

Builds on the AKS cluster from [01_deploy_to_aks](../01_deploy_to_aks):
inject auto-instrumentation via the **OpenTelemetry Operator**, scrape
`:9464/metrics` from each pod with a **PodMonitor** so ama-metrics ships
metrics into the **Azure Monitor Workspace (AMW)**, and visualize them with
three **Managed Grafana** dashboards (Node.js / Python / Spring).

> Korean version: [README_KR.md](./README_KR.md)

![Metrics flow](../docs/diagrams/metrics-via-podmonitor-flow.png)

```
[App pod]                                  ┌──► (App Insights — step 03)
 ├─ init: otel-auto-instrumentation        │
 │    └─ injects Java/Python/Node SDK      │
 └─ app container :9464/metrics  ──────────┴──► [ama-metrics]
                                                  │ remote-write
                                                  ▼
                                                [AMW]  ─►  [Managed Grafana]
                                                                │
                                                                ▼
                                            nodejs.json / python.json / spring.json
```

## What the chart already does (step 01)

When `otel.enabled=true` (the default), the Helm chart from step 01 already
provides everything needed for auto-injection, so step 02 only adds the
Operator + Instrumentation + PodMonitor:

- Each Deployment's pod template gets
  `instrumentation.opentelemetry.io/inject-{java|python|nodejs}` and
  `instrumentation.opentelemetry.io/container-names` annotations
- Each container exposes a named port `otel-metrics: 9464`
- Spring's NetworkPolicy permits `kube-system/ama-metrics → :9464` ingress
  (nodejs/python have no NP, so they default-allow)

That's why this stage has no `kubectl patch deploy ...` step.

## Steps

### 1. Install the OpenTelemetry Operator

The Operator's admission webhook needs TLS certs, so **cert-manager** is
required. Skip if it's already installed:

```powershell
# (A) cert-manager
kubectl get ns cert-manager 2>$null
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml
kubectl -n cert-manager rollout status deploy/cert-manager-webhook --timeout=180s

# (B) OpenTelemetry Operator
kubectl apply -f https://github.com/open-telemetry/opentelemetry-operator/releases/latest/download/opentelemetry-operator.yaml
kubectl -n opentelemetry-operator-system rollout status deploy/opentelemetry-operator --timeout=180s

kubectl -n opentelemetry-operator-system get pods
kubectl get crd | Select-String opentelemetry
```

### 2. Apply the Instrumentation CR

Declares the env vars each language SDK gets when injected as an init
container. Metrics are exposed via the **Prometheus exporter (`:9464/metrics`)**;
traces and logs stay off in this stage (step 03 switches them to OTLP).

```powershell
cd ./02_metrics_via_podmonitor    # from repo root
kubectl apply -f manifests/instrumentation.yaml
kubectl -n azure-otel get instrumentation
```

Once the CR exists, the Operator's webhook reads the chart's pre-set pod
annotations and injects an init container. Existing pods need a one-time
restart for the injection to take effect:

```powershell
kubectl -n azure-otel rollout restart deploy azure-otel-spring azure-otel-python azure-otel-nodejs
kubectl -n azure-otel rollout status   deploy azure-otel-spring --timeout=180s
kubectl -n azure-otel rollout status   deploy azure-otel-python --timeout=180s
kubectl -n azure-otel rollout status   deploy azure-otel-nodejs --timeout=180s

# Verify each pod has an opentelemetry-auto-instrumentation-{java|python|nodejs} init container
kubectl -n azure-otel get pods
```

### 3. Confirm the app exposes metrics on :9464

Repeat for each service:

```powershell
# Terminal 1
kubectl -n azure-otel port-forward deploy/azure-otel-spring 9464:9464

# Terminal 2
curl.exe -s http://localhost:9464/metrics | Select-String 'http_server' | Select-Object -First 5
```

You should see `http_server_request_duration_seconds_bucket`, `process_*`, and
for the JVM `jvm_memory_used_bytes` etc.

### 4. Apply the PodMonitor

```powershell
kubectl apply -f manifests/podmonitor.yaml
kubectl -n azure-otel get podmonitor.azmonitoring.coreos.com
```

> If the CRD was just installed, restart ama-metrics so it picks it up:
>
> ```powershell
> kubectl -n kube-system rollout restart deploy/ama-metrics
> ```

You can verify targets in step 5·B via Grafana Explore. To go deeper,
port-forward an ama-metrics pod to :9090 and query `/api/v1/targets` directly
(ama-metrics is sharded across two replicas so you may need to inspect both).

### 5. Confirm metrics arrive in AMW

#### A. Query the AMW Prometheus endpoint directly (most accurate)

```powershell
$amwUrl = (az monitor account show -g (azd env get-value AZURE_RESOURCE_GROUP) `
            -n (azd env get-value AZURE_MONITOR_WORKSPACE_NAME) `
            --query metrics.prometheusQueryEndpoint -o tsv)
$amwTok = (az account get-access-token --resource https://prometheus.monitor.azure.com `
            --query accessToken -o tsv)
curl.exe -sS -H "Authorization: Bearer $amwTok" `
  "$amwUrl/api/v1/query?query=count%20by%20(service)%20(up%7Bnamespace%3D%22azure-otel%22%7D)"
```

If `{"service":"nodejs"}`, `python`, and `spring` are returned, the pipeline
is healthy.

#### B. Verify the Managed Grafana → AMW path

Managed Grafana → Explore → datasource: **Managed_Prometheus_<amw-name>**

```promql
up{namespace="azure-otel"}
sum by (service) (rate(http_server_request_duration_seconds_count[5m]))
```

> If Grafana returns 401 / `Authentication to data source failed`, AMG's
> system-assigned MI is missing the `Monitoring Data Reader` role on AMW
> (or AAD propagation is still pending — usually a few minutes):
>
> ```powershell
> $mi    = az grafana show -n (azd env get-value GRAFANA_NAME) `
>            -g (azd env get-value AZURE_RESOURCE_GROUP) --query identity.principalId -o tsv
> $amwId = az monitor account show -n (azd env get-value AZURE_MONITOR_WORKSPACE_NAME) `
>            -g (azd env get-value AZURE_RESOURCE_GROUP) --query id -o tsv
> az role assignment create --assignee-object-id $mi `
>   --assignee-principal-type ServicePrincipal `
>   --role 'Monitoring Data Reader' --scope $amwId
> ```

### 6. Import the Grafana dashboards (Node / Python / Spring)

In the Managed Grafana console:

1. **Dashboards → New → Import**
2. Paste the contents of `dashboards/nodejs.json` → Load
3. Pick **Managed_Prometheus_<amw-name>** as the datasource
4. Repeat for `python.json` and `spring.json`

There are only three of them so the UI is easiest. To bulk-import via CLI:

<details><summary>CLI import (optional)</summary>

```powershell
$grafana = (azd env get-value GRAFANA_ENDPOINT)
# Azure Managed Grafana audience (fixed GUID)
$token   = az account get-access-token --resource ce34e7e5-485f-4d76-964f-b3d2b16d1e4f `
              --query accessToken -o tsv
$enc = New-Object Text.UTF8Encoding $false   # avoid PS5 BOM
foreach ($f in 'dashboards/nodejs.json','dashboards/python.json','dashboards/spring.json') {
  $dash = Get-Content $f -Raw | ConvertFrom-Json
  $dash | Add-Member -NotePropertyName id -NotePropertyValue $null -Force
  $body = @{ dashboard = $dash; overwrite = $true; folderId = 0 } | ConvertTo-Json -Depth 100
  [IO.File]::WriteAllText("$PWD\body.json", $body, $enc)
  curl.exe -sS -X POST "$grafana/api/dashboards/db" `
    -H "Authorization: Bearer $token" -H 'Content-Type: application/json' `
    --data-binary '@body.json'
  ''
}
Remove-Item body.json
```

</details>

## What the dashboards show

Each dashboard combines RED + runtime panels:

| Panel | PromQL gist |
|---|---|
| Request rate (req/s) | `sum(rate(http_server_request_duration_seconds_count[5m]))` |
| Error rate (5xx, %) | 5xx ratio |
| Latency p50/p95/p99 (ms) | `histogram_quantile` over `_bucket` |
| Throughput by route | `sum by (http_route) (rate(...))` |
| Runtime (per language) | Node: event loop / heap, Python: CPU / RSS, Java: JVM heap pool / GC pause / threads |

The `namespace` variable and `service=…` label are populated by the
PodMonitor's relabelings.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Pod has no init container | Instrumentation CR not applied (`kubectl -n azure-otel get instrumentation`) or Operator/cert-manager pods aren't Ready. After applying the CR you must restart pods once. |
| `up{service="spring"}=0` or `context deadline exceeded` | Spring's NetworkPolicy is dropping ama-metrics → :9464 traffic. Confirm `otel.scrapeNetworkPolicy=true` (default) in the step-01 values. |
| Spring metrics flap | JVM warmup can take 30s+. That's why the PodMonitor has `scrapeTimeout: 25s`. |
| `:9464` returns nothing | The SDK didn't start the Prometheus exporter or the port is in use. `kubectl logs <pod> -c spring \| grep -i prometheus` |
| No metrics in Grafana | ama-metrics may not have noticed the new PodMonitor CRD yet. `kubectl -n kube-system rollout restart deploy/ama-metrics` |
| `http_response_status_code` label is missing | Older OTel SDK versions emit `http_status_code` (or other names). Replace the label name in the panel PromQL with whatever the metric actually exposes. |

## Next

- **03**: Replace the `:9464` Prometheus exporter with an in-cluster
  **OTel Collector** that fans OTLP traces/metrics out to Application Insights
  (private via AMPLS) and AMW (scraped by ama-metrics) instead.
