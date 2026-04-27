# azure-otel Helm chart

Bundles the three sketch services into one release on AKS.

| Service     | Image tag (in `ghcr.io/hellices/azure-otel`) | Port | Exposure |
|-------------|----------------------------------------------|------|----------|
| spring-java | `spring-java-latest`                         | 8080 | **Cluster-internal only** (CRUD + embedded SQLite on PVC) |
| python      | `python-latest`                              | 8000 | Cluster-internal; reachable from the browser via Ingress `/api/*` |
| nodejs      | `nodejs-latest`                              | 3000 | Public (Ingress `/`) |

## Service-to-service communication (in-cluster only)

- `python` calls `spring` via cluster DNS `http://<release>-spring:8080`
  (auto-injected as `JAVA_API_BASE_URL`). Spring is **never** exposed publicly.
- A `NetworkPolicy` (`networkPolicy.spring.enabled=true`, on by default) restricts
  Spring's pod ingress to Python pods of the same release. Requires a CNI that
  enforces NetworkPolicy (Azure CNI Powered by Cilium, Calico, or Azure NPM on
  AKS).
- The browser-facing `PYTHON_API_BASE_URL` (rendered into `/config.js`) defaults
  to `/api` when Ingress is enabled, so the SPA calls FastAPI same-origin and no
  CORS rules are needed.

## Install

```powershell
helm upgrade --install azure-otel .\01_deploy_to_aks\azure-otel `
  --namespace azure-otel --create-namespace
```

## Pin a specific build

```powershell
helm upgrade --install azure-otel .\01_deploy_to_aks\azure-otel `
  --namespace azure-otel --create-namespace `
  --set spring.imageTag=spring-java-sha-abc1234 `
  --set python.imageTag=python-sha-abc1234 `
  --set nodejs.imageTag=nodejs-sha-abc1234
```

## Expose publicly

```powershell
# Example with AKS Web App Routing (nginx-based controller managed by AKS)
helm upgrade --install azure-otel .\01_deploy_to_aks\azure-otel `
  --namespace azure-otel `
  --set ingress.enabled=true `
  --set ingress.className=webapprouting.kubernetes.azure.com `
  --set ingress.host=azure-otel.example.com `
  --set 'ingress.annotations.nginx\.ingress\.kubernetes\.io/rewrite-target=/$2' `
  --set 'ingress.apiPathPrefix=/api(/|$)(.*)'
```

The `rewrite-target` + capture-group `apiPathPrefix` strip the `/api` prefix
before forwarding to FastAPI (so `GET /api/items` from the browser becomes
`GET /items` at python). For other controllers (AGIC, Traefik, Istio Gateway)
use the equivalent rewrite mechanism, or set
`nodejs.pythonPublicBaseUrl=https://<host>/api` and serve FastAPI under a
sub-path.

Quick test without ingress (port-forward):

```powershell
kubectl -n azure-otel port-forward svc/azure-otel-nodejs 3000:3000
# In another terminal, also forward python so the browser SPA can reach it:
kubectl -n azure-otel port-forward svc/azure-otel-python 8000:8000
# Re-deploy with --set nodejs.pythonPublicBaseUrl=http://localhost:8000
```

## Uninstall

```powershell
helm uninstall azure-otel -n azure-otel
kubectl -n azure-otel delete pvc -l app.kubernetes.io/part-of=azure-otel
```
