import { describe, expect, it } from "vitest";

describe("v0.4 runtime configuration", () => {
  it("publishes the release brand and version", async () => {
    const { APP_BRAND, APP_VERSION } = await import("./runtimeConfig");

    expect(APP_BRAND).toBe("书弈 Agent");
    expect(APP_VERSION).toBe("0.4.0");
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
});
