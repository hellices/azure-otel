import { getServerConfig } from "@/lib/config";

// Runtime-injected config so the SPA can reach the FastAPI backend without baking
// URLs into the bundle. Override PYTHON_API_BASE_URL via the AKS env to swap.
export const dynamic = "force-dynamic";

export function GET(): Response {
  const cfg = getServerConfig();
  const body = `window.__APP_CONFIG__ = ${JSON.stringify({
    pythonApiBaseUrl: cfg.pythonApiBaseUrl,
  })};`;
  return new Response(body, {
    headers: {
      "content-type": "application/javascript; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}
