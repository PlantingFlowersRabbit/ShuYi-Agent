import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("v0.5 application shell", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
    Reflect.deleteProperty(globalThis, "window");
  });

  it("renders the v0.5.0 shell with the SVG brand and no access token field", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/api/v1/");
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: { location: { search: "" } },
    });
    const { default: App } = await import("./App");

    const markup = renderToStaticMarkup(createElement(App));

    expect(markup).toContain('src="/shuyi-agent-zh.svg"');
    expect(markup).toContain("v0.5.0");
    expect(markup).toContain("自动配音");
    expect(markup).toContain("分步配音");
    expect(markup).toContain("文档解析");
    expect(markup).toContain("上传小说后点击左侧“文档解析”");
    expect(markup).not.toContain("上传小说后点击左侧“文本模型”");
    expect(markup).toContain('aria-pressed="true"');
    expect(markup).not.toContain("访问令牌");
    expect(markup).not.toContain('aria-label="后端访问令牌"');
    expect(markup).toContain('<div class="novel-preview" aria-label="小说开头预览"></div>');
  });

  it("renders v0.5.0 model configuration with TTS download deployment progress", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/api/v1/");
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: { location: { search: "?page=models" } },
    });
    const { default: App } = await import("./App");

    const markup = renderToStaticMarkup(createElement(App));

    expect(markup).toContain("文本模型");
    expect(markup).toContain("TTS模型");
    expect(markup).toContain("测试连接");
    expect(markup).toContain("下载并部署");
    expect(markup).toContain('aria-label="文本模型 API Key"');
    expect(markup).toContain('placeholder="eg: https://api.deepseek.com"');
    expect(markup).toContain('placeholder="eg: deepseek-v4-flash"');
    expect(markup).toContain('placeholder="sk-xxx..."');
    expect(markup).toContain('value="/models/Qwen3-TTS-12Hz-1.7B-Base"');
    expect(markup).toContain('value="/models/Qwen3-TTS-12Hz-1.7B-VoiceDesign"');
    expect(markup).not.toContain('value="./models/Qwen3-TTS-12Hz-1.7B-Base"');
    expect(markup).toContain('aria-label="TTS模型下载并部署进度"');
  });

  it("renders v0.5.0 voice library naming without bundled resource prompts", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/api/v1/");
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: { location: { search: "?page=voices" } },
    });
    const { default: App } = await import("./App");

    const markup = renderToStaticMarkup(createElement(App));

    expect(markup).toContain("音色列表");
    expect(markup).toContain("添加音色");
    expect(markup).toContain("生成音色");
  });

  it("keeps statement insertion available after existing utterances and sidebar toggle floating", async () => {
    const [{ readFileSync }, { fileURLToPath }] = await Promise.all([
      import("node:fs"),
      import("node:url"),
    ]);
    const appSource = readFileSync(fileURLToPath(new URL("./App.tsx", import.meta.url)), "utf-8");
    const cssSource = readFileSync(fileURLToPath(new URL("./styles.css", import.meta.url)), "utf-8");

    expect(appSource).toContain("在此后添加语句");
    expect(appSource).toContain("addUtteranceAfter(utterance.paragraphId, utterance.utteranceId)");
    expect(cssSource).toMatch(/\.chapter-sidebar:not\(\.collapsed\) \.sidebar-toggle\s*{[^}]*position:\s*absolute/s);
    expect(cssSource).toMatch(/\.role-stack\s*{[^}]*min-height:\s*clamp\(240px, 42vh, 520px\)/s);
    expect(cssSource).toMatch(/\.empty-state\s*{[^}]*min-height:\s*100%/s);
    expect(cssSource).toMatch(/\.brand-logo\s*{[^}]*height:\s*clamp\(38px, 5vw, 52px\)/s);
    expect(cssSource).not.toContain(".access-token-field");
  });

  it("parses numbered SSE frames and keeps an incomplete tail", async () => {
    const { parseAgentSseBuffer } = await import("./App");
    const parsed = parseAgentSseBuffer(
      'id: 1\nevent: role_selected\ndata: {"speaker_name":"旁白"}\n\nid: 2\nevent: completed\n',
    );

    expect(parsed.events).toEqual([
      { id: 1, event: "role_selected", data: { speaker_name: "旁白" } },
    ]);
    expect(parsed.remainder).toContain("id: 2");
  });

  it("only asks for role unbinding when delete fails with a reference conflict", async () => {
    const { ApiRequestError, isRoleDeleteReferenceConflict } = await import("./App");

    expect(
      isRoleDeleteReferenceConflict(
        new ApiRequestError(409, {
          delete_result: { referenced_count: 1, deleted: false },
        }),
      ),
    ).toBe(true);
    expect(isRoleDeleteReferenceConflict(new ApiRequestError(500, "Error"))).toBe(false);
    expect(
      isRoleDeleteReferenceConflict(
        new ApiRequestError(409, {
          delete_result: { referenced_count: 0, deleted: false },
        }),
      ),
    ).toBe(false);
  });
});
