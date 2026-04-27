export type AppConfig = {
  pythonApiBaseUrl: string;
};

declare global {
  interface Window {
    __APP_CONFIG__?: AppConfig;
  }
}

export function getServerConfig(): AppConfig {
  return {
    pythonApiBaseUrl:
      process.env.PYTHON_API_BASE_URL ?? "http://localhost:8000",
  };
}

export function getClientConfig(): AppConfig {
  if (typeof window === "undefined") return getServerConfig();
  return (
    window.__APP_CONFIG__ ?? { pythonApiBaseUrl: "http://localhost:8000" }
  );
}
