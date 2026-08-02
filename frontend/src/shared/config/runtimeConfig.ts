export const APP_BRAND = "书弈 Agent";
export const APP_VERSION = "0.5.2";

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
  const rawBase = sanitizeApiBaseInput(value?.trim() || "/api/v1");
  if (rawBase === "/") return "";
  if (rawBase.startsWith("/")) return rawBase.replace(/\/+$/, "");

  const withScheme = /^https?:\/\//i.test(rawBase) ? rawBase : `https://${rawBase}`;
  const normalized = withScheme.replace(/\/+$/, "");
  try {
    const url = new URL(normalized);
    const path = url.pathname.replace(/\/+$/, "");
    if (!path) url.pathname = "/api/v1";
    return url.toString().replace(/\/+$/, "");
  } catch {
    return normalized;
  }
}

function sanitizeApiBaseInput(value: string): string {
  const trimmed = value.trim().replace(/^[<\[(（「『"'“‘]+/, "").replace(/[>\])） 」』"'”’]+$/, "");
  const urlMatch = trimmed.match(/https?:\/\/[^\s<>\])）"'“”‘’]+/i);
  if (urlMatch) return urlMatch[0].replace(/[>\])）"'”’]+$/, "");
  const domainMatch = trimmed.match(/[a-z0-9.-]+\.[a-z]{2,}(?::\d+)?(?:\/[^\s<>\])）"'“”‘’]*)?/i);
  if (domainMatch) return domainMatch[0].replace(/[>\])）"'”’]+$/, "");
  return trimmed;
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
