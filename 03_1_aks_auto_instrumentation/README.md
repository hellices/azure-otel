# 03-1 — AKS Auto-Instrumentation → App Insights (no collector)

An alternative to [03_otel_observability](../03_otel_observability) that uses the
**AKS-native auto-instrumentation preview** instead of deploying a separate
OpenTelemetry Collector.

AKS injects the **Azure Monitor OpenTelemetry Distro** directly into application
pods. Telemetry is forwarded to **Application Insights** via the Azure Monitor
Agent (AMA) running on the cluster — no collector or operator installation required.

> Korean version: [README_KR.md](./README_KR.md)

```
app pod ─OTLP/HTTP─► AMA (Azure Monitor Agent) ─► Application Insights
                                                    └─► Live Metrics / App Map / Failures
```

## Comparison: step 03 vs 03-1

| Aspect | 03 (OTel Collector) | 03-1 (AKS auto-instr.) |
|---|---|---|
| Collector | Self-managed OTel Collector (2 replicas) | None — AMA handles OTLP |
| Operator | Upstream OTel Operator + cert-manager | AKS-managed (built-in webhook) |
| Python support | Full (OTLP/HTTP via operator) | Limited preview (private annotation) |
| Traces destination | `azuremonitor` exporter → App Insights | AMA → App Insights |
| Metrics destination | `prometheus` exporter → ama-metrics → AMW | App Insights (OTLP) |
| Step 02 dashboards | ✓ (via prom exporter on :8889) | Separate (App Insights metrics) |
| Health-check filter | `filter/drop_healthchecks` processor | Not built-in (configure via SDK) |
| Infrastructure overhead | Collector pods + operator pods | Zero (reuses existing AMA) |

## Prerequisites

- AKS cluster from [01_deploy_to_aks](../01_deploy_to_aks) (step 01 complete)
- Step 02 applied (or just the Helm chart deployed)
- Azure CLI ≥ 2.78.0 with `aks-preview` extension

## 0. Register preview features

> Registration can take a few minutes. Run this once per subscription.

```bash
# AKS auto-instrumentation
az feature register --namespace "Microsoft.ContainerService" --name "AzureMonitorAppMonitoringPreview"

# (Optional) OTLP ingestion for Application Insights
az feature register --namespace "Microsoft.Insights" --name "OtlpApplicationInsights"

# Wait for registration
az feature list -o table --query "[?contains(name, 'AzureMonitorAppMonitoringPreview')].{Name:name,State:properties.state}"

# Propagate
az provider register --namespace "Microsoft.ContainerService"
az provider register --namespace "Microsoft.Insights"
```

## 1. Clean up step 02 / 03

> All commands below assume you are inside `03_1_aks_auto_instrumentation/`.

Remove the OTel Operator's Instrumentation CR and any step 03 collector.
The PodMonitor from step 02 is not removed because it continues to work
independently for Prometheus metrics if desired.

```bash
cd 03_1_aks_auto_instrumentation    # from repo root

# Delete step 02/03 Instrumentation CR (OTel Operator)
kubectl -n azure-otel delete instrumentation.opentelemetry.io azure-otel --ignore-not-found

# Delete step 03 Collector (if applied)
kubectl -n azure-otel delete opentelemetrycollector otel --ignore-not-found
kubectl -n azure-otel delete secret otel-collector-secrets --ignore-not-found
```

## 2. Enable AKS auto-instrumentation on the cluster

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
RG=$(azd env get-value AZURE_RESOURCE_GROUP --cwd ../01_deploy_to_aks)
AKS=$(azd env get-value AKS_NAME --cwd ../01_deploy_to_aks)

az aks update \
  --resource-group "$RG" \
  --name "$AKS" \
  --enable-azure-monitor-app-monitoring
```

</details>

<details open>
<summary><strong>Windows (PowerShell)</strong></summary>

```powershell
$RG = azd env get-value AZURE_RESOURCE_GROUP --cwd ../01_deploy_to_aks
$AKS = azd env get-value AKS_NAME --cwd ../01_deploy_to_aks

az aks update `
  --resource-group $RG `
  --name $AKS `
  --enable-azure-monitor-app-monitoring
```

</details>

This installs the AKS auto-instrumentation webhook. Verify:

```bash
kubectl get crd instrumentations.monitor.azure.com
```

## 3. Create the AKS Instrumentation CR

The CR tells AKS which Application Insights resource to send telemetry to and
which languages to auto-instrument.

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
CONN_STR=$(azd env get-value APPLICATION_INSIGHTS_CONNECTION_STRING --cwd ../01_deploy_to_aks)

# Substitute the connection string into the manifest and apply
sed "s|\${APPLICATION_INSIGHTS_CONNECTION_STRING}|${CONN_STR}|" \
  manifests/instrumentation.yaml | kubectl apply -f -

kubectl -n azure-otel get instrumentation.monitor.azure.com
```

</details>

<details open>
<summary><strong>Windows (PowerShell)</strong></summary>

```powershell
$CONN_STR = azd env get-value APPLICATION_INSIGHTS_CONNECTION_STRING --cwd ../01_deploy_to_aks

(Get-Content manifests/instrumentation.yaml) `
  -replace '\$\{APPLICATION_INSIGHTS_CONNECTION_STRING\}', $CONN_STR | `
  kubectl apply -f -

kubectl -n azure-otel get instrumentation.monitor.azure.com
```

</details>

## 4. Patch the Python deployment (limited preview)

Python auto-instrumentation is in limited preview and requires a
private-preview annotation instead of the standard `inject-python`.

```bash
kubectl patch deploy azure-otel-python -n azure-otel \
  --type merge --patch-file manifests/python-patch.yaml
```

> If you do **not** have access to the Python limited preview, skip this step.
> The Python app will run without auto-instrumentation but still serves traffic
> normally.

## 5. Restart deployments

```bash
kubectl -n azure-otel rollout restart deploy \
  azure-otel-spring azure-otel-python azure-otel-nodejs

kubectl -n azure-otel rollout status deploy/azure-otel-spring  --timeout=180s
kubectl -n azure-otel rollout status deploy/azure-otel-python  --timeout=180s
kubectl -n azure-otel rollout status deploy/azure-otel-nodejs  --timeout=180s
```

## 6. Verify

### A. Check init containers

```bash
kubectl -n azure-otel get pods \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .spec.initContainers[*]}{.name}{", "}{end}{"\n"}{end}'
```

Java and Node.js pods should have an Azure Monitor init container.

### B. Check App Insights telemetry

Generate some traffic, wait 2–3 minutes, then open the Application Insights
resource in the Azure portal:

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
# Generate traffic via the AppGW / AGFC endpoint
AGFC=$(azd env get-value APPGW_PUBLIC_IP --cwd ../01_deploy_to_aks 2>/dev/null || \
       kubectl get gateway azure-otel-gateway -n azure-otel \
         -o jsonpath='{.status.addresses[0].value}' 2>/dev/null)

for i in $(seq 1 20); do curl -s "http://${AGFC}/api/items" > /dev/null; done

echo "Check traces in: https://portal.azure.com → Application Insights → Transaction search"
```

</details>

<details open>
<summary><strong>Windows (PowerShell)</strong></summary>

```powershell
$AGFC = azd env get-value APPGW_PUBLIC_IP --cwd ../01_deploy_to_aks 2>$null
if (-not $AGFC) {
  $AGFC = kubectl get gateway azure-otel-gateway -n azure-otel `
    -o jsonpath='{.status.addresses[0].value}' 2>$null
}

1..20 | ForEach-Object { Invoke-WebRequest -Uri "http://$AGFC/api/items" -UseBasicParsing | Out-Null }

Write-Host "Check traces in: https://portal.azure.com → Application Insights → Transaction search"
```

</details>

### C. Application Map

Open **Application Insights → Application Map** to see the distributed
dependency graph across `nodejs → python → spring`.

## Limitations (preview)

- **Windows node pools**: Not supported.
- **Python / .NET**: Limited preview (private-preview annotations).
- **OTLP format**: Only OTLP/HTTP with binary Protobuf. No JSON payloads or
  OTLP/gRPC.
- **Compression**: Not supported in SDK exporters.
- **Istio mTLS**: Not supported.
- **Private Link**: Not validated.
- Max 30 DCR associations per AKS cluster.

## References

- [Monitor AKS applications with OTLP (Preview)](https://learn.microsoft.com/azure/azure-monitor/containers/kubernetes-open-protocol)
- [Autoinstrument AKS apps with Azure Monitor](https://learn.microsoft.com/azure/azure-monitor/containers/kubernetes-codeless)
- [Python / .NET limited preview](https://learn.microsoft.com/azure/azure-monitor/containers/kubernetes-codeless-python-net)
