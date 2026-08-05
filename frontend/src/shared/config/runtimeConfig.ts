export const APP_BRAND = "书弈 Agent";
export const APP_VERSION = "0.7.2";

type RuntimeEnv = {
  BASE_URL?: string;
  VITE_API_BASE_URL?: string;
};

export type RuntimeConfig = {
  pagesBase: string;
  apiBase: string;
  setApiBase: (value: string) => string;
  apiUrl: (path: string) => string;
  mediaUrl: (path: string) => string;
};

export const API_BASE_STORAGE_KEY = "shuyi-agent-api-base-url";

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

function normalizeCopiedUrlText(value: string): string {
  return value.replace(/[‐-―−﹘﹣－]/g, "-");
}

function sanitizeApiBaseInput(value: string): string {
  const trimmed = normalizeCopiedUrlText(value)
    .trim()
    .replace(/^[<\[(（「『"'“‘]+/, "")
    .replace(/[>\])） 」』"'”’]+$/, "");
  const urlMatch = trimmed.match(/https?:\/\/[^\s<>\])）"'“”‘’]+/i);
  if (urlMatch) return urlMatch[0].replace(/[>\])）"'”’]+$/, "");
  const domainMatch = trimmed.match(/[a-z0-9.-]+\.[a-z]{2,}(?::\d+)?(?:\/[^\s<>\])）"'“”‘’]*)?/i);
  if (domainMatch) return domainMatch[0].replace(/[>\])）"'”’]+$/, "");
  return trimmed;
}

function readStoredApiBase(): string | undefined {
  if (typeof window === "undefined" || !("localStorage" in window)) return undefined;
  try {
    return window.localStorage.getItem(API_BASE_STORAGE_KEY) || undefined;
  } catch {
    return undefined;
  }
}

function writeStoredApiBase(value: string): void {
  if (typeof window === "undefined" || !("localStorage" in window)) return;
  try {
    window.localStorage.setItem(API_BASE_STORAGE_KEY, value);
  } catch {
    // Ignore storage failures; the in-memory runtime config still updates.
  }
}

export function resolveRuntimeConfig(env: RuntimeEnv): RuntimeConfig {
  const pagesBase = normalizePagesBase(env.BASE_URL);
  let apiBase = normalizeApiBase(env.VITE_API_BASE_URL);

  return {
    pagesBase,
    get apiBase() {
      return apiBase;
    },
    setApiBase(value: string) {
      apiBase = normalizeApiBase(value);
      writeStoredApiBase(apiBase);
      return apiBase;
    },
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

export const runtimeConfig = resolveRuntimeConfig({
  ...import.meta.env,
  VITE_API_BASE_URL: readStoredApiBase() || import.meta.env.VITE_API_BASE_URL,
});
