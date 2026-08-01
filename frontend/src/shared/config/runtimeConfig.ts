export const APP_BRAND = "书弈 Agent";
export const APP_VERSION = "0.4.0";

type RuntimeEnv = {
  BASE_URL?: string;
  VITE_API_BASE_URL?: string;
};

export type RuntimeConfig = {
  pagesBase: string;
  apiBase: string;
  apiUrl: (path: string) => string;
  mediaUrl: (path: string) => string;
};

function normalizePagesBase(value: string | undefined): string {
  const base = value?.trim() || "/";
  return `${base.startsWith("/") ? "" : "/"}${base.replace(/\/+$/, "")}/`;
}

function normalizeApiBase(value: string | undefined): string {
  const base = value?.trim() || "/api/v1";
  return base === "/" ? "" : base.replace(/\/+$/, "");
}

export function resolveRuntimeConfig(env: RuntimeEnv): RuntimeConfig {
  const pagesBase = normalizePagesBase(env.BASE_URL);
  const apiBase = normalizeApiBase(env.VITE_API_BASE_URL);

  return {
    pagesBase,
    apiBase,
    apiUrl(path: string) {
      if (/^https?:\/\//i.test(path)) return path;
      const endpoint = path.replace(/^\/+/, "");
      return apiBase ? `${apiBase}/${endpoint}` : `/${endpoint}`;
    },
    mediaUrl(path: string) {
      if (/^https?:\/\//i.test(path)) return path;
      const endpoint = path.startsWith("/") ? path : `/${path}`;
      if (!/^https?:\/\//i.test(apiBase)) return endpoint;
      return `${new URL(apiBase).origin}${endpoint}`;
    },
  };
}

export const runtimeConfig = resolveRuntimeConfig(import.meta.env);
