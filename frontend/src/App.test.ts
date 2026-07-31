import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("v0.4 application shell", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
    Reflect.deleteProperty(globalThis, "window");
  });

  it("renders the release brand, workflow mode selector, and configured API URLs", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/api/v1/");
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: { location: { search: "" } },
    });
    const { default: App } = await import("./App");

    const markup = renderToStaticMarkup(createElement(App));

    expect(markup).toContain("书弈 Agent v0.4.0");
    expect(markup).toContain("自动配音");
    expect(markup).toContain("分步配音");
    expect(markup).toContain('aria-pressed="true"');
    expect(markup).toContain("https://api.example.test/api/v1/voice-resources/voice-male-narrator/audio");
  });
});
