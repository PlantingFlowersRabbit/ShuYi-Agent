import { describe, expect, it } from "vitest";

describe("v0.5.1 runtime configuration", () => {
  it("publishes the release brand and version", async () => {
    const { APP_BRAND, APP_VERSION } = await import("./runtimeConfig");

    expect(APP_BRAND).toBe("书弈 Agent");
    expect(APP_VERSION).toBe("0.5.1");
  });

  it("keeps the Pages base separate from the versioned API base", async () => {
    const { resolveRuntimeConfig } = await import("./runtimeConfig");
    const config = resolveRuntimeConfig({
      BASE_URL: "/ShuYi-Agent/",
      VITE_API_BASE_URL: "https://api.example.test/api/v1/",
    });

    expect(config.pagesBase).toBe("/ShuYi-Agent/");
    expect(config.apiBase).toBe("https://api.example.test/api/v1");
    expect(config.apiUrl("/characters")).toBe("https://api.example.test/api/v1/characters");
    expect(config.mediaUrl("/outputs/audio/example.wav")).toBe(
      "https://api.example.test/outputs/audio/example.wav",
    );
  });

  it("accepts a bare API domain and treats it as the v1 HTTPS API base", async () => {
    const { resolveRuntimeConfig } = await import("./runtimeConfig");
    const config = resolveRuntimeConfig({
      BASE_URL: "/ShuYi-Agent/",
      VITE_API_BASE_URL: "cnb.example.test",
    });

    expect(config.apiBase).toBe("https://cnb.example.test/api/v1");
    expect(config.apiUrl("characters")).toBe("https://cnb.example.test/api/v1/characters");
    expect(config.mediaUrl("/outputs/audio/example.wav")).toBe(
      "https://cnb.example.test/outputs/audio/example.wav",
    );
  });

  it("normalizes copied CNB URLs with markdown or smart-quote noise", async () => {
    const { resolveRuntimeConfig } = await import("./runtimeConfig");
    const config = resolveRuntimeConfig({
      BASE_URL: "/ShuYi-Agent/",
      VITE_API_BASE_URL: "[https://q0owelusgf-8000.cnb.run”点击“测试连接”",
    });

    expect(config.apiBase).toBe("https://q0owelusgf-8000.cnb.run/api/v1");
    expect(config.apiUrl("/model-config")).toBe(
      "https://q0owelusgf-8000.cnb.run/api/v1/model-config",
    );
  });
});
