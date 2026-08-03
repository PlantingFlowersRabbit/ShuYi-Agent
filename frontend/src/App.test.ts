import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("v0.5.4 application shell", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
    Reflect.deleteProperty(globalThis, "window");
  });

  it("renders the v0.5.4 shell with the SVG brand and no access token field", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/api/v1/");
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: { location: { search: "" } },
    });
    const { default: App } = await import("./App");

    const markup = renderToStaticMarkup(createElement(App));

    expect(markup).toContain('src="/shuyi-agent-zh.svg"');
    expect(markup).toContain("v0.5.4");
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

  it("renders v0.5.4 model configuration with separate backend and model tests", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/api/v1/");
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: { location: { search: "?page=models" } },
    });
    const { default: App } = await import("./App");

    const markup = renderToStaticMarkup(createElement(App));

    expect(markup).toContain("后端 API");
    expect(markup).toContain('aria-label="后端 API Base URL"');
    expect(markup).toContain('value="https://api.example.test/api/v1"');
    expect(markup).toContain("保存后端地址");
    expect(markup).toContain("文本模型");
    expect(markup).toContain("TTS模型");
    expect(markup).toContain("测试连接");
    expect(markup).toContain("测试模型");
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

  it("renders v0.5.4 voice library naming without bundled resource prompts", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/api/v1/");
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: { location: { search: "?page=voices" } },
    });
    const { default: App } = await import("./App");

    const markup = renderToStaticMarkup(createElement(App));

    expect(markup).toContain("音色列表");
    expect(markup).toContain("导出音色库");
    expect(markup).toContain("添加音色");
    expect(markup).toContain("生成音色");
  });

  it("renames user-facing statement controls to dialogue copy", async () => {
    const [{ readFileSync }, { fileURLToPath }] = await Promise.all([
      import("node:fs"),
      import("node:url"),
    ]);
    const appSource = readFileSync(fileURLToPath(new URL("./App.tsx", import.meta.url)), "utf-8");
    const cssSource = readFileSync(fileURLToPath(new URL("./styles.css", import.meta.url)), "utf-8");

    expect(appSource).toContain("划分台词与角色匹配");
    expect(appSource).toContain("添加第一条台词");
    expect(appSource).toContain("在此后添加台词");
    expect(appSource).toContain("台词文本");
    expect(appSource).toContain("生成配音");
    expect(appSource).toContain("跳转到未确认");
    expect(appSource).toContain("确认已选台词与角色");
    expect(appSource).toContain("mergeApiAudioByUtteranceId");
    expect(appSource).toContain("dubbingQueueRef");
    expect(appSource).not.toContain("在此后添加语句");
    expect(appSource).not.toContain("划分语句与角色匹配");
    expect(appSource).toContain("addUtteranceAfter(utterance.paragraphId, utterance.utteranceId)");
    expect(cssSource).toMatch(/\.chapter-sidebar:not\(\.collapsed\) \.sidebar-toggle\s*{[^}]*position:\s*absolute/s);
    expect(cssSource).toMatch(/\.role-stack\s*{[^}]*min-height:\s*clamp\(240px, 42vh, 520px\)/s);
    expect(cssSource).toMatch(/\.empty-state\s*{[^}]*min-height:\s*100%/s);
    expect(cssSource).toMatch(/\.brand-logo\s*{[^}]*height:\s*clamp\(38px, 5vw, 52px\)/s);
    expect(cssSource).not.toContain(".access-token-field");
  });

  it("checks backend connectivity before sending large document parse payloads", async () => {
    const [{ readFileSync }, { fileURLToPath }] = await Promise.all([
      import("node:fs"),
      import("node:url"),
    ]);
    const appSource = readFileSync(fileURLToPath(new URL("./App.tsx", import.meta.url)), "utf-8");
    const splitFunction = appSource.slice(
      appSource.indexOf("async function runAiChapterSplit()"),
      appSource.indexOf("async function selectChapter"),
    );

    expect(splitFunction).toContain('requestJson<ConnectionTestResponse>("/connection-test")');
    expect(splitFunction.indexOf('"/connection-test"')).toBeLessThan(
      splitFunction.indexOf('"/books/agent-chapter-split"'),
    );
  });

  it("places role deletion after voice matching details and removes the inline voice play button", async () => {
    const [{ readFileSync }, { fileURLToPath }] = await Promise.all([
      import("node:fs"),
      import("node:url"),
    ]);
    const appSource = readFileSync(fileURLToPath(new URL("./App.tsx", import.meta.url)), "utf-8");
    const roleCard = appSource.slice(
      appSource.indexOf('<article className="role-card"'),
      appSource.indexOf("{aiRoleCandidates.length > 0"),
    );

    expect(roleCard).not.toContain('aria-label="播放音色"');
    expect(roleCard).not.toContain("onClick={() => playVoicePreview(voice)}");
    expect(roleCard).toContain("<strong>音色匹配</strong>");
    expect(roleCard.indexOf("<strong>音色匹配</strong>")).toBeLessThan(roleCard.indexOf("删除角色"));
    expect(roleCard.indexOf("<AuthorizedAudio source={voiceAudioSrc(voice)} />")).toBeLessThan(
      roleCard.indexOf("删除角色"),
    );
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

  it("formats disconnected backend failures as ApiRequestError while keeping reachable API details", async () => {
    const { ApiRequestError, apiFailureMessage, documentParseFallbackMessage } = await import("./App");

    const disconnected = new ApiRequestError(0, "后端不可连接");
    const staticHostNotFound = new ApiRequestError(404, "Not Found");
    const reachableFailure = new ApiRequestError(503, "TTS模型尚未就绪");

    expect(apiFailureMessage("音频生成失败", disconnected)).toBe("音频生成失败：ApiRequestError");
    expect(apiFailureMessage("测试连接失败", staticHostNotFound)).toBe("测试连接失败：ApiRequestError");
    expect(apiFailureMessage("测试模型失败", reachableFailure)).toBe("测试模型失败：TTS模型尚未就绪");
    expect(documentParseFallbackMessage(disconnected)).toBe(
      "没有连接后端，解析失败，采用前端默认简易解析策略：ApiRequestError",
    );
  });
});
