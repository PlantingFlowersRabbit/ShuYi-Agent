import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("v0.7.1 application shell", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
    Reflect.deleteProperty(globalThis, "window");
  });

  it("renders the v0.7.1 shell with the SVG brand and no access token field", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/api/v1/");
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: { location: { search: "" } },
    });
    const { default: App } = await import("./App");

    const markup = renderToStaticMarkup(createElement(App));

    expect(markup).toContain('src="/shuyi-agent-zh.svg"');
    expect(markup).toContain("v0.7.1");
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

  it("renders v0.7.1 model configuration with separate backend and model tests", async () => {
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

  it("renders v0.7.1 voice library naming without bundled resource prompts", async () => {
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

  it("renders v0.7.1 run audit history with agent trace fields", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/api/v1/");
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: { location: { search: "?page=agent-runs" } },
    });
    const { default: App } = await import("./App");

    const markup = renderToStaticMarkup(createElement(App));

    expect(markup).toContain("运行审计");
    expect(markup).toContain("Run History");
    expect(markup).toContain("Prompt SHA");
    expect(markup).toContain("Token预算");
    expect(markup).toContain("输入摘要");
    expect(markup).toContain("模型输出");
    expect(markup).toContain("JSON校验");
    expect(markup).toContain("Tool Calls");
    expect(markup).toContain("参数摘要");
    expect(markup).toContain("返回摘要");
    expect(markup).toContain("失败原因");
    expect(markup).toContain("Reflection");
    expect(markup).toContain("最终决策");
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
    expect(appSource).toContain("跳转到未选择角色的台词");
    expect(appSource).toContain("跳转到未生成配音的台词");
    expect(appSource).toContain("一键播放");
    expect(appSource).toContain("暂停播放");
    expect(appSource).toContain("继续播放");
    expect(appSource).toContain("上一句");
    expect(appSource).toContain("下一句");
    expect(appSource).toContain("整章播放列表");
    expect(appSource).toContain("当前播放台词高亮");
    expect(appSource).toContain("playPreviousQueuedChapterAudio");
    expect(appSource).toContain("playNextQueuedChapterAudio");
    expect(appSource).toContain("状态筛选");
    expect(appSource).toContain("未划分");
    expect(appSource).toContain("未选角色");
    expect(appSource).toContain("未配音");
    expect(appSource).toContain("项目工作区");
    expect(appSource).toContain("最近项目");
    expect(appSource).toContain("一键继续制作");
    expect(appSource).toContain("制作阻塞项");
    expect(appSource).toContain("智能下一步助手");
    expect(appSource).toContain("配音失败");
    expect(appSource).toContain("超长台词");
    expect(appSource).toContain("重复音色");
    expect(appSource).toContain("角色无音色");
    expect(appSource).toContain("needs_human_review");
    expect(appSource).toContain("刷新阻塞项");
    expect(appSource).toContain("导出阻塞项");
    expect(appSource).toContain("批量确认");
    expect(appSource).toContain("批量改角色");
    expect(appSource).toContain("批量重试");
    expect(appSource).toContain("批量拆分超长台词");
    expect(appSource).toContain("一键拆分长台词");
    expect(appSource).toContain("合并相邻台词");
    expect(appSource).toContain("splitLongUtterance");
    expect(appSource).toContain("mergeWithNextUtterance");
    expect(appSource).toContain("prepareRetryQueue");
    expect(appSource).toContain("/utterances/bulk-role");
    expect(appSource).toContain("splitRetryUtterances");
    expect(appSource).toContain("配音重试队列");
    expect(appSource).toContain("完整 WAV/MP3");
    expect(appSource).toContain("CSV 台本");
    expect(appSource).toContain("SRT/LRC 字幕");
    expect(appSource).toContain("角色表");
    expect(appSource).toContain("音色表");
    expect(appSource).toContain("失败清单");
    expect(appSource).toContain("片段间停顿");
    expect(appSource).toContain("头尾静音裁剪");
    expect(appSource).toContain("响度归一化");
    expect(appSource).toContain("/projects/${encodeURIComponent(projectId)}/exports/");
    expect(appSource).toContain("智能下一步助手");
    expect(appSource).toContain("把当前章节处理到可导出");
    expect(appSource).toContain("刷新建议");
    expect(appSource).toContain("planner-step-list");
    expect(appSource).toContain("章节状态小地图");
    expect(appSource).toContain("chapter-status-map");
    expect(appSource).toContain("reader-paragraph");
    expect(appSource).toContain("确认已选台词与角色");
    expect(appSource).toContain("mergeApiAudioByUtteranceId");
    expect(appSource).toContain("dubbingQueueRef");
    expect(appSource).toContain("chapterPlaybackQueueRef");
    expect(appSource).not.toContain("跳转到未确认");
    expect(appSource).not.toContain("在此后添加语句");
    expect(appSource).not.toContain("划分语句与角色匹配");
    expect(appSource).toContain("addUtteranceAfter(utterance.paragraphId, utterance.utteranceId)");
    expect(cssSource).toMatch(/\.chapter-sidebar:not\(\.collapsed\) \.sidebar-toggle\s*{[^}]*position:\s*absolute/s);
    expect(cssSource).toMatch(/\.role-stack\s*{[^}]*min-height:\s*clamp\(240px, 42vh, 520px\)/s);
    expect(cssSource).toMatch(/\.empty-state\s*{[^}]*min-height:\s*100%/s);
    expect(cssSource).toMatch(/\.brand-logo\s*{[^}]*height:\s*clamp\(38px, 5vw, 52px\)/s);
    expect(cssSource).toContain(".reader-paragraph.failed");
    expect(cssSource).toContain(".chapter-status-map");
    expect(cssSource).toContain(".status-filter-bar");
    expect(cssSource).not.toContain(".access-token-field");
  });

  it("renders v0.7.1 guided production controls, memory, blockers, export presets, and safer bulk role edits", async () => {
    const [{ readFileSync }, { fileURLToPath }] = await Promise.all([
      import("node:fs"),
      import("node:url"),
    ]);
    const appSource = readFileSync(fileURLToPath(new URL("./App.tsx", import.meta.url)), "utf-8");

    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test/api/v1/");
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: { location: { search: "" } },
    });
    const { default: App } = await import("./App");

    const markup = renderToStaticMarkup(createElement(App));

    expect(markup).toContain("制作台");
    expect(markup).toContain("项目记忆");
    expect(markup).toContain("运行审计");
    expect(markup).toContain("设置");
    expect(markup).not.toContain("Agent追踪</button>");
    expect(markup).not.toContain("模型配置</button>");
    expect(markup).not.toContain("加载红楼梦示例项目");

    expect(appSource).toContain("type Page = \"main\" | \"voices\" | \"memory\" | \"agent-runs\" | \"models\"");
    expect(appSource).toContain("renderMemoryPage");
    expect(appSource).toContain("角色证据");
    expect(appSource).toContain("设定记忆");
    expect(appSource).toContain("用户纠错");
    expect(appSource).toContain("/story-bible/memory-context");
    expect(appSource).toContain("/story-bible/facts");

    expect(appSource).toContain("productionPrimaryAction");
    expect(appSource).toContain("上传小说");
    expect(appSource).toContain("解析章节");
    expect(appSource).toContain("确认台词与角色");
    expect(appSource).toContain("生成缺失配音");
    expect(appSource).toContain("导出制作包");
    expect(appSource).toContain("处理阻塞项");
    expect(appSource).toContain("production-stepper");
    expect(appSource).toContain("后端待检测");
    expect(appSource).toContain("前端本地规则可继续");
    expect(appSource).toContain("智能下一步助手");
    expect(appSource).not.toContain(">生成计划</button>");
    expect(appSource).not.toContain(">执行计划</button>");
    expect(appSource).not.toContain(">复盘计划</button>");

    expect(appSource).toContain("制作阻塞项");
    expect(appSource).toContain("严重级别");
    expect(appSource).toContain("影响");
    expect(appSource).toContain("推荐操作");
    expect(appSource).toContain("处理状态");
    expect(appSource).not.toContain("质量检查面板");
    expect(appSource).not.toContain("<div className=\"section-title\">审稿队列</div>");

    expect(appSource).toContain("bulkRoleTargetId");
    expect(appSource).toContain("bulkRolePreviewArmed");
    expect(appSource).toContain("请选择目标角色");
    expect(appSource).toContain("预览影响");
    expect(appSource).not.toContain("const fallbackRole = roles.find");

    expect(appSource).toContain("exportPreset");
    expect(appSource).toContain("试听版");
    expect(appSource).toContain("交付版");
    expect(appSource).toContain("后期版");
    expect(appSource).toContain("pause_ms: exportOptions.pauseMs");
    expect(appSource).toContain("speed: exportOptions.speed");
    expect(appSource).toContain("trim_silence: exportOptions.trimSilence");
    expect(appSource).toContain("normalize_audio: exportOptions.normalizeAudio");
    expect(appSource).toContain("target_peak: exportOptions.targetPeak");
  });

  it("classifies paragraph heatmap status with failure and completion priority", async () => {
    const { paragraphDubbingStatus } = await import("./App");

    expect(paragraphDubbingStatus([])).toBe("unsegmented");
    expect(paragraphDubbingStatus([{ roleId: "", audioStatus: "尚未生成" }])).toBe("unselected-role");
    expect(paragraphDubbingStatus([{ roleId: "hero", audioStatus: "尚未生成" }])).toBe("undubbed");
    expect(paragraphDubbingStatus([{ roleId: "hero", audioPath: "outputs/audio/u-001.wav" }])).toBe("dubbed");
    expect(paragraphDubbingStatus([{ roleId: "hero", audioPath: "outputs/audio/u-001.wav", audioError: "TTS error" }])).toBe("failed");
    expect(paragraphDubbingStatus([{ roleId: "hero", audioStatus: "音频生成失败：文本过长" }])).toBe("failed");
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
    const parserInternalError = new ApiRequestError(500, "Internal Server Error");
    const reachableFailure = new ApiRequestError(503, "TTS模型尚未就绪");

    expect(apiFailureMessage("音频生成失败", disconnected)).toBe("音频生成失败：后端未连接");
    expect(apiFailureMessage("测试连接失败", staticHostNotFound)).toBe("测试连接失败：后端未连接");
    expect(apiFailureMessage("测试模型失败", reachableFailure)).toBe("测试模型失败：TTS模型尚未就绪");
    expect(documentParseFallbackMessage(disconnected)).toBe(
      "后端未连接，已使用前端本地规则解析章节；可继续制作，连接后端后可启用 Agent 规则增强。",
    );
    expect(documentParseFallbackMessage(parserInternalError)).toBe(
      "后端解析暂不可用，已使用前端本地规则解析章节；可继续制作。错误：Internal Server Error",
    );
  });

  it("summarizes batch dubbing counts without duplicating per-line TTS failure text", async () => {
    const { formatBatchDubbingStatus } = await import("./App");

    const message = formatBatchDubbingStatus({
      success_count: 104,
      skipped_count: 0,
      failed_count: 1,
      groups: [
        { voice_resource_id: "voice-auto-0002", count: 23 },
        { voice_resource_id: "voice-auto-0001", count: 54 },
      ],
      errors: [
        {
          statement_id: "p-0001-u-099",
          message: "当前台词文本长度 167 字，超过本地 TTS 单条上限 120 字。",
        },
      ],
    });

    expect(message).toContain("成功 104 条，跳过 0 条，失败 1 条");
    expect(message).toContain("失败原因已标记在对应台词");
    expect(message).not.toContain("当前台词文本长度 167 字");
  });
});
