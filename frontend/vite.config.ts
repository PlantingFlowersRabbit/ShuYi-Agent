import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const repositoryName = env.GITHUB_REPOSITORY?.split("/").pop() || "NovelVoice-Agent";
  const base = env.VITE_PAGES_BASE_URL || (env.GITHUB_ACTIONS === "true" ? `/${repositoryName}/` : "/");
  const apiBase = env.VITE_API_BASE_URL?.trim() || "/api";
  const proxy: Record<string, string> = {
    "/outputs": "http://127.0.0.1:8000",
  };

  if (apiBase.startsWith("/")) {
    proxy[apiBase.replace(/\/+$/, "") || "/api"] = "http://127.0.0.1:8000";
  }

  return {
    base,
    plugins: [react()],
    server: {
      proxy,
    },
  };
});
