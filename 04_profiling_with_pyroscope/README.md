# 04 — Java continuous profiling with the Pyroscope SDK (no app changes)

Stages 01–03 give us metrics + traces. This stage adds the **profiling**
signal **for the Spring Boot service only**, using the official
[Pyroscope Java agent](https://github.com/grafana/pyroscope-java) injected
as a sidecar `-javaagent` — the application image and source code are
untouched.

> Korean version: [README_KR.md](./README_KR.md)

![Pyroscope flow](../docs/diagrams/pyroscope-java-flow.png)

OpenTelemetry's profiling signal is still **Development** as of 2026-05
(OTLP `profiles` data model exists, SDK + spec are not GA). Pyroscope's
own SDK is the practical interim path. Among the three sample languages,
**Java is the only one that supports a fully no-code injection** via
`-javaagent`:

| Service | Native SDK injection without code change? |
|---|---|
| Spring (Java) | ✅ `-javaagent` + env vars (this stage) |
| FastAPI (Python) | ❌ requires `pyroscope.configure(...)` at startup |
| Next.js (Node) | ⚠️ requires `--require` bootstrap script |

Python and Node are intentionally left out for now — their SDKs need a
process-level bootstrap that this repo's "no app changes" rule doesn't
allow. They can be added later with eBPF (Grafana Alloy `pyroscope.ebpf`)
or with `pyroscope-otel` bridges.

```
spring pod (OTel javaagent + Pyroscope javaagent)
    │
    └─ HTTP push ─► pyroscope (in-cluster) ─► UI :4040
                        │                     │
                        │                     └─ (optional) AGFC HTTPRoute
                        │                        ─► AMG datasource
                        └─ profile blocks ─► Azure Blob Storage
                           (federated auth via AKS Workload Identity)
```

| Component | Purpose |
|---|---|
| `pyroscope` (Helm, single binary) | Profiles ingest + UI on `:4040`; blocks persisted to **Azure Blob Storage** |
| Azure Blob container `pyroscope` | Durable profile store (`storage.backend: azure`) — survives pod/node loss, no PVC |
| User-assigned identity + federated credential | Keyless auth: the `pyroscope` ServiceAccount exchanges its token for Entra ID (`Storage Blob Data Contributor`) |
| `spring-pyroscope-patch.yaml` | initContainer downloads `pyroscope.jar`; env vars wire it to the JVM and Pyroscope server |
| (optional) `HTTPRoute` (AGFC-only) | Exposes Pyroscope behind the gateway when AGFC is enabled |

Storing blocks in Blob instead of a PVC follows the pattern from
[Continuous profiling on AKS with Pyroscope, Blob Storage and Managed Grafana](https://azureglobalblackbelts.com/2026/05/06/continuous-profiling-on-AKS-with-pyroscope-blob-storage-and-managed-grafana/)
(Azure Global Black Belts) — adapted here to single-binary mode, which is
plenty for a 3-service demo. The blog's microservices layout is the scale-up
path.

The patch sets `PYROSCOPE_APPLICATION_NAME=spring` so the Pyroscope label
`service_name` matches the `service=spring` label used by the step-02/03
dashboards — metrics ↔ flame graph correlation comes for free.

## Prerequisites

- Stages 01–03 are running (`azure-otel` namespace, sample apps, OTel
  Collector). The Spring deployment must be `azure-otel-spring`.
- AKS pods can reach `github.com` for the agent download (default egress
  is open). If outbound is locked down, mirror `pyroscope.jar` to ACR and
  edit the initContainer image / URL.
- Permission to create a storage account / user-assigned identity and to
  grant `Storage Blob Data Contributor` on it. The stage-01 cluster already
  ships with `--enable-oidc-issuer` + `--enable-workload-identity`
  (`01_deploy_to_aks/infra/resources.bicep`), so no cluster change is needed.

## Recommended Execution Flow (Updated)

Use this sequence as the default workflow.

1. Complete stages 01–03 and verify health first.
2. Create a dedicated resource group for stage-04 validation.
3. Apply stage 04 while checking ingestion and access continuously.

Example validation resource group:

```bash
az group create -n rg-otel-04-check -l koreacentral
```

Quick sanity checks for stages 01–03:

```bash
kubectl -n azure-otel get deploy,pod,svc
kubectl -n azure-otel get instrumentation
kubectl -n azure-otel get podmonitor.azmonitoring.coreos.com
```

## 1. Create the Azure Blob storage backend

Pyroscope persists profile **blocks** to object storage. Azure Blob is the
native option (`storage.backend: azure`) — durable, cheap, and keyless when
combined with AKS Workload Identity. No PVC is created.

> All commands below assume you are inside `04_profiling_with_pyroscope/`.

```bash
cd 04_profiling_with_pyroscope    # from repo root

rg=$(azd env get-value AZURE_RESOURCE_GROUP --cwd ../01_deploy_to_aks)
loc=$(az group show -n "$rg" --query location -o tsv)
aks=$(az aks list -g "$rg" --query '[0].name' -o tsv)
sa="stpyro$RANDOM$RANDOM"          # storage account names must be globally unique
echo "$sa" > .storage-account      # keep it around for later steps / cleanup

# 1a. Storage account — shared-key auth disabled, RBAC only
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

# 1c. Federated credential for the chart-created `pyroscope` ServiceAccount
oidc=$(az aks show -n "$aks" -g "$rg" --query oidcIssuerProfile.issuerUrl -o tsv)
az identity federated-credential create --name pyroscope-federated \
  --identity-name id-pyroscope -g "$rg" \
  --issuer "$oidc" \
  --subject "system:serviceaccount:azure-otel:pyroscope" \
  --audiences api://AzureADTokenExchange
```

No `az storage container create` needed — Pyroscope creates the `pyroscope`
container on first start (the identity has Contributor on the data plane).

> **Why Storage Blob Data Contributor?** Pyroscope reads *and* writes blocks
> (segments, compacted blocks, tenant indices). Reader alone breaks the
> compactor.

## 2. Install Pyroscope

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

Keep the chart `--version` pinned: chart 2.x renders CLI flags that the 1.x
image doesn't know (`flag provided but not defined`), and never hardcode
`pyroscope.image.tag` — the chart's own `appVersion` image is the one that
matches its flags.

Verify the blob backend is healthy (federated token exchanged, bucket
reachable):

```bash
kubectl -n azure-otel logs pyroscope-0 | grep -i "bucket health check"
# Expected: msg="bucket health check succeeded"
kubectl -n azure-otel exec pyroscope-0 -- env | grep ^AZURE_
# Expected: AZURE_CLIENT_ID / AZURE_TENANT_ID / AZURE_FEDERATED_TOKEN_FILE
```

`manifests/pyroscope-values.yaml` has `api.base-url: /pyroscope` **commented out** by
default. Uncomment it only when exposing Pyroscope behind a reverse proxy at
the `/pyroscope` path (e.g. AGFC HTTPRoute). When using `port-forward` directly,
leaving it enabled causes blank UI (asset paths mismatch).

## 3. Inject the Pyroscope Java agent into the Spring deployment

```bash
kubectl -n azure-otel patch deploy azure-otel-spring \
  --patch-file manifests/spring-pyroscope-patch.yaml
kubectl -n azure-otel rollout status deploy/azure-otel-spring --timeout=180s
```

Verify both javaagents loaded:

```bash
kubectl -n azure-otel logs deploy/azure-otel-spring --tail=20 | grep -iE 'pyroscope|javaagent|otel'
kubectl -n azure-otel exec deploy/azure-otel-spring -- printenv JAVA_TOOL_OPTIONS
# Expected:
#   -javaagent:/pyroscope/pyroscope.jar -javaagent:/otel-auto-instrumentation-java/javaagent.jar
```

The OTel Operator's mutating webhook **preserves** `JAVA_TOOL_OPTIONS`
when it injects its own auto-instrumentation, so both agents end up loaded
without conflicts.

## 4. Verify ingestion

Generate some CPU work:

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

Open the Pyroscope UI:

```bash
kubectl -n azure-otel port-forward svc/pyroscope 4040:4040
# browse http://localhost:4040
```

In the UI:

1. **Explore profiles** → `service_name = spring` should appear.
2. Profile types available (because `PYROSCOPE_FORMAT=jfr`):
   - `process_cpu / cpu (nanoseconds)` — on-CPU sampler (`itimer`)
   - `memory / alloc_in_new_tlab_bytes` — allocations
   - `mutex / lock_count` — contended locks
3. Flame graph should show `org.springframework.web.servlet.*`,
   `org.apache.tomcat.*`, your `ItemController.list`, the SQLite JDBC
   driver, etc.

And confirm blocks are landing in Blob Storage (flushed every ~15 s under
load, plus on shutdown):

```bash
kubectl -n azure-otel logs pyroscope-0 --tail=500 | grep "uploading blob"
# Expected lines like:
#   msg="uploading blob" blob=segments/1/anonymous/<ULID>/block.bin
#   msg="uploading blob" blob=blocks/1/anonymous/<ULID>/block.bin
```

Because history now lives in Blob, `kubectl delete pod pyroscope-0` no longer
loses profiles — after the restart the same flame graphs are still queryable.

## 5. (Optional) Expose Pyroscope to Azure Managed Grafana

If your current deployment mode is **AppGW** (the repo default), the
`HTTPRoute` method below does not apply.
`manifests/httproute.yaml` is **AGFC-only**. In AppGW mode, validate first via
`kubectl port-forward svc/pyroscope 4040:4040`, then add a dedicated AppGW
backend pool/path rule if you need external access.

### 5a. Route the gateway (AGFC-only)

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

### 5b. Register the datasource in AMG

The `grafana-pyroscope-datasource` is a **core** plugin in AMG Standard
(Grafana 12) — no plugin install / `grafanaPlugins` ARM property needed,
just create the datasource via the Grafana HTTP API:

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
# Expect: status = OK, message = "Data source is working"
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

Or the same thing through the UI: Grafana → **Connections → Add new data
source → Pyroscope** → URL `http://<ALB>/pyroscope`.

Pyroscope OSS has no built-in auth — for anything beyond a demo, prefer
[AMG Managed Private Endpoint](https://learn.microsoft.com/azure/managed-grafana/how-to-connect-to-data-source-privately)
or put an OAuth proxy in front.

## 6. (Optional, requires app rebuild) Span Profiles

Per-span flame graphs need the
[`pyroscope-otel`](https://github.com/grafana/otel-profiling-java)
javaagent extension loaded alongside the OTel agent
(`OTEL_JAVAAGENT_EXTENSIONS=/path/to/pyroscope-otel.jar`). That requires
extending the step-03 `Instrumentation` CR (`spec.java.extensions`) so the
operator copies the JAR into the OTel agent volume — out of scope here.

## Cleanup

```bash
# Remove the patch by re-applying the chart (resets deployment to chart spec)
helm -n azure-otel upgrade azure-otel ../01_deploy_to_aks/azure-otel
kubectl delete -f manifests/httproute.yaml --ignore-not-found
helm -n azure-otel uninstall pyroscope

# Blob-side cleanup (profiles live in the storage account, not in a PVC)
rg=$(azd env get-value AZURE_RESOURCE_GROUP --cwd ../01_deploy_to_aks)
sa=$(cat .storage-account)
az identity federated-credential delete --name pyroscope-federated \
  --identity-name id-pyroscope -g "$rg" --yes
az identity delete -n id-pyroscope -g "$rg"
az storage account delete -n "$sa" -g "$rg" --yes
rm -f .storage-account
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Pyroscope pod logs `WorkloadIdentityCredential: no client ID specified` | The WI webhook injects `AZURE_CLIENT_ID` / `AZURE_FEDERATED_TOKEN_FILE` only when the **pod** carries `azure.workload.identity/use: "true"` — annotating the ServiceAccount is not enough. The values file sets it via `pyroscope.extraLabels` (the chart has no `podLabels`); if you upgraded an older release, delete the stuck StatefulSet pod to force re-render. |
| Pyroscope pod crashes with `flag provided but not defined: -query-backend.address` | Helm chart and container image versions out of sync (chart 2.x flags vs 1.x binary). Keep `--version` pinned and never set `pyroscope.image.tag`. |
| Blob requests fail with 403 `AuthorizationFailure` | Two options: (a) RBAC — the identity needs `Storage Blob Data Contributor` (Reader is not enough); (b) network — an Azure Policy forces `publicNetworkAccess: Disabled` on the account. For (b), add a private endpoint for `blob` on the AKS subnet + `privatelink.blob.core.windows.net` DNS zone linked to the AKS VNet, then verify `nslookup <sa>.blob.core.windows.net` from a pod returns a `10.x` IP. |
| Init container fails on download | AKS egress to `github.com` blocked. Mirror `pyroscope.jar` to ACR and change the initContainer's `image` + URL. |
| Spring pod boots but Pyroscope UI shows no `spring` service | `JAVA_TOOL_OPTIONS` got overwritten somewhere. Check `kubectl exec deploy/azure-otel-spring -- printenv JAVA_TOOL_OPTIONS` — it must contain BOTH `-javaagent:/pyroscope/pyroscope.jar` and the OTel one. If the OTel one is missing, the operator webhook didn't fire (cert-manager Ready? pod restarted after `Instrumentation` CR was applied?). |
| Spring pod logs `agent attach failed` | JDK version mismatch. The Pyroscope Java agent supports JDK 8/11/17/21. Bump `PYROSCOPE_AGENT_VERSION` in the patch if you're on a newer JDK. |
| Flame graph is mostly `[unknown]` frames | `async-profiler` (used by the Pyroscope agent) needs `perf_event_paranoid <= 2` AND frame-pointer-friendly libraries. AKS Ubuntu nodes are fine by default; if not, add a one-time DaemonSet that `sysctl -w kernel.perf_event_paranoid=1`. |
| Allocations / locks profiles missing | `PYROSCOPE_FORMAT` is not `jfr`. The default `collapsed` format only ships CPU. Keep `jfr`. |
| Pod CrashLoop with `failed to load javaagent` after upgrade | Bumped agent version doesn't exist at that GitHub release URL. Pin a valid tag from <https://github.com/grafana/pyroscope-java/releases>. |
| AMG “Add data source” list doesn't show Pyroscope | Confusing UI quirk — the type is registered as a core plugin in AMG Standard but is hidden from the picker until at least one datasource of that type exists. Create it via the API call in step 5b once; it will appear in the list afterwards. |
| ARM PATCH `grafanaPlugins.grafana-pyroscope-datasource` returns BadRequest | Expected. The datasource is a core plugin and is NOT in the ARM `listAvailablePlugins` allowlist (only `grafana-pyroscope-app`, the Drilldown app, is). Skip the ARM step and create the datasource via the Grafana API. |
