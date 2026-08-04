import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  createWorkflowState,
  transitionWorkflow,
  type WorkflowMode,
} from "./features/agent-workflow/workflowMachine";
import {
  APP_BRAND,
  APP_VERSION,
  runtimeConfig,
} from "./shared/config/runtimeConfig";

export class ApiRequestError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown) {
    super(formatApiErrorDetail(detail));
    this.name = "ApiRequestError";
    this.status = status;
    this.detail = detail;
  }
}

function formatApiErrorDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
    return JSON.stringify(detail);
  }
  return String(detail || "请求失败");
}

export function apiFailureDetail(error: unknown): string {
  if (error instanceof ApiRequestError) {
    const message = error.message || "ApiRequestError";
    if (
      error.status === 0 ||
      (error.status === 404 && ["Not Found", "请求失败"].includes(message))
    ) {
      return "ApiRequestError";
    }
    return message;
  }
  return error instanceof Error ? error.message : String(error);
}

export function apiFailureMessage(prefix: string, error: unknown): string {
  return `${prefix}：${apiFailureDetail(error)}`;
}

export function documentParseFallbackMessage(error: unknown): string {
  if (error instanceof ApiRequestError && error.status === 0) {
    return "没有连接后端，解析失败，采用前端默认简易解析策略：ApiRequestError";
  }
  return apiFailureMessage("文档解析失败，已使用本地章节索引兜底", error);
}

export function formatBatchDubbingStatus(
  data: BatchDubbingStatusPayload,
): string {
  const groupSummary = data.groups
    .map((group) => `${group.voice_resource_id}×${group.count}`)
    .join("，");
  const failureSummary =
    data.failed_count > 0
      ? "；失败原因已标记在对应台词，请直接查看对应条目"
      : "";
  return `批量生成配音完成：成功 ${data.success_count} 条，跳过 ${data.skipped_count} 条，失败 ${data.failed_count} 条；分组 ${groupSummary || "无待生成"}${failureSummary}`;
}

export function isRoleDeleteReferenceConflict(
  error: unknown,
): error is ApiRequestError {
  if (!(error instanceof ApiRequestError) || error.status !== 409) return false;
  const detail = error.detail as {
    delete_result?: { referenced_count?: unknown };
  } | null;
  const referencedCount = detail?.delete_result?.referenced_count;
  return typeof referencedCount === "number" && referencedCount > 0;
}

type Page = "main" | "voices" | "memory" | "agent-runs" | "models";
type VoiceMode = "voice_cloning" | "voice_design";
type ExportPreset = "preview" | "delivery" | "post";

type Chapter = {
  chapterId: string;
  title: string;
  body: string;
  bodyStart?: number;
  bodyEnd?: number;
};

type ChapterHeadingMatch = {
  index: number;
  text: string;
  title: string;
};

type UploadedNovelFile = {
  filename: string;
  contentBase64: string;
  kind: "epub";
};

type NovelFileUpload = {
  text: string;
  preview: string;
  uploadedFile: UploadedNovelFile | null;
};

type ApiChapter = {
  chapter_id: string;
  title: string;
  body: string;
};

type ApiChapterSplitResponse = {
  chapters: ApiChapter[];
  agent: {
    status: string;
    rule_path: string | null;
    trace: string[];
    validation_errors: string[];
  };
};

type ParagraphModule = {
  paragraphId: string;
  text: string;
  collapsed: boolean;
  deleted: boolean;
};

type ApiParagraph = {
  paragraph_id: string;
  text: string;
  collapsed: boolean;
  deleted: boolean;
};

type VoiceResource = {
  voiceId: string;
  name: string;
  gender: string;
  description: string;
  suitableRoleTypes: string[];
  referenceText: string;
  referenceAudioPath: string;
  playableAudioPath: string;
  generated: boolean;
};

type ApiVoiceResource = {
  voice_id: string;
  name: string;
  gender?: string | null;
  description: string;
  suitable_role_types?: string[];
  reference_text: string;
  reference_audio_path: string;
  playable_audio_path?: string | null;
  generated: boolean;
};

type RoleCard = {
  roleId: string;
  name: string;
  aliases: string[];
  gender: string;
  profile: string;
  description: string;
  voiceMode: VoiceMode;
  voiceResourceId: string;
  referenceAudioPath: string;
  referenceText: string;
  designPrompt: string;
  voiceDescription: string;
  voiceSampleText: string;
  playableVoicePath: string;
  voiceMatchScore?: number | null;
  voiceMatchReason?: string | null;
  voiceGeneratedByAi: boolean;
};

type ApiRoleCard = {
  role_id: string;
  name: string;
  aliases?: string[];
  gender?: string | null;
  profile?: string | null;
  description: string;
  voice_mode: VoiceMode;
  voice_resource_id: string | null;
  reference_audio_path: string | null;
  reference_text: string | null;
  design_prompt: string | null;
  voice_description?: string | null;
  voice_sample_text?: string | null;
  playable_voice_path?: string | null;
  voice_match_score?: number | null;
  voice_match_reason?: string | null;
  voice_generated_by_ai?: boolean;
};

type UtteranceDraft = {
  utteranceId: string;
  paragraphId: string;
  text: string;
  roleId: string;
  speakerName: string;
  audioStatus: string;
  audioUrl?: string;
  audioPath?: string;
  audioDuration?: number;
  audioProvider?: string;
  audioModel?: string;
  audioError?: string;
  needsHumanReview: boolean;
};

type ApiUtterance = {
  utterance_id: string;
  paragraph_id?: string;
  text: string;
  speaker_name: string;
  speaker_role_id: string | null;
  voice_mode: VoiceMode;
  emotion: string;
  speed: number;
  volume: number;
  design_prompt: string | null;
  confidence?: number;
  needs_human_review?: boolean;
  audio_status?: string;
  audio_path?: string;
  audio_url?: string;
  audio_duration?: number;
  audio_provider?: string;
  audio_model?: string;
  audio_error?: string;
};

type ApiChapterParagraphsResponse = {
  paragraphs: ApiParagraph[];
  can_segment: boolean;
  utterance_drafts?: ApiUtterance[];
};

type AiRoleCandidate = {
  name: string | null;
  aliases: string[];
  gender: string | null;
  profile: string | null;
  voice_direction: string | null;
  evidence: string[];
  confidence: number;
  needs_human_review: boolean;
};

type RoleAnalysisRunResponse = {
  status: string;
  thread_id: string;
  message: string;
  role_candidates: AiRoleCandidate[];
  roles?: ApiRoleCard[];
  voices?: ApiVoiceResource[];
  auto_role_report?: {
    added_count: number;
    updated_count: number;
    generated_voice_count: number;
  } | null;
};

type AiRoleSelectionEvent = {
  paragraph_id: string;
  utterance_id: string;
  text: string;
  speaker_role_id: string | null;
  speaker_name: string;
  confidence: number;
  needs_human_review: boolean;
  reason: string;
};

type DubbingArrangementResponse = {
  status: string;
  thread_id: string;
  message: string;
  utterances_by_paragraph: Record<string, ApiUtterance[]>;
  role_selection_events: AiRoleSelectionEvent[];
  failure?: {
    paragraph_id: string;
    error_code: string;
    message: string;
  } | null;
};

type ToolCallTrace = {
  tool_call_id: string;
  tool_name: string;
  status: string;
  permission_scope?: string;
  arguments_summary?: string;
  output_summary?: string;
  failure?: string | null;
  duration_ms?: number;
};

type AgentTrace = {
  run_id: string;
  project_id: string;
  chapter_id: string;
  agent_id: string;
  agent_name: string;
  prompt_id: string;
  prompt_version: string;
  prompt_sha256: string;
  model_name: string;
  provider_base_url: string;
  temperature: number;
  max_tokens: number;
  estimated_prompt_tokens: number;
  estimated_input_tokens: number;
  estimated_output_tokens: number;
  estimated_total_tokens: number;
  context_window: number;
  input_summary: string;
  raw_model_output: string;
  parsed_output: unknown;
  validation_status: string;
  validation_errors: unknown[];
  reflection_count: number;
  reflection_trace: unknown[];
  final_decision: string;
  human_review_count: number;
  created_at?: string;
  updated_at?: string;
  duration_ms?: number;
  token_context_report?: {
    reserved_output_tokens?: number;
    available_input_tokens?: number;
    within_context_window?: boolean;
    budget_policy?: Record<string, string>;
  };
  tool_calls?: ToolCallTrace[];
};

type AgentTraceHistoryResponse = {
  runs: AgentTrace[];
};

type AgentTraceDetailResponse = {
  trace: AgentTrace;
};

type ProjectWorkspace = {
  project_id: string;
  name: string;
  status: string;
  output_roots?: {
    audio?: string;
    exports?: string;
  };
  updated_at?: string;
};

type QualitySummary = Record<
  | "unsegmented"
  | "unselected_role"
  | "undubbed"
  | "dubbing_failed"
  | "long_utterance"
  | "duplicate_voice"
  | "role_without_voice"
  | "needs_human_review",
  number
>;

type QualityIssue = {
  issue_id: string;
  issue_type: keyof QualitySummary;
  severity: string;
  chapter_id?: string;
  paragraph_id?: string;
  utterance_id?: string;
  role_id?: string;
  message: string;
  actions?: string[];
};

type QualityCheckResponse = {
  project_id: string;
  summary: QualitySummary;
  issues: QualityIssue[];
  can_generate: boolean;
  can_export: boolean;
};

type ReviewQueueResponse = {
  project_id: string;
  items: QualityIssue[];
  total_count: number;
  filters?: Record<string, string>;
};

type StoryBibleFact = {
  fact_id: string;
  project_id: string;
  subject: string;
  predicate: string;
  object: string;
  confidence:
    | "model_suggested"
    | "user_confirmed"
    | "system_verified"
    | "rejected"
    | string;
  source_id?: string;
  source_type?: string;
  writer?: string;
  notes?: string;
  metadata?: Record<string, unknown>;
  updated_at?: string;
};

type StoryBibleResponse = {
  project_id: string;
  facts: StoryBibleFact[];
};

type StoryMemoryContextResponse = {
  project_id: string;
  query: string;
  facts_for_prompt: StoryBibleFact[];
  candidate_facts: StoryBibleFact[];
  rejected_facts: StoryBibleFact[];
  policy?: Record<string, unknown>;
};

type PlannerStep = {
  step_id: string;
  title: string;
  status: string;
  kind?: string;
  rationale?: string;
  tool_call?: {
    tool_name?: string;
    arguments?: Record<string, unknown>;
  } | null;
  tool_result?: {
    status?: string;
    failure?: string | null;
    output_summary?: string;
  };
};

type PlannerRun = {
  run_id: string;
  project_id: string;
  chapter_id?: string;
  status: string;
  current_goal: string;
  steps: PlannerStep[];
  recovery_suggestions?: {
    step_id?: string;
    title?: string;
    message?: string;
  }[];
};

type PlannerRunResponse = {
  project_id: string;
  planner_run: PlannerRun;
  review?: {
    status: string;
    remaining_issues: {
      failed_step_id?: string;
      title?: string;
      message?: string;
      recovery_action?: string;
    }[];
  };
};

type UtteranceEditResponse = {
  project_id: string;
  utterances_by_paragraph: Record<string, ApiUtterance[]>;
  retry_items?: { paragraph_id: string; utterance_id: string }[];
  updated_count?: number;
  split_report?: {
    source_utterance_id?: string;
    paragraph_id?: string;
    segment_count?: number;
  };
  merge_report?: { target_utterance_id?: string };
};

type ProjectQualityPayload = {
  chapters: {
    chapter_id: string;
    title: string;
    paragraphs: { paragraph_id: string; text: string }[];
  }[];
  roles: Record<string, unknown>[];
  utterances_by_paragraph: Record<string, Record<string, unknown>[]>;
  max_utterance_chars: number;
  filters?: Record<string, string>;
};

type ExportOptions = (typeof EXPORT_PRESETS)[ExportPreset];

type BatchDubbingStatusPayload = {
  success_count: number;
  skipped_count: number;
  failed_count: number;
  groups: { voice_resource_id: string; count: number }[];
  errors?: { statement_id: string; message: string }[];
};

export type ParagraphDubbingStatus =
  "unsegmented" | "unselected-role" | "undubbed" | "dubbed" | "failed";

type ParagraphStatusUtterance = {
  roleId?: string | null;
  audioUrl?: string;
  audioPath?: string;
  audioError?: string | null;
  audioStatus?: string;
};

type ParagraphStatusItem = {
  paragraphId: string;
  text: string;
  status: ParagraphDubbingStatus;
  label: string;
  firstUtteranceId: string;
};

type ModelConfig = {
  text_model: {
    base_url: string;
    model: string;
    has_api_key: boolean;
  };
  tts: {
    base_url: string;
    model_path: string;
    voice_design_model_path: string;
  };
};

type ConnectionTestResponse = {
  message: string;
  progress?: number;
};

type ModelApisTestResponse = {
  message: string;
  models?: {
    text_model?: { ok: boolean; message: string };
    tts?: { ok: boolean; message: string };
  };
};

type TtsDeploymentStatus = {
  status: "idle" | "running" | "succeeded" | "failed";
  stage: string;
  progress: number;
  message: string;
  can_retry?: boolean;
  error?: string | null;
  pid?: number | null;
  health?: Record<string, unknown> | null;
  model_path?: string;
  voice_design_model_path?: string;
};

const MAX_NOVEL_PREVIEW_CHARS = 700;
const DEFAULT_GENERATED_VOICE_TEXT = "这是一段用于试听新音色的语音。";
const DEFAULT_BASE_MODEL_PATH = "/models/Qwen3-TTS-12Hz-1.7B-Base";
const DEFAULT_VOICE_DESIGN_MODEL_PATH =
  "/models/Qwen3-TTS-12Hz-1.7B-VoiceDesign";

const defaultVoices: VoiceResource[] = [];

const PARAGRAPH_STATUS_META: Record<ParagraphDubbingStatus, { label: string }> =
  {
    unsegmented: { label: "未划分" },
    "unselected-role": { label: "未选角色" },
    undubbed: { label: "未配音" },
    dubbed: { label: "已配音" },
    failed: { label: "失败" },
  };

const PARAGRAPH_STATUS_FILTERS: ParagraphDubbingStatus[] = [
  "unsegmented",
  "unselected-role",
  "undubbed",
  "failed",
];

const defaultModelConfig: ModelConfig = {
  text_model: {
    base_url: "",
    model: "",
    has_api_key: false,
  },
  tts: {
    base_url: "http://127.0.0.1:7811",
    model_path: DEFAULT_BASE_MODEL_PATH,
    voice_design_model_path: DEFAULT_VOICE_DESIGN_MODEL_PATH,
  },
};

const defaultTtsDeployment: TtsDeploymentStatus = {
  status: "idle",
  stage: "idle",
  progress: 0,
  message: "尚未下载并部署 TTS 模型。",
  can_retry: false,
  error: null,
  pid: null,
  health: null,
  model_path: DEFAULT_BASE_MODEL_PATH,
  voice_design_model_path: DEFAULT_VOICE_DESIGN_MODEL_PATH,
};

const PROJECT_STORAGE_KEY = "shuyi-agent.recent-projects.v0.6.1";

const defaultQualitySummary: QualitySummary = {
  unsegmented: 0,
  unselected_role: 0,
  undubbed: 0,
  dubbing_failed: 0,
  long_utterance: 0,
  duplicate_voice: 0,
  role_without_voice: 0,
  needs_human_review: 0,
};

const QUALITY_LABELS: Record<keyof QualitySummary, string> = {
  unsegmented: "未划分",
  unselected_role: "未选角色",
  undubbed: "未配音",
  dubbing_failed: "配音失败",
  long_utterance: "超长台词",
  duplicate_voice: "重复音色",
  role_without_voice: "角色无音色",
  needs_human_review: "needs_human_review",
};

const QUALITY_SUMMARY_KEYS = Object.keys(
  defaultQualitySummary,
) as (keyof QualitySummary)[];

const BLOCKER_RECOMMENDATIONS: Record<keyof QualitySummary, string> = {
  unsegmented: "先补齐章节段落与台词划分",
  unselected_role: "为台词选择明确角色后再继续",
  undubbed: "批量生成或重试缺失配音",
  dubbing_failed: "查看失败原因，修复后加入重试队列",
  long_utterance: "拆分超长台词并校验文本守恒",
  duplicate_voice: "调整重复音色，避免角色混淆",
  role_without_voice: "为角色绑定或生成音色",
  needs_human_review: "人工确认低置信度角色或台词",
};

const EXPORT_PRESETS: Record<
  ExportPreset,
  {
    label: string;
    description: string;
    pauseMs: number;
    speed: number;
    trimSilence: boolean;
    normalizeAudio: boolean;
    targetPeak: number;
    exportFormats: ("wav" | "mp3")[];
  }
> = {
  preview: {
    label: "试听版",
    description: "停顿短、保留 WAV，适合快速听审。",
    pauseMs: 180,
    speed: 1.0,
    trimSilence: false,
    normalizeAudio: false,
    targetPeak: 0.9,
    exportFormats: ["wav"],
  },
  delivery: {
    label: "交付版",
    description: "默认片段停顿、头尾静音裁剪和响度归一化。",
    pauseMs: 300,
    speed: 1.0,
    trimSilence: true,
    normalizeAudio: true,
    targetPeak: 0.9,
    exportFormats: ["wav", "mp3"],
  },
  post: {
    label: "后期版",
    description: "停顿更长，导出 WAV/MP3，便于剪辑后期处理。",
    pauseMs: 500,
    speed: 1.0,
    trimSilence: true,
    normalizeAudio: true,
    targetPeak: 0.86,
    exportFormats: ["wav", "mp3"],
  },
};

function initialPageFromUrl(): Page {
  const page = new URLSearchParams(window.location.search).get("page");
  return page === "voices" ||
    page === "memory" ||
    page === "models" ||
    page === "agent-runs"
    ? page
    : "main";
}

function makeNovelPreview(text: string): string {
  const trimmed = text.trimStart();
  if (trimmed.length <= MAX_NOVEL_PREVIEW_CHARS) return trimmed;
  return `${trimmed.slice(0, MAX_NOVEL_PREVIEW_CHARS)}\n\n……仅展示开头预览，完整小说已保留用于小说格式解析。`;
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return window.btoa(binary);
}

async function decodeNovelTextFile(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  return decodeNovelTextBuffer(buffer);
}

function decodeNovelTextBuffer(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    const legacyChineseDecoders = [
      new TextDecoder("gb18030"),
      new TextDecoder("gbk"),
      new TextDecoder("big5"),
    ];
    for (const decoder of legacyChineseDecoders) {
      try {
        return decoder.decode(bytes);
      } catch {
        // 继续尝试浏览器支持的下一种中文编码。
      }
    }
  }
  return new TextDecoder("utf-8").decode(bytes);
}

async function readNovelFileUpload(file: File): Promise<NovelFileUpload> {
  const buffer = await file.arrayBuffer();
  const isEpub =
    file.name.toLowerCase().endsWith(".epub") ||
    file.type === "application/epub+zip";
  if (isEpub) {
    return {
      text: "",
      preview: `已上传 EPUB：${file.name}\n\n点击“文档解析”后将由后端解析 EPUB 目录和正文。`,
      uploadedFile: {
        filename: file.name,
        contentBase64: arrayBufferToBase64(buffer),
        kind: "epub",
      },
    };
  }
  const text = decodeNovelTextBuffer(buffer);
  return { text, preview: makeNovelPreview(text), uploadedFile: null };
}

function findChapterHeadingMatches(text: string): ChapterHeadingMatch[] {
  const headingPatterns = [
    /^[ \t]*((?:第[一二三四五六七八九十百千万零〇两\d]+[章节回][^\n\r]{0,80}))\r?$/gm,
    /^[ \t]*((?:第[一二三四五六七八九十百千万零〇两\d]+[卷部篇][ \t　]+[^\n\r]{1,80}))\r?$/gm,
    /^[ \t]*(\d{1,4}[.．、](?!\d|[0-9]*[%％])[^\n\r]{0,60})\r?$/gm,
  ];
  const candidates: ChapterHeadingMatch[][] = [];
  for (const pattern of headingPatterns) {
    const matches = Array.from(text.matchAll(pattern)).map((match) => ({
      index: match.index ?? 0,
      text: match[0],
      title: match[1].trim(),
    }));
    if (matches.length > 0) candidates.push(matches);
  }
  return (
    candidates.sort((left, right) =>
      compareChapterHeadingMatches(text, right, left),
    )[0] ?? []
  );
}

function compareChapterHeadingMatches(
  text: string,
  left: ChapterHeadingMatch[],
  right: ChapterHeadingMatch[],
): number {
  const leftScore = chapterHeadingScore(text, left);
  const rightScore = chapterHeadingScore(text, right);
  return (
    leftScore[0] - rightScore[0] ||
    leftScore[1] - rightScore[1] ||
    leftScore[2] - rightScore[2]
  );
}

function chapterHeadingScore(
  text: string,
  matches: ChapterHeadingMatch[],
): [number, number, number] {
  const nonEmptyBodies = matches.filter((match, index) => {
    const next = matches[index + 1];
    const body = text
      .slice(match.index + match.text.length, next?.index ?? text.length)
      .trim();
    return body.length > 0;
  }).length;
  const firstIndex = matches[0]?.index ?? text.length;
  return [nonEmptyBodies, matches.length, -firstIndex];
}

function parseChapters(text: string): Chapter[] {
  const matches = findChapterHeadingMatches(text);
  if (matches.length === 0) {
    return text.trim()
      ? [{ chapterId: "chapter-0001", title: "未分章正文", body: text.trim() }]
      : [];
  }
  return matches.map((match, index) => {
    const next = matches[index + 1];
    const bodyStart = match.index + match.text.length;
    const bodyEnd = next?.index ?? text.length;
    return {
      chapterId: `chapter-${String(index + 1).padStart(4, "0")}`,
      title: match.title,
      body: text
        .slice(bodyStart, bodyEnd)
        .replace(/^-{3,}\s*/, "")
        .trim(),
    };
  });
}

function parseChapterIndex(text: string): Chapter[] {
  const matches = findChapterHeadingMatches(text);
  if (matches.length === 0) {
    const stripped = text.trim();
    return stripped
      ? [
          {
            chapterId: "chapter-0001",
            title: "未分章正文",
            body: "",
            bodyStart: 0,
            bodyEnd: text.length,
          },
        ]
      : [];
  }
  return matches.map((match, index) => {
    const next = matches[index + 1];
    return {
      chapterId: `chapter-${String(index + 1).padStart(4, "0")}`,
      title: match.title,
      body: "",
      bodyStart: match.index + match.text.length,
      bodyEnd: next?.index ?? text.length,
    };
  });
}

function extractChapterBody(text: string, chapter: Chapter): string {
  if (chapter.body) return chapter.body;
  const body = text.slice(
    chapter.bodyStart ?? 0,
    chapter.bodyEnd ?? text.length,
  );
  return body.replace(/^-{3,}\s*/, "").trim();
}

function paragraphsFromChapter(chapter: Chapter): ParagraphModule[] {
  return chapter.body
    .split(/\n\s*\n+/)
    .map((text, index) => ({
      paragraphId: `p-${String(index + 1).padStart(4, "0")}`,
      text: text.trim(),
      collapsed: false,
      deleted: false,
    }))
    .filter((paragraph) => paragraph.text);
}

function fromApiChapter(chapter: ApiChapter): Chapter {
  return {
    chapterId: chapter.chapter_id,
    title: chapter.title,
    body: chapter.body,
  };
}

function fromApiParagraph(paragraph: ApiParagraph): ParagraphModule {
  return {
    paragraphId: paragraph.paragraph_id,
    text: paragraph.text,
    collapsed: paragraph.collapsed,
    deleted: paragraph.deleted,
  };
}

function fromApiVoice(voice: ApiVoiceResource): VoiceResource {
  return {
    voiceId: voice.voice_id,
    name: voice.name,
    gender: voice.gender ?? "",
    description: voice.description,
    suitableRoleTypes: voice.suitable_role_types ?? [],
    referenceText: voice.reference_text,
    referenceAudioPath: voice.reference_audio_path,
    playableAudioPath: voice.playable_audio_path ?? voice.reference_audio_path,
    generated: voice.generated,
  };
}

function fromApiRole(role: ApiRoleCard): RoleCard {
  return {
    roleId: role.role_id,
    name: role.name,
    aliases: role.aliases ?? [],
    gender: role.gender ?? "",
    profile: role.profile ?? "",
    description: role.description,
    voiceMode: role.voice_mode,
    voiceResourceId: role.voice_resource_id ?? "",
    referenceAudioPath: role.reference_audio_path ?? "",
    referenceText: role.reference_text ?? "",
    designPrompt: role.design_prompt ?? "",
    voiceDescription: role.voice_description ?? role.description,
    voiceSampleText: role.voice_sample_text ?? role.reference_text ?? "",
    playableVoicePath:
      role.playable_voice_path ?? role.reference_audio_path ?? "",
    voiceMatchScore: role.voice_match_score,
    voiceMatchReason: role.voice_match_reason,
    voiceGeneratedByAi: Boolean(role.voice_generated_by_ai),
  };
}

function toApiVoice(
  voice: Omit<Partial<VoiceResource>, "suitableRoleTypes"> & {
    suitableRoleTypes?: string[] | string;
  },
): Record<string, unknown> {
  return {
    voice_id: voice.voiceId,
    name: voice.name,
    gender: voice.gender,
    description: voice.description,
    suitable_role_types: Array.isArray(voice.suitableRoleTypes)
      ? voice.suitableRoleTypes
      : String(voice.suitableRoleTypes ?? "")
          .split(/[，,、]/)
          .map((item) => item.trim())
          .filter(Boolean),
    reference_text: voice.referenceText,
    reference_audio_path: voice.referenceAudioPath,
    playable_audio_path: voice.playableAudioPath,
    generated: voice.generated,
  };
}

function toApiRole(role: RoleCard): Record<string, unknown> {
  return {
    role_id: role.roleId,
    name: role.name,
    aliases: role.aliases,
    gender: role.gender || null,
    profile: role.profile || null,
    description: role.description,
    voice_mode: role.voiceMode,
    voice_resource_id: role.voiceResourceId,
    reference_audio_path: role.referenceAudioPath,
    reference_text: role.referenceText,
    design_prompt: role.designPrompt || null,
    voice_description: role.voiceDescription,
    voice_sample_text: role.voiceSampleText,
    playable_voice_path: role.playableVoicePath,
    voice_match_score: role.voiceMatchScore,
    voice_match_reason: role.voiceMatchReason,
    voice_generated_by_ai: role.voiceGeneratedByAi,
  };
}

function utteranceGroupsToApi(
  groups: Record<string, UtteranceDraft[]>,
): Record<string, Record<string, unknown>[]> {
  return Object.fromEntries(
    Object.entries(groups).map(([paragraphId, utterances]) => [
      paragraphId,
      utterances.map((utterance) => ({
        utterance_id: utterance.utteranceId,
        paragraph_id: paragraphId,
        text: utterance.text,
        speaker_name: utterance.speakerName,
        speaker_role_id: utterance.roleId || null,
        voice_mode: "voice_cloning",
        emotion: "neutral",
        speed: 1.0,
        volume: 1.0,
        design_prompt: null,
        audio_status: utterance.audioPath
          ? "success"
          : utterance.audioError
            ? "failed"
            : undefined,
        audio_path: utterance.audioPath,
        audio_duration: utterance.audioDuration,
        audio_provider: utterance.audioProvider,
        audio_model: utterance.audioModel,
        audio_error: utterance.audioError,
        needs_human_review: utterance.needsHumanReview,
      })),
    ]),
  );
}

function voiceAudioSrc(voice: VoiceResource): string {
  return runtimeConfig.apiUrl(`/voice-profiles/${voice.voiceId}/audio`);
}

function roleFromVoice(
  roleId: string,
  name: string,
  voice: VoiceResource,
): RoleCard {
  return {
    roleId,
    name,
    aliases: [],
    gender: voice.gender,
    profile: voice.description,
    description: voice.description,
    voiceMode: "voice_cloning",
    voiceResourceId: voice.voiceId,
    referenceAudioPath: voice.referenceAudioPath,
    referenceText: voice.referenceText,
    designPrompt: "",
    voiceDescription: voice.description,
    voiceSampleText: voice.referenceText,
    playableVoicePath: voice.playableAudioPath || voice.referenceAudioPath,
    voiceMatchScore: null,
    voiceMatchReason: "用户手动选择音色",
    voiceGeneratedByAi: voice.generated,
  };
}

function createDefaultRoles(_voices: VoiceResource[]): RoleCard[] {
  return [];
}

function createBlankRole(roleId: string, name: string): RoleCard {
  return {
    roleId,
    name,
    aliases: [],
    gender: "",
    profile: "",
    description: "",
    voiceMode: "voice_design",
    voiceResourceId: "",
    referenceAudioPath: "",
    referenceText: "",
    designPrompt: "",
    voiceDescription: "",
    voiceSampleText: "",
    playableVoicePath: "",
    voiceMatchScore: null,
    voiceMatchReason: "用户手动创建",
    voiceGeneratedByAi: false,
  };
}

async function fetchApi(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(runtimeConfig.apiUrl(path), init);
  } catch {
    throw new ApiRequestError(0, "后端不可连接");
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const isMultipart = init?.body instanceof FormData;
  const response = await fetchApi(path, {
    ...init,
    headers: {
      ...(isMultipart ? {} : { "Content-Type": "application/json" }),
      ...(init?.headers ?? {}),
    },
  });
  let data: any;
  try {
    data = await response.json();
  } catch {
    if (response.ok) throw new ApiRequestError(0, "后端响应不是 JSON API");
    data = {};
  }
  if (!response.ok) {
    throw new ApiRequestError(
      response.status,
      data.detail ?? data.error ?? response.statusText,
    );
  }
  return data as T;
}

type SecretExchangePayload = {
  secret_id: string;
  ciphertext_b64: string;
  length: number;
};

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return window.btoa(binary);
}

function base64ToBytes(value: string): Uint8Array {
  return Uint8Array.from(window.atob(value), (character) =>
    character.charCodeAt(0),
  );
}

async function createSecretExchangePayload(
  secret: string,
): Promise<SecretExchangePayload | null> {
  const trimmed = secret.trim();
  if (!trimmed) return null;
  const secretBytes = new TextEncoder().encode(trimmed);
  const challenge = await requestJson<{ secret_id: string; pad_b64: string }>(
    "/model-config/secret-exchange",
    {
      method: "POST",
      body: JSON.stringify({ byte_length: Math.max(128, secretBytes.length) }),
    },
  );
  const pad = base64ToBytes(challenge.pad_b64);
  const cipher = secretBytes.map((value, index) => value ^ pad[index]);
  return {
    secret_id: challenge.secret_id,
    ciphertext_b64: bytesToBase64(cipher),
    length: secretBytes.length,
  };
}

function mediaRequestUrl(source: string): string {
  if (/^(blob:|data:)/.test(source)) return source;
  if (source.startsWith("/outputs/") || source.startsWith("outputs/")) {
    return runtimeConfig.mediaUrl(source);
  }
  if (source.startsWith("/api/")) return runtimeConfig.mediaUrl(source);
  return /^https?:\/\//.test(source) ? source : runtimeConfig.apiUrl(source);
}

type AgentStreamEvent = { id: number; event: string; data: any };

export function parseAgentSseBuffer(buffer: string): {
  events: AgentStreamEvent[];
  remainder: string;
} {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const frames = normalized.split("\n\n");
  const remainder = frames.pop() ?? "";
  const events: AgentStreamEvent[] = [];
  for (const frame of frames) {
    if (!frame.trim()) continue;
    let id = 0;
    let event = "message";
    const dataLines: string[] = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith("id:")) id = Number(line.slice(3).trim()) || 0;
      else if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:"))
        dataLines.push(line.slice(5).trimStart());
    }
    if (dataLines.length) {
      events.push({ id, event, data: JSON.parse(dataLines.join("\n")) });
    }
  }
  return { events, remainder };
}

function AuthorizedAudio({ source }: { source: string }) {
  const [playableUrl, setPlayableUrl] = useState("");

  useEffect(() => {
    if (!source) return undefined;
    if (/^(blob:|data:)/.test(source)) {
      setPlayableUrl(source);
      return undefined;
    }
    let revokedUrl = "";
    let cancelled = false;
    fetch(mediaRequestUrl(source))
      .then((response) => {
        if (!response.ok) throw new Error(`音频读取失败：${response.status}`);
        return response.blob();
      })
      .then((blob) => {
        if (cancelled) return;
        revokedUrl = URL.createObjectURL(blob);
        setPlayableUrl(revokedUrl);
      })
      .catch(() => setPlayableUrl(""));
    return () => {
      cancelled = true;
      if (revokedUrl) URL.revokeObjectURL(revokedUrl);
    };
  }, [source]);

  return playableUrl ? (
    <audio controls src={playableUrl} />
  ) : (
    <small>音频暂不可用</small>
  );
}

function makeUtteranceDraft(paragraph: ParagraphModule): UtteranceDraft {
  return {
    utteranceId: `${paragraph.paragraphId}-u-001`,
    paragraphId: paragraph.paragraphId,
    text: paragraph.text,
    roleId: "",
    speakerName: "",
    audioStatus: "尚未生成",
    needsHumanReview: true,
  };
}

function makeWholeParagraphUtteranceGroups(
  paragraphs: ParagraphModule[],
): Record<string, UtteranceDraft[]> {
  return Object.fromEntries(
    paragraphs.map((paragraph) => [
      paragraph.paragraphId,
      [makeUtteranceDraft(paragraph)],
    ]),
  );
}

function apiUtterancesToGroups(
  groups: Record<string, ApiUtterance[]>,
  paragraphs: ParagraphModule[],
  roles: RoleCard[],
): Record<string, UtteranceDraft[]> {
  return Object.fromEntries(
    Object.entries(groups).map(([paragraphId, utterances]) => {
      const paragraph = paragraphs.find(
        (item) => item.paragraphId === paragraphId,
      ) ?? {
        paragraphId,
        text: "",
        collapsed: false,
        deleted: false,
      };
      return [
        paragraphId,
        utterances.map((utterance) =>
          fromApiUtterance(utterance, paragraph, roles),
        ),
      ];
    }),
  );
}

function audioPathToUrl(path?: string): string | undefined {
  if (!path) return undefined;
  if (path.startsWith("/outputs/")) return path;
  if (path.startsWith("outputs/")) return `/${path}`;
  const marker = "/outputs/";
  const index = path.indexOf(marker);
  return index >= 0 ? path.slice(index) : undefined;
}

function utteranceAudioSource(
  utterance: Pick<UtteranceDraft, "audioUrl" | "audioPath">,
): string | undefined {
  return utterance.audioUrl ?? audioPathToUrl(utterance.audioPath);
}

export function paragraphDubbingStatus(
  utterances: ParagraphStatusUtterance[] | undefined,
): ParagraphDubbingStatus {
  const list = utterances ?? [];
  if (list.length === 0) return "unsegmented";
  if (
    list.some(
      (utterance) =>
        Boolean(utterance.audioError) ||
        String(utterance.audioStatus ?? "").includes("音频生成失败"),
    )
  ) {
    return "failed";
  }
  if (list.some((utterance) => !utterance.roleId)) return "unselected-role";
  if (list.some((utterance) => !utteranceAudioSource(utterance)))
    return "undubbed";
  return "dubbed";
}

function fromApiUtterance(
  utterance: ApiUtterance,
  paragraph: ParagraphModule,
  roles: RoleCard[],
): UtteranceDraft {
  const role = roles.find((item) => item.roleId === utterance.speaker_role_id);
  const audioUrl = utterance.audio_url ?? audioPathToUrl(utterance.audio_path);
  const audioStatus =
    utterance.audio_status === "success"
      ? "音频生成完成"
      : utterance.audio_status === "failed"
        ? `音频生成失败：${utterance.audio_error || "请拆分台词生成后重试"}`
        : "尚未生成";
  return {
    utteranceId: utterance.utterance_id,
    paragraphId: utterance.paragraph_id ?? paragraph.paragraphId,
    text: utterance.text,
    roleId: role?.roleId ?? utterance.speaker_role_id ?? "",
    speakerName: utterance.speaker_name || role?.name || "",
    audioStatus,
    audioUrl,
    audioPath: utterance.audio_path,
    audioDuration: utterance.audio_duration,
    audioProvider: utterance.audio_provider,
    audioModel: utterance.audio_model,
    audioError: utterance.audio_error,
    needsHumanReview: Boolean(utterance.needs_human_review),
  };
}

function mergeApiAudioByUtteranceId(
  current: Record<string, UtteranceDraft[]>,
  groups: Record<string, ApiUtterance[]>,
  paragraphs: ParagraphModule[],
  roles: RoleCard[],
): Record<string, UtteranceDraft[]> {
  const incomingGroups = apiUtterancesToGroups(groups, paragraphs, roles);
  const incomingById = new Map(
    Object.values(incomingGroups)
      .flat()
      .map((utterance) => [utterance.utteranceId, utterance]),
  );
  if (Object.keys(current).length === 0) return incomingGroups;

  const merged: Record<string, UtteranceDraft[]> = {};
  for (const [paragraphId, utterances] of Object.entries(current)) {
    const knownIds = new Set(
      utterances.map((utterance) => utterance.utteranceId),
    );
    const additions = (incomingGroups[paragraphId] ?? []).filter(
      (utterance) => !knownIds.has(utterance.utteranceId),
    );
    merged[paragraphId] = [...utterances, ...additions].map((utterance) => {
      const incoming = incomingById.get(utterance.utteranceId);
      if (!incoming) return utterance;
      return {
        ...utterance,
        audioStatus: incoming.audioStatus,
        audioUrl: incoming.audioUrl,
        audioPath: incoming.audioPath,
        audioDuration: incoming.audioDuration,
        audioProvider: incoming.audioProvider,
        audioModel: incoming.audioModel,
        audioError: incoming.audioError,
      };
    });
  }
  return merged;
}

function fromApiUtteranceEditGroups(
  groups: Record<string, ApiUtterance[]>,
  paragraphs: ParagraphModule[],
  roles: RoleCard[],
): Record<string, UtteranceDraft[]> {
  return apiUtterancesToGroups(groups, paragraphs, roles);
}

function splitRetryUtterances(
  groups: Record<string, UtteranceDraft[]>,
  sourceUtteranceId: string,
  paragraphId?: string,
): UtteranceDraft[] {
  const candidates = paragraphId
    ? groups[paragraphId] ?? []
    : Object.values(groups).flat();
  const splitPrefix = `${sourceUtteranceId}-s`;
  return candidates.filter(
    (utterance) =>
      utterance.utteranceId === sourceUtteranceId ||
      utterance.utteranceId.startsWith(splitPrefix),
  );
}

function normalizeModelConfig(
  config: Partial<ModelConfig> & {
    llm?: Partial<ModelConfig["text_model"]>;
    chapter_agent?: Partial<ModelConfig["text_model"]>;
  },
): ModelConfig {
  const textModel =
    config.text_model ?? config.chapter_agent ?? config.llm ?? {};
  return {
    text_model: {
      base_url: textModel.base_url ?? defaultModelConfig.text_model.base_url,
      model: textModel.model ?? defaultModelConfig.text_model.model,
      has_api_key: textModel.has_api_key ?? false,
    },
    tts: {
      base_url: config.tts?.base_url ?? defaultModelConfig.tts.base_url,
      model_path: config.tts?.model_path ?? defaultModelConfig.tts.model_path,
      voice_design_model_path:
        config.tts?.voice_design_model_path ??
        defaultModelConfig.tts.voice_design_model_path,
    },
  };
}

function normalizeTtsDeployment(
  status: Partial<TtsDeploymentStatus> | null | undefined,
): TtsDeploymentStatus {
  return {
    ...defaultTtsDeployment,
    ...(status ?? {}),
    progress: Number.isFinite(status?.progress)
      ? Number(status?.progress)
      : defaultTtsDeployment.progress,
  };
}

function ProgressBar({ label, value }: { label: string; value: number }) {
  const normalized = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div className="progress-block">
      <div className="progress-label">
        <span>{label}</span>
        <span>{normalized}%</span>
      </div>
      <div
        className="progress-bar"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={normalized}
      >
        <span style={{ width: `${normalized}%` }} />
      </div>
    </div>
  );
}

function formatTraceJson(value: unknown): string {
  if (value === undefined || value === null || value === "") return "暂无记录";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

function formatTraceTimestamp(value?: string): string {
  if (!value) return "未记录";
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp)
    ? value
    : new Date(timestamp).toLocaleString("zh-CN");
}

function projectStorage(): Storage | null {
  if (typeof window === "undefined" || !("localStorage" in window)) return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function readRecentProjectIds(): string[] {
  const storage = projectStorage();
  if (!storage) return [];
  try {
    const value = JSON.parse(storage.getItem(PROJECT_STORAGE_KEY) ?? "[]");
    return Array.isArray(value)
      ? value.filter((item): item is string => typeof item === "string")
      : [];
  } catch {
    return [];
  }
}

function writeRecentProjectIds(projectIds: string[]) {
  const storage = projectStorage();
  if (!storage) return;
  storage.setItem(PROJECT_STORAGE_KEY, JSON.stringify(projectIds.slice(0, 8)));
}

function rememberRecentProject(projectId: string) {
  if (!projectId) return;
  writeRecentProjectIds([
    projectId,
    ...readRecentProjectIds().filter((item) => item !== projectId),
  ]);
}

function forgetRecentProject(projectId: string) {
  writeRecentProjectIds(
    readRecentProjectIds().filter((item) => item !== projectId),
  );
}

function sortProjectsByRecent(
  projects: ProjectWorkspace[],
): ProjectWorkspace[] {
  const recentIds = readRecentProjectIds();
  return [...projects].sort((left, right) => {
    const leftIndex = recentIds.indexOf(left.project_id);
    const rightIndex = recentIds.indexOf(right.project_id);
    const leftRank = leftIndex === -1 ? Number.MAX_SAFE_INTEGER : leftIndex;
    const rightRank = rightIndex === -1 ? Number.MAX_SAFE_INTEGER : rightIndex;
    return (
      leftRank - rightRank ||
      String(right.updated_at ?? "").localeCompare(
        String(left.updated_at ?? ""),
      )
    );
  });
}

function App() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const voiceAudioInputRef = useRef<HTMLInputElement>(null);
  const fullNovelTextRef = useRef("");
  const uploadedNovelFileRef = useRef<UploadedNovelFile | null>(null);
  const automaticDubbingStartedRef = useRef(false);
  const automaticRoleMatchingAttemptedRef = useRef(false);
  const dubbingInFlightRef = useRef(false);
  const dubbingQueueRef = useRef(Promise.resolve());
  const queuedUtteranceIdsRef = useRef<Set<string>>(new Set());
  const chapterPlayerRef = useRef<HTMLAudioElement>(null);
  const chapterPlaybackQueueRef = useRef<UtteranceDraft[]>([]);
  const chapterPlaybackIndexRef = useRef(0);
  const [page, setPage] = useState<Page>(() => initialPageFromUrl());
  const [novelPreview, setNovelPreview] = useState("");
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [activeChapterId, setActiveChapterId] = useState("");
  const [paragraphs, setParagraphs] = useState<ParagraphModule[]>([]);
  const [chapterSidebarCollapsed, setChapterSidebarCollapsed] = useState(false);
  const [hasSplitChapters, setHasSplitChapters] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [voices, setVoices] = useState<VoiceResource[]>(defaultVoices);
  const [roles, setRoles] = useState<RoleCard[]>([]);
  const [utterancesByParagraph, setUtterancesByParagraph] = useState<
    Record<string, UtteranceDraft[]>
  >({});
  const [chapterBackendSynced, setChapterBackendSynced] = useState(false);
  const [selectedVoiceIds, setSelectedVoiceIds] = useState<
    Record<string, boolean>
  >({});
  const [newVoice, setNewVoice] = useState({
    name: "",
    gender: "",
    description: "",
    suitableRoleTypes: "",
    referenceText: "",
    referenceAudioPath: "",
    playableAudioPath: "",
  });
  const [generatedVoice, setGeneratedVoice] = useState({
    name: "",
    gender: "",
    description: "",
    suitableRoleTypes: "",
    referenceText: DEFAULT_GENERATED_VOICE_TEXT,
  });
  const [newVoiceAudioPreviewUrl, setNewVoiceAudioPreviewUrl] = useState("");
  const [generatedVoicePreview, setGeneratedVoicePreview] =
    useState<VoiceResource | null>(null);
  const [generatedVoicePreviewUrl, setGeneratedVoicePreviewUrl] = useState("");
  const [modelConfig, setModelConfig] =
    useState<ModelConfig>(defaultModelConfig);
  const [textModelApiKey, setTextModelApiKey] = useState("");
  const [backendApiBase, setBackendApiBase] = useState(
    runtimeConfig.apiBase || "/api/v1",
  );
  const [apiStatus, setApiStatus] = useState("等待上传小说");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [chapterSplitProgress, setChapterSplitProgress] = useState(0);
  const [roleMatchingProgress, setRoleMatchingProgress] = useState(0);
  const [voiceGenerationProgress, setVoiceGenerationProgress] = useState(0);
  const [generatingUtteranceIds, setGeneratingUtteranceIds] = useState<
    Record<string, boolean>
  >({});
  const [highlightUtteranceId, setHighlightUtteranceId] = useState("");
  const [highlightParagraphId, setHighlightParagraphId] = useState("");
  const [activeParagraphStatusFilter, setActiveParagraphStatusFilter] =
    useState<ParagraphDubbingStatus | "">("");
  const [generatedVoiceProgress, setGeneratedVoiceProgress] = useState(0);
  const [localTtsStarting, setLocalTtsStarting] = useState(false);
  const [ttsDeployment, setTtsDeployment] =
    useState<TtsDeploymentStatus>(defaultTtsDeployment);
  const [aiRoleCandidates, setAiRoleCandidates] = useState<AiRoleCandidate[]>(
    [],
  );
  const [agentRunThreadId, setAgentRunThreadId] = useState("");
  const [agentRunWaitingForRoles, setAgentRunWaitingForRoles] = useState(false);
  const [agentRunRunning, setAgentRunRunning] = useState(false);
  const [agentTraces, setAgentTraces] = useState<AgentTrace[]>([]);
  const [selectedAgentTrace, setSelectedAgentTrace] =
    useState<AgentTrace | null>(null);
  const [agentTraceStatus, setAgentTraceStatus] = useState(
    "Run History 会在完成一次 Agent run 后显示。",
  );
  const [projects, setProjects] = useState<ProjectWorkspace[]>([]);
  const [activeProjectId, setActiveProjectId] = useState("default");
  const [newProjectName, setNewProjectName] = useState("");
  const [qualityReport, setQualityReport] = useState<QualityCheckResponse>({
    project_id: "default",
    summary: defaultQualitySummary,
    issues: [],
    can_generate: false,
    can_export: false,
  });
  const [reviewQueue, setReviewQueue] = useState<ReviewQueueResponse>({
    project_id: "default",
    items: [],
    total_count: 0,
  });
  const [qualityStatus, setQualityStatus] =
    useState("制作阻塞项等待当前项目数据。");
  const [bulkRoleTargetId, setBulkRoleTargetId] = useState("");
  const [bulkRolePreviewArmed, setBulkRolePreviewArmed] = useState(false);
  const [plannerGoal, setPlannerGoal] = useState("把当前章节处理到可导出");
  const [plannerRun, setPlannerRun] = useState<PlannerRun | null>(null);
  const [plannerStatus, setPlannerStatus] =
    useState("智能下一步助手会根据当前章节状态给出建议。");
  const [exportPreset, setExportPreset] =
    useState<ExportPreset>("delivery");
  const [exportOptions, setExportOptions] = useState<ExportOptions>(
    EXPORT_PRESETS.delivery,
  );
  const [storyBibleFacts, setStoryBibleFacts] = useState<StoryBibleFact[]>([]);
  const [memoryContext, setMemoryContext] =
    useState<StoryMemoryContextResponse | null>(null);
  const [memoryQuery, setMemoryQuery] = useState("");
  const [memoryStatus, setMemoryStatus] =
    useState("项目记忆会展示角色证据、设定记忆和用户纠错。");
  const [memoryCorrection, setMemoryCorrection] = useState({
    subject: "",
    predicate: "alias",
    object: "",
    notes: "",
  });
  const [chapterPlaybackState, setChapterPlaybackState] = useState<
    "idle" | "playing" | "paused"
  >("idle");
  const [chapterPlaybackUtteranceId, setChapterPlaybackUtteranceId] =
    useState("");
  const [workflowState, setWorkflowState] = useState(() =>
    createWorkflowState("automatic"),
  );

  const activeChapter = chapters.find(
    (chapter) => chapter.chapterId === activeChapterId,
  );
  const activeProject =
    projects.find((project) => project.project_id === activeProjectId) ??
    projects[0] ??
    null;
  const visibleParagraphs = paragraphs.filter(
    (paragraph) => !paragraph.deleted,
  );
  const flattenedUtterances = useMemo(
    () =>
      visibleParagraphs.flatMap(
        (paragraph) => utterancesByParagraph[paragraph.paragraphId] ?? [],
      ),
    [utterancesByParagraph, visibleParagraphs],
  );
  const paragraphStatusItems = useMemo<ParagraphStatusItem[]>(
    () =>
      visibleParagraphs.map((paragraph) => {
        const utterances = utterancesByParagraph[paragraph.paragraphId] ?? [];
        const status = paragraphDubbingStatus(utterances);
        return {
          paragraphId: paragraph.paragraphId,
          text: paragraph.text,
          status,
          label: PARAGRAPH_STATUS_META[status].label,
          firstUtteranceId: utterances[0]?.utteranceId ?? "",
        };
      }),
    [utterancesByParagraph, visibleParagraphs],
  );
  const paragraphStatusCounts = useMemo<Record<ParagraphDubbingStatus, number>>(
    () =>
      paragraphStatusItems.reduce(
        (counts, item) => ({
          ...counts,
          [item.status]: counts[item.status] + 1,
        }),
        {
          unsegmented: 0,
          "unselected-role": 0,
          undubbed: 0,
          dubbed: 0,
          failed: 0,
        },
      ),
    [paragraphStatusItems],
  );
  const hasPendingHumanReview = flattenedUtterances.some(
    (utterance) =>
      utterance.needsHumanReview || !utterance.roleId || !utterance.text.trim(),
  );
  const hasUnselectedRoleUtterance =
    paragraphStatusCounts["unselected-role"] > 0;
  const hasUngeneratedAudioUtterance = paragraphStatusCounts.undubbed > 0;
  const hasGeneratedAudioUtterance = flattenedUtterances.some((utterance) =>
    Boolean(utteranceAudioSource(utterance)),
  );
  const playableChapterQueue = useMemo(
    () => flattenedUtterances.filter((utterance) => utteranceAudioSource(utterance)),
    [flattenedUtterances],
  );
  const primaryStatementParagraphId = visibleParagraphs[0]?.paragraphId ?? "";
  const roleOptions = useMemo(
    () => roles.map((role) => ({ value: role.roleId, label: role.name })),
    [roles],
  );
  const bulkRoleChangeIds = useMemo(
    () => [
      ...new Set(
        reviewQueue.items
          .filter(
            (item) =>
              item.issue_type === "unselected_role" ||
              item.actions?.includes("change_role"),
          )
          .flatMap((item) => (item.utterance_id ? [item.utterance_id] : [])),
      ),
    ],
    [reviewQueue.items],
  );
  const blockerItems = useMemo(() => {
    const source = reviewQueue.items.length > 0 ? reviewQueue.items : qualityReport.issues;
    const seen = new Set<string>();
    return source.filter((item) => {
      const id = item.issue_id || `${item.issue_type}:${item.utterance_id ?? item.paragraph_id ?? item.role_id ?? item.message}`;
      if (seen.has(id)) return false;
      seen.add(id);
      return true;
    });
  }, [qualityReport.issues, reviewQueue.items]);
  const productionPrimaryAction = useMemo(() => {
    if (!hasSplitChapters) {
      return {
        label: "开始制作",
        detail: novelPreview
          ? "继续解析小说章节，进入制作流程。"
          : "先上传小说，随后解析章节并进入制作流程。",
        disabled: false,
      };
    }
    if (!activeChapter) {
      return {
        label: "继续下一步",
        detail: "请选择一个章节后继续制作。",
        disabled: chapters.length === 0,
      };
    }
    if (blockerItems.length > 0 || hasPendingHumanReview) {
      return {
        label: "处理阻塞项",
        detail: `当前有 ${Math.max(blockerItems.length, 1)} 个制作阻塞项需要处理。`,
        disabled: false,
      };
    }
    if (roles.length === 0 || flattenedUtterances.length === 0) {
      return {
        label: "开始制作",
        detail: "运行 Agent 生成角色、台词和初始配音编排。",
        disabled: agentRunRunning || visibleParagraphs.length === 0,
      };
    }
    if (agentRunWaitingForRoles && agentRunThreadId) {
      return {
        label: "继续下一步",
        detail: "角色已分析，继续执行配音编排。",
        disabled: agentRunRunning,
      };
    }
    if (!confirmed) {
      return {
        label: "继续下一步",
        detail: "确认已选台词与角色后进入配音生成。",
        disabled: flattenedUtterances.length === 0,
      };
    }
    if (hasUngeneratedAudioUtterance) {
      return {
        label: "继续下一步",
        detail: "批量生成当前章节缺失的配音。",
        disabled: false,
      };
    }
    if (hasGeneratedAudioUtterance) {
      return {
        label: "继续下一步",
        detail: "导出制作包；需要听审时可在高级操作中播放整章。",
        disabled: false,
      };
    }
    return {
      label: "处理阻塞项",
      detail: "先刷新阻塞项，确认当前章节是否可继续。",
      disabled: false,
    };
  }, [
    activeChapter,
    agentRunRunning,
    agentRunThreadId,
    agentRunWaitingForRoles,
    blockerItems.length,
    chapters.length,
    confirmed,
    flattenedUtterances.length,
    hasGeneratedAudioUtterance,
    hasPendingHumanReview,
    hasSplitChapters,
    hasUngeneratedAudioUtterance,
    novelPreview,
    roles.length,
    visibleParagraphs.length,
  ]);

  function resetAgentRunState() {
    setAiRoleCandidates([]);
    setAgentRunThreadId("");
    setAgentRunWaitingForRoles(false);
    setAgentRunRunning(false);
  }

  function projectQualityPayload(
    filters?: Record<string, string>,
  ): ProjectQualityPayload {
    const scopedChapters = activeChapter
      ? [
          {
            chapter_id: activeChapter.chapterId,
            title: activeChapter.title,
            paragraphs: visibleParagraphs.map((paragraph) => ({
              paragraph_id: paragraph.paragraphId,
              text: paragraph.text,
            })),
          },
        ]
      : chapters.map((chapter) => ({
          chapter_id: chapter.chapterId,
          title: chapter.title,
          paragraphs: [],
        }));
    return {
      chapters: scopedChapters,
      roles: roles.map(toApiRole),
      utterances_by_paragraph: utteranceGroupsToApi(utterancesByParagraph),
      max_utterance_chars: 120,
      ...(filters ? { filters } : {}),
    };
  }

  async function loadProjects() {
    setQualityStatus("正在打开最近项目");
    try {
      const data = await requestJson<{ projects: ProjectWorkspace[] }>(
        "/projects",
      );
      const sorted = sortProjectsByRecent(data.projects);
      const recentIds = readRecentProjectIds();
      const preferredProject =
        sorted.find((project) => project.project_id === activeProjectId) ??
        sorted.find((project) => recentIds.includes(project.project_id)) ??
        sorted[0];
      setProjects(sorted);
      if (preferredProject) {
        setActiveProjectId(preferredProject.project_id);
        rememberRecentProject(preferredProject.project_id);
      }
      setQualityStatus(
        preferredProject
          ? `已打开项目：${preferredProject.name}`
          : "暂无项目，请新建项目工作区",
      );
    } catch (error) {
      setQualityStatus(apiFailureMessage("项目工作区载入失败", error));
    }
  }

  async function createProject() {
    const name = newProjectName.trim();
    if (!name) {
      setQualityStatus("请输入项目名称后再新建项目");
      return;
    }
    try {
      const data = await requestJson<{ project: ProjectWorkspace }>(
        "/projects",
        {
          method: "POST",
          body: JSON.stringify({ name }),
        },
      );
      rememberRecentProject(data.project.project_id);
      setProjects((current) =>
        sortProjectsByRecent([
          data.project,
          ...current.filter(
            (project) => project.project_id !== data.project.project_id,
          ),
        ]),
      );
      setActiveProjectId(data.project.project_id);
      setNewProjectName("");
      setQualityReport({
        ...qualityReport,
        project_id: data.project.project_id,
        summary: defaultQualitySummary,
        issues: [],
      });
      setReviewQueue({
        project_id: data.project.project_id,
        items: [],
        total_count: 0,
      });
      setQualityStatus(`项目工作区已创建：${data.project.name}`);
    } catch (error) {
      setQualityStatus(apiFailureMessage("项目创建失败", error));
    }
  }

  async function deleteProject(projectId: string) {
    if (projectId === "default") {
      setQualityStatus("默认项目用于兼容旧数据，不能删除");
      return;
    }
    try {
      await requestJson<{ deleted: boolean }>(
        `/projects/${encodeURIComponent(projectId)}`,
        {
          method: "DELETE",
        },
      );
      forgetRecentProject(projectId);
      setProjects((current) => {
        const remaining = current.filter(
          (project) => project.project_id !== projectId,
        );
        const nextProject = remaining[0] ?? null;
        if (nextProject) {
          setActiveProjectId(nextProject.project_id);
          rememberRecentProject(nextProject.project_id);
        }
        return remaining;
      });
      setQualityStatus("项目工作区已删除");
    } catch (error) {
      setQualityStatus(apiFailureMessage("项目删除失败", error));
    }
  }

  function selectProject(projectId: string) {
    const project = projects.find((item) => item.project_id === projectId);
    if (!project) return;
    rememberRecentProject(projectId);
    setActiveProjectId(projectId);
    setProjects((current) => sortProjectsByRecent(current));
    setQualityReport({
      project_id: projectId,
      summary: defaultQualitySummary,
      issues: [],
      can_generate: false,
      can_export: false,
    });
    setReviewQueue({ project_id: projectId, items: [], total_count: 0 });
    setQualityStatus(`已切换到最近项目：${project.name}`);
  }

  async function runQualityCheck(purpose: "generate" | "export" = "generate") {
    const projectId = activeProject?.project_id ?? activeProjectId;
    setQualityStatus(
      purpose === "export" ? "正在刷新导出阻塞项" : "正在刷新制作阻塞项",
    );
    try {
      const data = await requestJson<QualityCheckResponse>(
        `/projects/${encodeURIComponent(projectId)}/quality-check`,
        {
          method: "POST",
          body: JSON.stringify(projectQualityPayload()),
        },
      );
      setQualityReport(data);
      setQualityStatus(
        purpose === "export"
          ? data.can_export
            ? "导出阻塞项已清空"
            : `导出仍有 ${data.issues.length} 个阻塞项`
          : data.can_generate
            ? "制作阻塞项已清空，可以继续生成"
            : `制作仍有 ${data.issues.length} 个阻塞项`,
      );
      void loadReviewQueue();
    } catch (error) {
      setQualityStatus(apiFailureMessage("制作阻塞项刷新失败", error));
    }
  }

  async function loadReviewQueue(issueType?: keyof QualitySummary) {
    const projectId = activeProject?.project_id ?? activeProjectId;
    try {
      const data = await requestJson<ReviewQueueResponse>(
        `/projects/${encodeURIComponent(projectId)}/review-queue`,
        {
          method: "POST",
          body: JSON.stringify(
            projectQualityPayload(
              issueType ? { issue_type: issueType } : undefined,
            ),
          ),
        },
      );
      setReviewQueue(data);
      if (issueType)
        setQualityStatus(`制作阻塞项已筛选：${QUALITY_LABELS[issueType]}`);
    } catch (error) {
      setQualityStatus(apiFailureMessage("制作阻塞项读取失败", error));
    }
  }

  async function generatePlannerPlan() {
    const goal = plannerGoal.trim();
    if (!goal) {
      setPlannerStatus("请输入制作目标后再生成计划");
      return;
    }
    const projectId = activeProject?.project_id ?? activeProjectId;
    setPlannerStatus("正在生成制作任务计划");
    try {
      const data = await requestJson<PlannerRunResponse>(
        `/projects/${encodeURIComponent(projectId)}/planner/plan`,
        {
          method: "POST",
          body: JSON.stringify({
            goal,
            chapter_id: activeChapterId,
            ...projectQualityPayload(),
          }),
        },
      );
      setPlannerRun(data.planner_run);
      setPlannerStatus(`计划已生成：${data.planner_run.steps.length} 个步骤`);
    } catch (error) {
      setPlannerStatus(apiFailureMessage("Planner 生成计划失败", error));
    }
  }

  async function executePlannerPlan() {
    if (!plannerRun) {
      setPlannerStatus("请先生成计划，再执行 Planner");
      return;
    }
    const projectId = activeProject?.project_id ?? activeProjectId;
    setPlannerStatus("正在执行制作任务计划");
    try {
      const data = await requestJson<PlannerRunResponse>(
        `/projects/${encodeURIComponent(projectId)}/planner/execute`,
        {
          method: "POST",
          body: JSON.stringify({ run_id: plannerRun.run_id }),
        },
      );
      setPlannerRun(data.planner_run);
      setPlannerStatus(`计划执行状态：${data.planner_run.status}`);
    } catch (error) {
      setPlannerStatus(apiFailureMessage("Planner 执行失败", error));
    }
  }

  async function reviewPlannerPlan() {
    if (!plannerRun) {
      setPlannerStatus("请先生成计划，再复盘 Planner");
      return;
    }
    const projectId = activeProject?.project_id ?? activeProjectId;
    setPlannerStatus("正在复盘制作任务计划");
    try {
      const data = await requestJson<PlannerRunResponse>(
        `/projects/${encodeURIComponent(projectId)}/planner/review`,
        {
          method: "POST",
          body: JSON.stringify({ run_id: plannerRun.run_id }),
        },
      );
      setPlannerRun(data.planner_run);
      const issueCount = data.review?.remaining_issues.length ?? 0;
      setPlannerStatus(
        issueCount > 0
          ? `复盘完成：仍有 ${issueCount} 个问题需要人工介入`
          : `复盘完成：${data.review?.status ?? data.planner_run.status}`,
      );
    } catch (error) {
      setPlannerStatus(apiFailureMessage("Planner 复盘失败", error));
    }
  }

  async function refreshProductionAssistant() {
    if (!hasSplitChapters || !activeChapter) {
      setPlannerStatus("智能下一步助手：先上传小说、解析章节并选择当前章节。");
      return;
    }
    if (!plannerRun || plannerRun.chapter_id !== activeChapterId) {
      await generatePlannerPlan();
      return;
    }
    await reviewPlannerPlan();
  }

  async function handleProductionPrimaryAction() {
    if (!hasSplitChapters) {
      if (uploadedNovelFileRef.current || fullNovelTextRef.current.trim()) {
        await runAiChapterSplit();
      } else {
        fileInputRef.current?.click();
        setApiStatus("请选择小说文件，随后点击开始制作继续解析章节");
      }
      return;
    }
    if (!activeChapter) {
      setApiStatus("请先选择一个章节，再继续制作");
      return;
    }
    if (blockerItems.length > 0 || hasPendingHumanReview) {
      await runQualityCheck("generate");
      if (blockerItems[0]) focusQualityIssue(blockerItems[0]);
      return;
    }
    if (roles.length === 0 || flattenedUtterances.length === 0) {
      await runAiRoleAnalysis();
      return;
    }
    if (agentRunWaitingForRoles && agentRunThreadId) {
      await runAiRoleMatching();
      return;
    }
    if (!confirmed) {
      confirmAllReadyUtterances();
      return;
    }
    if (hasUngeneratedAudioUtterance) {
      await generateChapterDubbing();
      return;
    }
    if (hasGeneratedAudioUtterance) {
      await exportChapterAudio();
      return;
    }
    await runQualityCheck("generate");
  }

  function focusQualityIssue(issue: QualityIssue) {
    if (issue.utterance_id) {
      const utterance = flattenedUtterances.find(
        (item) => item.utteranceId === issue.utterance_id,
      );
      if (utterance) {
        focusUtterance(utterance, `已跳转到制作阻塞项问题：${issue.message}`);
        return;
      }
    }
    if (issue.paragraph_id) {
      const item = paragraphStatusItems.find(
        (paragraph) => paragraph.paragraphId === issue.paragraph_id,
      );
      if (item) {
        focusParagraphStatusItem(
          item,
          `已跳转到质量检查问题：${issue.message}`,
        );
        return;
      }
    }
    setQualityStatus(`已定位问题：${issue.message}`);
  }

  function bulkConfirmReviewItems() {
    const reviewIds = new Set(
      reviewQueue.items.map((item) => item.utterance_id).filter(Boolean),
    );
    setUtterancesByParagraph((current) =>
      Object.fromEntries(
        Object.entries(current).map(([paragraphId, utterances]) => [
          paragraphId,
          utterances.map((utterance) =>
            reviewIds.has(utterance.utteranceId)
              ? {
                  ...utterance,
                  needsHumanReview: false,
                  audioStatus: "人工复核已确认",
                }
              : utterance,
          ),
        ]),
      ),
    );
    setQualityStatus(
      `批量确认完成：${reviewIds.size} 条台词已移出 needs_human_review`,
    );
  }

  async function bulkChangeReviewRole() {
    const targetRole = roles.find((role) => role.roleId === bulkRoleTargetId);
    if (!targetRole) {
      setBulkRolePreviewArmed(false);
      setQualityStatus("批量改角色失败：请选择目标角色");
      return;
    }
    if (bulkRoleChangeIds.length === 0) {
      setBulkRolePreviewArmed(false);
      setQualityStatus("制作阻塞项没有可批量改角色的台词");
      return;
    }
    if (!bulkRolePreviewArmed) {
      setBulkRolePreviewArmed(true);
      setQualityStatus(
        `预览影响：${bulkRoleChangeIds.length} 条台词将绑定到 ${targetRole.name}；再次点击确认批量改角色`,
      );
      return;
    }
    const projectId = activeProject?.project_id ?? activeProjectId;
    try {
      const data = await requestJson<UtteranceEditResponse>(
        `/projects/${encodeURIComponent(projectId)}/utterances/bulk-role`,
        {
          method: "POST",
          body: JSON.stringify({
            ...projectQualityPayload(),
            utterance_ids: bulkRoleChangeIds,
            role_id: targetRole.roleId,
            speaker_name: targetRole.name,
          }),
        },
      );
      setUtterancesByParagraph(
        fromApiUtteranceEditGroups(data.utterances_by_paragraph, paragraphs, roles),
      );
      setConfirmed(false);
      setBulkRolePreviewArmed(false);
      setQualityStatus(
        `批量改角色完成：${data.updated_count ?? bulkRoleChangeIds.length} 条台词已绑定到 ${targetRole.name}`,
      );
    } catch (error) {
      setBulkRolePreviewArmed(false);
      setQualityStatus(apiFailureMessage("批量改角色失败", error));
    }
  }

  async function bulkSplitLongUtterances() {
    const longItems = reviewQueue.items.filter(
      (item) => item.issue_type === "long_utterance" && item.utterance_id,
    );
    if (longItems.length === 0) {
      setQualityStatus("制作阻塞项没有可批量拆分的超长台词");
      return;
    }
    let currentGroups = utterancesByParagraph;
    const retryUtterances: UtteranceDraft[] = [];
    const projectId = activeProject?.project_id ?? activeProjectId;
    try {
      for (const item of longItems) {
        const data = await requestJson<UtteranceEditResponse>(
          `/projects/${encodeURIComponent(projectId)}/utterances/${encodeURIComponent(
            item.utterance_id ?? "",
          )}/split-long-text`,
          {
            method: "POST",
            body: JSON.stringify({
              ...projectQualityPayload(),
              utterances_by_paragraph: utteranceGroupsToApi(currentGroups),
            }),
          },
        );
        const nextGroups = fromApiUtteranceEditGroups(
          data.utterances_by_paragraph,
          paragraphs,
          roles,
        );
        retryUtterances.push(
          ...splitRetryUtterances(
            nextGroups,
            data.split_report?.source_utterance_id ?? item.utterance_id ?? "",
            data.split_report?.paragraph_id ?? item.paragraph_id,
          ),
        );
        currentGroups = nextGroups;
      }
      setUtterancesByParagraph(currentGroups);
      setConfirmed(false);
      retryUtterances.forEach((utterance) => void generateAudio(utterance));
      setQualityStatus(
        `批量拆分超长台词完成：${longItems.length} 条，已加入 ${retryUtterances.length} 条配音重试队列`,
      );
    } catch (error) {
      setQualityStatus(apiFailureMessage("批量拆分超长台词失败", error));
    }
  }

  async function prepareRetryQueue(utteranceIds: string[]): Promise<UtteranceDraft[]> {
    const projectId = activeProject?.project_id ?? activeProjectId;
    const data = await requestJson<UtteranceEditResponse>(
      `/projects/${encodeURIComponent(projectId)}/utterances/retry-queue`,
      {
        method: "POST",
        body: JSON.stringify({
          ...projectQualityPayload(),
          utterance_ids: utteranceIds,
        }),
      },
    );
    const nextGroups = fromApiUtteranceEditGroups(
      data.utterances_by_paragraph,
      paragraphs,
      roles,
    );
    setUtterancesByParagraph(nextGroups);
    return Object.values(nextGroups)
      .flat()
      .filter((utterance) => utteranceIds.includes(utterance.utteranceId));
  }

  async function bulkRetryDubbing() {
    const retryIds = new Set(
      reviewQueue.items
        .filter(
          (item) =>
            item.issue_type === "dubbing_failed" ||
            item.actions?.includes("retry_dubbing"),
        )
        .map((item) => item.utterance_id)
        .filter(Boolean),
    );
    const retryUtterances = flattenedUtterances.filter((utterance) =>
      retryIds.has(utterance.utteranceId),
    );
    if (retryUtterances.length === 0) {
      setQualityStatus("制作阻塞项没有可批量重试的配音失败台词");
      return;
    }
    try {
      const prepared = await prepareRetryQueue(
        retryUtterances.map((utterance) => utterance.utteranceId),
      );
      prepared.forEach((utterance) => void generateAudio(utterance));
      setQualityStatus(
        `批量重试已加入队列：${prepared.length} 条配音失败台词`,
      );
    } catch (error) {
      setQualityStatus(apiFailureMessage("批量重试准备失败", error));
    }
  }

  async function splitLongUtterance(utterance: UtteranceDraft) {
    const projectId = activeProject?.project_id ?? activeProjectId;
    try {
      const data = await requestJson<UtteranceEditResponse>(
        `/projects/${encodeURIComponent(projectId)}/utterances/${encodeURIComponent(
          utterance.utteranceId,
        )}/split-long-text`,
        {
          method: "POST",
          body: JSON.stringify(projectQualityPayload()),
        },
      );
      const nextGroups = fromApiUtteranceEditGroups(
        data.utterances_by_paragraph,
        paragraphs,
        roles,
      );
      setUtterancesByParagraph(nextGroups);
      setConfirmed(false);
      const retryUtterances = splitRetryUtterances(
        nextGroups,
        data.split_report?.source_utterance_id ?? utterance.utteranceId,
        data.split_report?.paragraph_id ?? utterance.paragraphId,
      );
      retryUtterances.forEach((retryUtterance) => void generateAudio(retryUtterance));
      setQualityStatus(
        `长台词已拆分：${data.split_report?.segment_count ?? 0} 段，已加入 ${retryUtterances.length} 条配音重试队列`,
      );
    } catch (error) {
      setQualityStatus(apiFailureMessage("一键拆分长台词失败", error));
    }
  }

  async function mergeWithNextUtterance(utterance: UtteranceDraft) {
    const list = utterancesByParagraph[utterance.paragraphId] ?? [];
    const index = list.findIndex((item) => item.utteranceId === utterance.utteranceId);
    const next = index >= 0 ? list[index + 1] : undefined;
    if (!next) {
      setQualityStatus("合并相邻台词失败：当前台词后面没有相邻台词");
      return;
    }
    const projectId = activeProject?.project_id ?? activeProjectId;
    try {
      const data = await requestJson<UtteranceEditResponse>(
        `/projects/${encodeURIComponent(projectId)}/utterances/merge`,
        {
          method: "POST",
          body: JSON.stringify({
            ...projectQualityPayload(),
            paragraph_id: utterance.paragraphId,
            utterance_ids: [utterance.utteranceId, next.utteranceId],
          }),
        },
      );
      setUtterancesByParagraph(
        fromApiUtteranceEditGroups(data.utterances_by_paragraph, paragraphs, roles),
      );
      setConfirmed(false);
      setQualityStatus(
        `相邻台词已合并：${data.merge_report?.target_utterance_id ?? utterance.utteranceId}`,
      );
    } catch (error) {
      setQualityStatus(apiFailureMessage("合并相邻台词失败", error));
    }
  }

  async function loadAgentRunHistory() {
    setAgentTraceStatus("正在读取 Agent Run History");
    try {
      const data = await requestJson<AgentTraceHistoryResponse>("/agent-runs");
      setAgentTraces(data.runs);
      setSelectedAgentTrace((current) => current ?? data.runs[0] ?? null);
      setAgentTraceStatus(
        data.runs.length
          ? `已载入 ${data.runs.length} 条 运行审计`
          : "暂无 Agent run 记录",
      );
    } catch (error) {
      setAgentTraceStatus(apiFailureMessage("运行审计读取失败", error));
    }
  }

  async function selectAgentTrace(trace: AgentTrace) {
    setSelectedAgentTrace(trace);
    try {
      const data = await requestJson<AgentTraceDetailResponse>(
        `/agent-runs/${trace.run_id}?agent_id=${encodeURIComponent(trace.agent_id)}`,
      );
      setSelectedAgentTrace(data.trace);
    } catch (error) {
      setAgentTraceStatus(apiFailureMessage("运行审计详情读取失败", error));
    }
  }

  async function loadStoryBible() {
    const projectId = activeProject?.project_id ?? activeProjectId;
    setMemoryStatus("正在读取项目记忆");
    try {
      const data = await requestJson<StoryBibleResponse>(
        `/projects/${encodeURIComponent(projectId)}/story-bible`,
      );
      setStoryBibleFacts(data.facts);
      setMemoryStatus(
        data.facts.length
          ? `已载入 ${data.facts.length} 条项目记忆`
          : "项目记忆为空，可先索引正文或手动写入用户纠错",
      );
    } catch (error) {
      setMemoryStatus(apiFailureMessage("项目记忆读取失败", error));
    }
  }

  async function searchStoryMemoryContext() {
    const projectId = activeProject?.project_id ?? activeProjectId;
    const query = memoryQuery.trim() || activeChapter?.title || "角色";
    setMemoryStatus(`正在检索项目记忆：${query}`);
    try {
      const data = await requestJson<StoryMemoryContextResponse>(
        `/projects/${encodeURIComponent(projectId)}/story-bible/memory-context?query=${encodeURIComponent(query)}`,
      );
      setMemoryContext(data);
      setMemoryStatus(
        `记忆上下文已更新：可信 ${data.facts_for_prompt.length} 条，候选 ${data.candidate_facts.length} 条，已拒绝 ${data.rejected_facts.length} 条`,
      );
    } catch (error) {
      setMemoryStatus(apiFailureMessage("项目记忆检索失败", error));
    }
  }

  async function saveMemoryCorrection() {
    const subject = memoryCorrection.subject.trim();
    const predicate = memoryCorrection.predicate.trim();
    const object = memoryCorrection.object.trim();
    if (!subject || !predicate || !object) {
      setMemoryStatus("用户纠错需要填写主体、关系和事实内容");
      return;
    }
    const projectId = activeProject?.project_id ?? activeProjectId;
    try {
      const data = await requestJson<{ fact: StoryBibleFact }>(
        `/projects/${encodeURIComponent(projectId)}/story-bible/facts`,
        {
          method: "POST",
          body: JSON.stringify({
            subject,
            predicate,
            object,
            notes: memoryCorrection.notes,
            source_type: "user_correction",
            writer: "user",
            confidence: "user_confirmed",
          }),
        },
      );
      setStoryBibleFacts((current) => [
        data.fact,
        ...current.filter((fact) => fact.fact_id !== data.fact.fact_id),
      ]);
      setMemoryCorrection({ subject: "", predicate: "alias", object: "", notes: "" });
      setMemoryStatus(`用户纠错已写入：${data.fact.subject} ${data.fact.predicate}`);
    } catch (error) {
      setMemoryStatus(apiFailureMessage("用户纠错写入失败", error));
    }
  }

  function applyTtsDeployment(
    status: Partial<TtsDeploymentStatus> | null | undefined,
  ) {
    const normalized = normalizeTtsDeployment(status);
    setTtsDeployment(normalized);
    if (normalized.model_path || normalized.voice_design_model_path) {
      setModelConfig((current) => ({
        ...current,
        tts: {
          ...current.tts,
          ...(normalized.model_path
            ? { model_path: normalized.model_path }
            : {}),
          ...(normalized.voice_design_model_path
            ? { voice_design_model_path: normalized.voice_design_model_path }
            : {}),
        },
      }));
    }
    return normalized;
  }

  useEffect(() => {
    void loadProjects();

    requestJson<{ voices: ApiVoiceResource[] }>("/voice-profiles")
      .then((data) => setVoices(data.voices.map(fromApiVoice)))
      .catch((error) =>
        setApiStatus(apiFailureMessage("音色库载入失败，已保持空列表", error)),
      );

    requestJson<{ roles: ApiRoleCard[] }>("/characters")
      .then((data) => setRoles(data.roles.map(fromApiRole)))
      .catch((error) =>
        setApiStatus(
          apiFailureMessage("角色列表载入失败，已保持空列表", error),
        ),
      );

    requestJson<{ config: ModelConfig }>("/model-config")
      .then((data) => setModelConfig(normalizeModelConfig(data.config)))
      .catch(() => undefined);

    requestJson<{ deployment: TtsDeploymentStatus }>(
      "/model-config/tts/deployment",
    )
      .then((data) => applyTtsDeployment(data.deployment))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (page === "agent-runs") void loadAgentRunHistory();
    if (page === "memory") void loadStoryBible();
  }, [page]);

  useEffect(() => {
    if (ttsDeployment.status !== "running") return undefined;
    let cancelled = false;
    const poll = () => {
      requestJson<{ deployment: TtsDeploymentStatus }>(
        "/model-config/tts/deployment",
      )
        .then((data) => {
          if (cancelled) return;
          const status = applyTtsDeployment(data.deployment);
          if (status.status !== "running") setApiStatus(status.message);
        })
        .catch((error) => {
          if (!cancelled)
            setApiStatus(apiFailureMessage("TTS模型部署进度读取失败", error));
        });
    };
    poll();
    const timer = window.setInterval(poll, 1200);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [ttsDeployment.status]);

  useEffect(() => {
    if (
      workflowState.mode !== "automatic" ||
      workflowState.status !== "running"
    )
      return;
    if (
      workflowState.activeAgent === "role_analyzer" &&
      agentRunWaitingForRoles &&
      !agentRunRunning &&
      !automaticRoleMatchingAttemptedRef.current
    ) {
      automaticRoleMatchingAttemptedRef.current = true;
      void runAiRoleMatching();
      return;
    }
    if (
      workflowState.activeAgent === "dubbing_director" &&
      confirmed &&
      !automaticDubbingStartedRef.current
    ) {
      automaticDubbingStartedRef.current = true;
      void generateChapterDubbing();
    }
  }, [
    agentRunRunning,
    agentRunWaitingForRoles,
    confirmed,
    workflowState.activeAgent,
    workflowState.mode,
    workflowState.status,
  ]);

  async function importNovelText(text: string) {
    fullNovelTextRef.current = text;
    setNovelPreview(makeNovelPreview(text));
    try {
      const data = await requestJson<{ chapters: ApiChapter[] }>(
        "/books/parse",
        {
          method: "POST",
          body: JSON.stringify({ text }),
        },
      );
      const parsed = data.chapters.map(fromApiChapter);
      applyChapters(parsed, "小说已上传并由后端划分章节");
    } catch (error) {
      applyChapters(
        parseChapters(text),
        apiFailureMessage("后端导入失败，已使用本地章节预览", error),
      );
    }
  }

  function applyChapters(parsed: Chapter[], status: string) {
    setChapters(parsed);
    setActiveChapterId("");
    setParagraphs([]);
    setHasSplitChapters(parsed.length > 0);
    setConfirmed(false);
    setChapterBackendSynced(false);
    setUtterancesByParagraph({});
    setGeneratingUtteranceIds({});
    resetAgentRunState();
    setApiStatus(status);
  }

  async function handleTxtFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploadProgress(8);
    setApiStatus(`正在读取小说：${file.name}`);
    const upload = await readNovelFileUpload(file);
    fullNovelTextRef.current = upload.text;
    uploadedNovelFileRef.current = upload.uploadedFile;
    setNovelPreview(upload.preview);
    setChapters([]);
    setActiveChapterId("");
    setParagraphs([]);
    setHasSplitChapters(false);
    setChapterBackendSynced(false);
    setChapterSplitProgress(0);
    setRoleMatchingProgress(0);
    setVoiceGenerationProgress(0);
    setGeneratingUtteranceIds({});
    resetAgentRunState();
    setUploadProgress(62);
    setApiStatus("小说已上传，仅展示开头预览；点击“文档解析”生成章节目录");
    setUploadProgress(100);
  }

  async function runAiChapterSplit() {
    setChapterSplitProgress(12);
    setApiStatus("文档解析正在检查可复用规则");
    try {
      await requestJson<ConnectionTestResponse>("/connection-test");
      const uploadedFile = uploadedNovelFileRef.current;
      const data = uploadedFile
        ? await requestJson<ApiChapterSplitResponse>(
            "/books/agent-chapter-split-file",
            (() => {
              const form = new FormData();
              form.append(
                "file",
                new File(
                  [
                    Uint8Array.from(
                      atob(uploadedFile.contentBase64),
                      (character) => character.charCodeAt(0),
                    ),
                  ],
                  uploadedFile.filename,
                  { type: "application/epub+zip" },
                ),
              );
              return { method: "POST", body: form };
            })(),
          )
        : await requestJson<ApiChapterSplitResponse>(
            "/books/agent-chapter-split",
            {
              method: "POST",
              body: JSON.stringify({ text: fullNovelTextRef.current }),
            },
          );
      setChapterSplitProgress(84);
      const parsed = data.chapters.map(fromApiChapter);
      const ruleName =
        data.agent.rule_path?.split(/[\\/]/).pop() ?? "未记录规则";
      const agentStatus =
        data.agent.status === "rule_reused"
          ? `文档解析完成：已复用 ${ruleName}`
          : `文档解析完成：已生成并保存 ${ruleName}`;
      applyChapters(parsed, `${agentStatus}；选择左侧章节后才加载该章正文`);
    } catch (error) {
      setChapterSplitProgress(76);
      const parsed = parseChapterIndex(fullNovelTextRef.current);
      applyChapters(parsed, documentParseFallbackMessage(error));
    } finally {
      setChapterSplitProgress(100);
    }
  }

  async function selectChapter(chapterId: string) {
    const chapter = chapters.find((item) => item.chapterId === chapterId);
    if (!chapter) return;
    setActiveChapterId(chapterId);
    const body = extractChapterBody(fullNovelTextRef.current, chapter);
    const nextParagraphs = paragraphsFromChapter({ ...chapter, body });
    setParagraphs(nextParagraphs);
    setConfirmed(false);
    setChapterBackendSynced(false);
    setUtterancesByParagraph(makeWholeParagraphUtteranceGroups(nextParagraphs));
    setRoleMatchingProgress(0);
    setVoiceGenerationProgress(0);
    setGeneratingUtteranceIds({});
    resetAgentRunState();
    setApiStatus(`已加载章节：${chapter.title}`);
  }

  async function syncCurrentChapterParagraphs(confirm = false): Promise<{
    paragraphs: ParagraphModule[];
    canSegment: boolean;
    utteranceDrafts: ApiUtterance[];
  }> {
    if (!activeChapter) throw new Error("请选择章节");
    const data = await requestJson<ApiChapterParagraphsResponse>(
      `/chapters/${activeChapter.chapterId}/paragraphs`,
      {
        method: "PUT",
        body: JSON.stringify({
          title: activeChapter.title,
          paragraphs: visibleParagraphs.map((paragraph) => ({
            paragraph_id: paragraph.paragraphId,
            text: paragraph.text,
            collapsed: paragraph.collapsed,
            deleted: paragraph.deleted,
          })),
          confirm,
        }),
      },
    );
    const syncedParagraphs = data.paragraphs.map(fromApiParagraph);
    setParagraphs(syncedParagraphs);
    setConfirmed(data.can_segment);
    setChapterBackendSynced(true);
    return {
      paragraphs: syncedParagraphs,
      canSegment: data.can_segment,
      utteranceDrafts: data.utterance_drafts ?? [],
    };
  }

  function updateParagraph(
    paragraphId: string,
    updates: Partial<ParagraphModule>,
  ) {
    setParagraphs((current) =>
      current.map((paragraph) =>
        paragraph.paragraphId === paragraphId
          ? { ...paragraph, ...updates }
          : paragraph,
      ),
    );
    if ("text" in updates) {
      setConfirmed(false);
      setChapterBackendSynced(false);
      setUtterancesByParagraph({});
      setGeneratingUtteranceIds({});
      resetAgentRunState();
    }
  }

  function deleteParagraph(paragraphId: string) {
    setParagraphs((current) =>
      current.map((paragraph) =>
        paragraph.paragraphId === paragraphId
          ? { ...paragraph, deleted: true }
          : paragraph,
      ),
    );
    setUtterancesByParagraph((current) => {
      const remainingUtterances = { ...current };
      delete remainingUtterances[paragraphId];
      return remainingUtterances;
    });
    setGeneratingUtteranceIds((current) => {
      const remainingGeneratingIds = { ...current };
      for (const utterance of utterancesByParagraph[paragraphId] ?? []) {
        delete remainingGeneratingIds[utterance.utteranceId];
      }
      return remainingGeneratingIds;
    });
    setChapterBackendSynced(false);
    setApiStatus(`已删除段落 ${paragraphId}；其余配音编排 Agent 结果已保留`);
  }

  async function ensureChapterStatementsReady(): Promise<
    Record<string, UtteranceDraft[]>
  > {
    const hasStatementDrafts = visibleParagraphs.some(
      (paragraph) =>
        (utterancesByParagraph[paragraph.paragraphId] ?? []).length > 0,
    );
    if (confirmed && hasStatementDrafts) return utterancesByParagraph;
    setApiStatus("正在同步当前章节并准备可匹配台词草稿");
    const synced = await syncCurrentChapterParagraphs(true);
    const draftsByParagraph = Object.fromEntries(
      synced.paragraphs.map((paragraph) => [
        paragraph.paragraphId,
        synced.utteranceDrafts.filter(
          (utterance) => utterance.paragraph_id === paragraph.paragraphId,
        ),
      ]),
    );
    const nextUtterances = apiUtterancesToGroups(
      draftsByParagraph,
      synced.paragraphs,
      roles,
    );
    setUtterancesByParagraph(nextUtterances);
    setApiStatus(
      "当前章节已准备为可编辑台词草稿；配音编排 Agent 将自动完成台词划分和角色选择",
    );
    return nextUtterances;
  }

  async function confirmParagraphs() {
    if (visibleParagraphs.length === 0) return;
    setApiStatus("正在同步当前章节段落并确认");
    try {
      const synced = await syncCurrentChapterParagraphs(true);
      const draftsByParagraph = Object.fromEntries(
        synced.paragraphs.map((paragraph) => [
          paragraph.paragraphId,
          synced.utteranceDrafts.filter(
            (utterance) => utterance.paragraph_id === paragraph.paragraphId,
          ),
        ]),
      );
      setUtterancesByParagraph(
        apiUtterancesToGroups(draftsByParagraph, synced.paragraphs, roles),
      );
      setApiStatus(
        "段落已确认，已默认按整段落生成台词文本；配音编排 Agent 将自动完成台词划分和角色选择",
      );
    } catch (error) {
      setConfirmed(false);
      setChapterBackendSynced(false);
      setApiStatus(apiFailureMessage("段落确认失败", error));
    }
  }

  function applyVoiceToRole(role: RoleCard, voiceId: string): RoleCard {
    if (!voiceId) {
      return {
        ...role,
        voiceResourceId: "",
        referenceAudioPath: "",
        referenceText: "",
        voiceMode: "voice_design",
        voiceDescription: "",
        voiceSampleText: "",
        playableVoicePath: "",
        voiceMatchScore: null,
        voiceMatchReason: "用户手动清除音色",
        voiceGeneratedByAi: false,
      };
    }
    const voice = voices.find((item) => item.voiceId === voiceId);
    if (!voice) return role;
    return {
      ...role,
      voiceResourceId: voice.voiceId,
      referenceAudioPath: voice.referenceAudioPath,
      referenceText: voice.referenceText,
      description: voice.description,
      voiceMode: "voice_cloning",
      designPrompt: "",
      voiceDescription: voice.description,
      voiceSampleText: voice.referenceText,
      playableVoicePath: voice.playableAudioPath || voice.referenceAudioPath,
      voiceMatchScore: null,
      voiceMatchReason: "用户手动选择音色",
      voiceGeneratedByAi: voice.generated,
    };
  }

  function updateRole(roleId: string, updates: Partial<RoleCard>) {
    const currentRole = roles.find((role) => role.roleId === roleId);
    if (!currentRole) return;
    if (updates.voiceResourceId) {
      const duplicate = roles.find(
        (role) =>
          role.roleId !== roleId &&
          role.voiceResourceId === updates.voiceResourceId,
      );
      if (duplicate) {
        setApiStatus(
          `音色已分配给 ${duplicate.name}，本章节每个角色需要使用唯一音色`,
        );
        return;
      }
    }
    const merged = { ...currentRole, ...updates };
    const updatedRole =
      updates.voiceResourceId !== undefined
        ? applyVoiceToRole(merged, updates.voiceResourceId)
        : merged;
    setRoles((current) =>
      current.map((role) => (role.roleId === roleId ? updatedRole : role)),
    );
    requestJson(`/characters/${roleId}`, {
      method: "PATCH",
      body: JSON.stringify(toApiRole(updatedRole)),
    }).catch((error) => setApiStatus(apiFailureMessage("角色同步失败", error)));
  }

  async function addRole() {
    const usedVoiceIds = new Set(
      roles.map((role) => role.voiceResourceId).filter(Boolean),
    );
    const voice = voices.find((item) => !usedVoiceIds.has(item.voiceId));
    const roleId = `custom_role_${Date.now()}`;
    const roleName = `新角色${roles.length + 1}`;
    const role = voice
      ? roleFromVoice(roleId, roleName, voice)
      : createBlankRole(roleId, roleName);
    setRoles((current) => [...current, role]);
    try {
      const data = await requestJson<{ roles: ApiRoleCard[] }>("/characters", {
        method: "POST",
        body: JSON.stringify(toApiRole(role)),
      });
      setRoles(data.roles.map(fromApiRole));
      setApiStatus(`已新增角色：${role.name}`);
    } catch (error) {
      setApiStatus(
        apiFailureMessage("新增角色同步失败，已保留本地角色", error),
      );
    }
  }

  async function deleteRole(roleId: string) {
    const payload = {
      roles: roles.map(toApiRole),
      utterances_by_paragraph: utteranceGroupsToApi(utterancesByParagraph),
    };
    try {
      const data = await requestJson<{
        roles: ApiRoleCard[];
        utterances_by_paragraph: Record<string, ApiUtterance[]>;
      }>(`/characters/${roleId}`, {
        method: "DELETE",
        body: JSON.stringify(payload),
      });
      setRoles(data.roles.map(fromApiRole));
      setUtterancesByParagraph(
        apiUtterancesToGroups(
          data.utterances_by_paragraph,
          paragraphs,
          data.roles.map(fromApiRole),
        ),
      );
      setApiStatus("角色删除成功");
    } catch (error) {
      if (!isRoleDeleteReferenceConflict(error)) {
        setApiStatus(apiFailureMessage("角色删除失败", error));
        return;
      }
      const detail = error.detail as {
        delete_result?: { referenced_count?: number };
      };
      const referencedCount = detail.delete_result?.referenced_count ?? 0;
      const shouldUnbind = window.confirm(
        `角色正在被 ${referencedCount} 条台词引用，是否解除这些台词的角色绑定并删除？`,
      );
      if (!shouldUnbind) {
        setApiStatus("角色删除已取消：仍保留角色和台词绑定");
        return;
      }
      try {
        const data = await requestJson<{
          roles: ApiRoleCard[];
          utterances_by_paragraph: Record<string, ApiUtterance[]>;
        }>(`/characters/${roleId}`, {
          method: "DELETE",
          body: JSON.stringify({ ...payload, action: "unbind" }),
        });
        const nextRoles = data.roles.map(fromApiRole);
        setRoles(nextRoles);
        setUtterancesByParagraph(
          apiUtterancesToGroups(
            data.utterances_by_paragraph,
            paragraphs,
            nextRoles,
          ),
        );
        setApiStatus("已解除引用台词的角色绑定并删除角色");
      } catch (secondError) {
        setApiStatus(apiFailureMessage("角色删除失败", secondError));
      }
    }
  }

  async function runAiRoleAnalysis() {
    if (!activeChapter || visibleParagraphs.length === 0) return;
    setAgentRunRunning(true);
    automaticDubbingStartedRef.current = false;
    automaticRoleMatchingAttemptedRef.current = false;
    setWorkflowState((current) =>
      transitionWorkflow(current, { type: "START" }),
    );
    setRoleMatchingProgress(8);
    setApiStatus("角色分析 Agent 正在同步当前章节、创建角色并匹配音色");
    try {
      await syncCurrentChapterParagraphs(false);
      const data = await requestJson<RoleAnalysisRunResponse>(
        `/chapters/${activeChapter.chapterId}/agent-runs`,
        { method: "POST", body: JSON.stringify({}) },
      );
      if (data.voices?.length) setVoices(data.voices.map(fromApiVoice));
      if (data.roles?.length) setRoles(data.roles.map(fromApiRole));
      setAgentRunThreadId(data.thread_id);
      setAiRoleCandidates(data.role_candidates);
      setAgentRunWaitingForRoles(true);
      setWorkflowState((current) =>
        transitionWorkflow(current, { type: "AGENT_COMPLETED" }),
      );
      setRoleMatchingProgress(35);
      const autoSummary = data.auto_role_report
        ? `自动新增 ${data.auto_role_report.added_count} 个角色，生成 ${data.auto_role_report.generated_voice_count} 个音色。`
        : "";
      setApiStatus(
        `${data.message} ${autoSummary} 请检查角色列表后点击“配音编排 Agent”。`,
      );
      void loadAgentRunHistory();
    } catch (error) {
      resetAgentRunState();
      setRoleMatchingProgress(100);
      setApiStatus(apiFailureMessage("角色分析 Agent 失败", error));
    } finally {
      setAgentRunRunning(false);
    }
  }

  async function runAiRoleMatching() {
    if (!agentRunThreadId) return;
    setAgentRunRunning(true);
    setWorkflowState((current) =>
      transitionWorkflow(current, { type: "CONTINUE" }),
    );
    setAgentRunWaitingForRoles(false);
    setRoleMatchingProgress(45);
    setApiStatus("配音编排 Agent 正在划分台词并为未绑定台词选择角色");
    try {
      const readyUtterances = await ensureChapterStatementsReady();
      const requestBody = JSON.stringify({
        roles: roles.map(toApiRole),
        utterances_by_paragraph: utteranceGroupsToApi(readyUtterances),
      });
      let lastEventId = 0;
      let terminalReceived = false;
      for (let attempt = 0; attempt < 3 && !terminalReceived; attempt += 1) {
        try {
          const response = await fetchApi(
            `/agent-runs/${agentRunThreadId}/events`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                ...(lastEventId
                  ? { "Last-Event-ID": String(lastEventId) }
                  : {}),
              },
              body: requestBody,
            },
          );
          if (!response.ok) throw new Error(await response.text());
          if (!response.body) throw new Error("配音编排 Agent 没有返回进度流");
          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";
          while (true) {
            const { value, done } = await reader.read();
            buffer += decoder.decode(value ?? new Uint8Array(), {
              stream: !done,
            });
            const parsed = parseAgentSseBuffer(buffer);
            buffer = parsed.remainder;
            for (const event of parsed.events) {
              lastEventId = Math.max(lastEventId, event.id);
              handleAgentRunStreamEvent(event);
              terminalReceived ||=
                event.event === "completed" || event.event === "failed";
            }
            if (done) break;
          }
          if (!terminalReceived && attempt < 2) {
            await new Promise((resolve) =>
              window.setTimeout(resolve, 250 * 2 ** attempt),
            );
          }
        } catch (error) {
          if (attempt >= 2) throw error;
          await new Promise((resolve) =>
            window.setTimeout(resolve, 250 * 2 ** attempt),
          );
        }
      }
      if (!terminalReceived) throw new Error("配音编排 Agent 进度流提前结束");
    } catch (error) {
      setAgentRunWaitingForRoles(true);
      setRoleMatchingProgress(100);
      setApiStatus(apiFailureMessage("配音编排 Agent 失败", error));
    } finally {
      setAgentRunRunning(false);
    }
  }

  function handleAgentRunStreamEvent(event: { event: string; data: any }) {
    if (event.event === "role_selected") {
      applyAiRoleSelectionEvent(event.data as AiRoleSelectionEvent);
      setRoleMatchingProgress((current) =>
        Math.min(95, Math.max(current + 5, 55)),
      );
      return;
    }
    if (event.event === "completed") {
      const data = event.data as DubbingArrangementResponse;
      setUtterancesByParagraph(
        apiUtterancesToGroups(data.utterances_by_paragraph, paragraphs, roles),
      );
      const requiresHumanReview =
        data.status === "needs_human_review" ||
        data.role_selection_events.some((item) => item.needs_human_review);
      setConfirmed(!requiresHumanReview);
      setChapterBackendSynced(true);
      setAgentRunWaitingForRoles(false);
      setRoleMatchingProgress(100);
      setApiStatus(data.message);
      setWorkflowState((current) =>
        transitionWorkflow(current, {
          type:
            data.status === "needs_human_review" ? "PAUSE" : "AGENT_COMPLETED",
        }),
      );
      void loadAgentRunHistory();
      return;
    }
    if (event.event === "failed") {
      const message =
        event.data?.failure?.message ??
        event.data?.message ??
        "模型输出未通过校验";
      setAgentRunWaitingForRoles(true);
      setRoleMatchingProgress(100);
      setApiStatus(`配音编排 Agent 失败：${message}`);
    }
  }

  function applyAiRoleSelectionEvent(event: AiRoleSelectionEvent) {
    setUtterancesByParagraph((current) => {
      const list = current[event.paragraph_id] ?? [];
      const role = roles.find((item) => item.roleId === event.speaker_role_id);
      const next: UtteranceDraft = {
        utteranceId: event.utterance_id,
        paragraphId: event.paragraph_id,
        text: event.text,
        roleId: role?.roleId ?? event.speaker_role_id ?? "",
        speakerName: event.speaker_name || role?.name || "",
        audioStatus: event.needs_human_review
          ? "AI已选择角色，请人工确认"
          : "AI已选择角色",
        needsHumanReview: event.needs_human_review,
      };
      const found = list.some(
        (item) => item.utteranceId === event.utterance_id,
      );
      return {
        ...current,
        [event.paragraph_id]: found
          ? list.map((item) =>
              item.utteranceId === event.utterance_id
                ? { ...item, ...next }
                : item,
            )
          : [...list, next],
      };
    });
  }

  function updateUtterance(
    paragraphId: string,
    utteranceId: string,
    field: keyof UtteranceDraft,
    value: string | number | boolean,
  ) {
    setUtterancesByParagraph((current) => ({
      ...current,
      [paragraphId]: (current[paragraphId] ?? []).map((utterance) => {
        if (utterance.utteranceId !== utteranceId) return utterance;
        const updated = { ...utterance, [field]: value };
        if (field === "roleId") {
          const role = roles.find((item) => item.roleId === value);
          updated.speakerName = role?.name ?? "";
          updated.needsHumanReview = !value || !updated.text.trim();
          if (!value) {
            updated.audioStatus = "请选择角色后再确认";
          }
        }
        if (field === "text") {
          updated.needsHumanReview = !updated.roleId || !String(value).trim();
        }
        return updated;
      }),
    }));
    if (field === "roleId" && !value) setConfirmed(false);
  }

  function firstPendingUtterance(
    utterances: UtteranceDraft[] = flattenedUtterances,
  ) {
    return utterances.find(
      (utterance) =>
        utterance.needsHumanReview ||
        !utterance.roleId ||
        !utterance.text.trim(),
    );
  }

  function focusUtterance(utterance: UtteranceDraft, statusMessage: string) {
    setHighlightUtteranceId(utterance.utteranceId);
    document
      .querySelector(`[data-utterance-id="${utterance.utteranceId}"]`)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
    window.setTimeout(() => setHighlightUtteranceId(""), 1600);
    setApiStatus(statusMessage);
  }

  function focusParagraphStatusItem(
    item: ParagraphStatusItem,
    statusMessage: string,
  ) {
    setHighlightParagraphId(item.paragraphId);
    if (item.firstUtteranceId) setHighlightUtteranceId(item.firstUtteranceId);
    document
      .querySelector(`[data-reader-paragraph-id="${item.paragraphId}"]`)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
    if (item.firstUtteranceId) {
      document
        .querySelector(`[data-utterance-id="${item.firstUtteranceId}"]`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    window.setTimeout(() => {
      setHighlightParagraphId("");
      if (item.firstUtteranceId) setHighlightUtteranceId("");
    }, 1600);
    setApiStatus(statusMessage);
  }

  function toggleParagraphStatusFilter(status: ParagraphDubbingStatus) {
    const nextStatus = activeParagraphStatusFilter === status ? "" : status;
    setActiveParagraphStatusFilter(nextStatus);
    if (!nextStatus) {
      setApiStatus("已显示全部正文状态");
      return;
    }
    const firstItem = paragraphStatusItems.find(
      (item) => item.status === nextStatus,
    );
    if (!firstItem) {
      setApiStatus(
        `当前章节没有${PARAGRAPH_STATUS_META[nextStatus].label}段落`,
      );
      return;
    }
    focusParagraphStatusItem(
      firstItem,
      `已筛选并跳转到${firstItem.label}段落：${firstItem.paragraphId}`,
    );
  }

  function jumpToFirstUnselectedRoleUtterance() {
    const pending = flattenedUtterances.find((utterance) => !utterance.roleId);
    if (!pending) {
      setApiStatus("当前没有未选择角色的台词");
      return;
    }
    focusUtterance(pending, `已跳转到未选择角色的台词：${pending.utteranceId}`);
  }

  function jumpToFirstUngeneratedAudioUtterance() {
    const pendingParagraph = paragraphStatusItems.find(
      (item) => item.status === "undubbed",
    );
    if (!pendingParagraph) {
      setApiStatus("当前没有未生成配音的台词");
      return;
    }
    focusParagraphStatusItem(
      pendingParagraph,
      `已跳转到未生成配音的段落：${pendingParagraph.paragraphId}`,
    );
  }

  function confirmAllReadyUtterances() {
    let remaining = 0;
    const nextGroups: Record<string, UtteranceDraft[]> = {};
    for (const [paragraphId, utterances] of Object.entries(
      utterancesByParagraph,
    )) {
      nextGroups[paragraphId] = utterances.map((utterance) => {
        const ready = Boolean(utterance.roleId && utterance.text.trim());
        if (!ready) remaining += 1;
        return {
          ...utterance,
          needsHumanReview: !ready,
          audioStatus:
            ready && utterance.audioStatus === "请选择角色后再确认"
              ? "台词与角色已确认"
              : utterance.audioStatus,
        };
      });
    }
    setUtterancesByParagraph(nextGroups);
    setConfirmed(remaining === 0 && flattenedUtterances.length > 0);
    if (remaining > 0) {
      setApiStatus(`仍有 ${remaining} 条台词缺少文本或角色，请处理后再确认`);
      const pending = firstPendingUtterance();
      if (pending) {
        window.setTimeout(
          () => focusUtterance(pending, `请处理台词：${pending.utteranceId}`),
          0,
        );
      }
      return;
    }
    setApiStatus("所有台词与角色已确认，可以继续生成配音");
    if (
      workflowState.mode === "automatic" &&
      workflowState.activeAgent === "dubbing_director"
    ) {
      setWorkflowState((current) =>
        transitionWorkflow(current, { type: "CONTINUE" }),
      );
      if (!automaticDubbingStartedRef.current) {
        automaticDubbingStartedRef.current = true;
        void generateChapterDubbing(true);
      }
    }
  }

  function addUtteranceAfter(paragraphId: string, afterUtteranceId?: string) {
    const paragraph = paragraphs.find(
      (item) => item.paragraphId === paragraphId,
    );
    if (!paragraph) return;
    setUtterancesByParagraph((current) => {
      const list = current[paragraphId] ?? [];
      const nextNumber =
        list.reduce((max, utterance) => {
          const match = utterance.utteranceId.match(/-u-(\d+)$/);
          return Math.max(max, match ? Number(match[1]) : 0);
        }, 0) + 1;
      const draft = {
        ...makeUtteranceDraft({ ...paragraph, text: "" }),
        utteranceId: `${paragraphId}-u-${String(nextNumber).padStart(3, "0")}`,
      };
      const insertIndex = afterUtteranceId
        ? list.findIndex((item) => item.utteranceId === afterUtteranceId) + 1
        : list.length;
      const safeIndex = insertIndex <= 0 ? list.length : insertIndex;
      return {
        ...current,
        [paragraphId]: [
          ...list.slice(0, safeIndex),
          draft,
          ...list.slice(safeIndex),
        ],
      };
    });
  }

  function addCurrentUtteranceAfter(utterance: UtteranceDraft) {
    addUtteranceAfter(utterance.paragraphId, utterance.utteranceId);
  }

  function deleteUtterance(paragraphId: string, utteranceId: string) {
    setUtterancesByParagraph((current) => ({
      ...current,
      [paragraphId]: (current[paragraphId] ?? []).filter(
        (utterance) => utterance.utteranceId !== utteranceId,
      ),
    }));
  }

  function finishChapterPlayback(message = "当前章节配音播放完成") {
    const player = chapterPlayerRef.current;
    if (player) {
      player.pause();
      player.removeAttribute("src");
      player.load();
    }
    chapterPlaybackQueueRef.current = [];
    chapterPlaybackIndexRef.current = 0;
    setChapterPlaybackState("idle");
    setChapterPlaybackUtteranceId("");
    setApiStatus(message);
  }

  function playQueuedChapterAudioAt(index: number) {
    const queue = chapterPlaybackQueueRef.current;
    const utterance = queue[index];
    if (!utterance) {
      finishChapterPlayback();
      return;
    }
    const source = utteranceAudioSource(utterance);
    if (!source) {
      playQueuedChapterAudioAt(index + 1);
      return;
    }
    const player = chapterPlayerRef.current;
    if (!player) {
      setApiStatus("一键播放失败：播放器尚未初始化");
      return;
    }
    chapterPlaybackIndexRef.current = index;
    setChapterPlaybackUtteranceId(utterance.utteranceId);
    setChapterPlaybackState("playing");
    document
      .querySelector(`[data-utterance-id="${utterance.utteranceId}"]`)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
    player.src = mediaRequestUrl(source);
    player.currentTime = 0;
    player
      .play()
      .then(() => setApiStatus(`正在播放配音：${utterance.utteranceId}`))
      .catch((error) => {
        setChapterPlaybackState("paused");
        setApiStatus(apiFailureMessage("一键播放失败", error));
      });
  }

  function ensureChapterPlaybackQueue(): UtteranceDraft[] {
    if (chapterPlaybackQueueRef.current.length > 0) return chapterPlaybackQueueRef.current;
    chapterPlaybackQueueRef.current = playableChapterQueue;
    return chapterPlaybackQueueRef.current;
  }

  function playPreviousQueuedChapterAudio() {
    const queue = ensureChapterPlaybackQueue();
    if (queue.length === 0) {
      setApiStatus("整章播放列表为空：当前章节没有已生成配音的台词");
      return;
    }
    playQueuedChapterAudioAt(Math.max(0, chapterPlaybackIndexRef.current - 1));
  }

  function playNextQueuedChapterAudio() {
    const queue = ensureChapterPlaybackQueue();
    if (queue.length === 0) {
      setApiStatus("整章播放列表为空：当前章节没有已生成配音的台词");
      return;
    }
    playQueuedChapterAudioAt(chapterPlaybackIndexRef.current + 1);
  }

  function toggleChapterPlayback() {
    const player = chapterPlayerRef.current;
    if (chapterPlaybackState === "playing") {
      player?.pause();
      setChapterPlaybackState("paused");
      setApiStatus("已暂停当前章节配音播放");
      return;
    }
    if (chapterPlaybackState === "paused") {
      if (!player) {
        setApiStatus("继续播放失败：播放器尚未初始化");
        return;
      }
      player
        .play()
        .then(() => {
          setChapterPlaybackState("playing");
          setApiStatus(`继续播放配音：${chapterPlaybackUtteranceId}`);
        })
        .catch((error) =>
          setApiStatus(apiFailureMessage("继续播放失败", error)),
        );
      return;
    }
    const queue = playableChapterQueue;
    if (queue.length === 0) {
      setApiStatus("当前章节没有已生成配音的台词");
      return;
    }
    chapterPlaybackQueueRef.current = queue;
    chapterPlaybackIndexRef.current = 0;
    playQueuedChapterAudioAt(0);
  }

  async function generateAudio(utterance: UtteranceDraft) {
    if (queuedUtteranceIdsRef.current.has(utterance.utteranceId)) return;
    queuedUtteranceIdsRef.current.add(utterance.utteranceId);
    setGeneratingUtteranceIds((current) => ({
      ...current,
      [utterance.utteranceId]: true,
    }));
    updateUtterance(
      utterance.paragraphId,
      utterance.utteranceId,
      "audioStatus",
      "已加入配音生成队列",
    );

    const task = dubbingQueueRef.current.then(() =>
      generateAudioNow(utterance),
    );
    dubbingQueueRef.current = task.catch(() => undefined);
    await task;
  }

  async function generateAudioNow(utterance: UtteranceDraft) {
    const role = roles.find((item) => item.roleId === utterance.roleId);
    if (!role) {
      updateUtterance(
        utterance.paragraphId,
        utterance.utteranceId,
        "audioStatus",
        "音频生成失败：角色不存在",
      );
      queuedUtteranceIdsRef.current.delete(utterance.utteranceId);
      setGeneratingUtteranceIds((current) => ({
        ...current,
        [utterance.utteranceId]: false,
      }));
      return;
    }
    updateUtterance(
      utterance.paragraphId,
      utterance.utteranceId,
      "audioStatus",
      "正在根据角色参考音频和语音具体内容生成音频",
    );
    setVoiceGenerationProgress(25);
    try {
      const result = await requestJson<{
        audio_url: string;
        duration_seconds?: number;
        voice_job: {
          status: string;
          output_path?: string;
          provider?: string;
          response_format?: string;
        };
        warning?: string;
      }>(`/dubbing-segments/${utterance.utteranceId}/dubbing-jobs`, {
        method: "POST",
        body: JSON.stringify({
          role_id: role.roleId,
          voice_resource_id: role.voiceResourceId,
          text: utterance.text,
          voice_mode: role.voiceMode,
          language: "Auto",
        }),
      });
      const audioStatus =
        result.voice_job.status === "substitute"
          ? "本地 TTS 未启动，已生成可播放占位音频"
          : "音频生成完成";
      setUtterancesByParagraph((current) => ({
        ...current,
        [utterance.paragraphId]: (current[utterance.paragraphId] ?? []).map(
          (item) =>
            item.utteranceId === utterance.utteranceId
              ? {
                  ...item,
                  audioStatus,
                  audioUrl: result.audio_url,
                  audioPath: result.voice_job.output_path,
                  audioDuration: result.duration_seconds,
                  audioProvider: result.voice_job.provider,
                  audioModel: result.voice_job.response_format,
                  audioError: undefined,
                }
              : item,
        ),
      }));
      setVoiceGenerationProgress(100);
    } catch (error) {
      const message = apiFailureMessage("音频生成失败", error);
      setUtterancesByParagraph((current) => ({
        ...current,
        [utterance.paragraphId]: (current[utterance.paragraphId] ?? []).map(
          (item) =>
            item.utteranceId === utterance.utteranceId
              ? {
                  ...item,
                  audioStatus: message,
                  audioError: apiFailureDetail(error),
                }
              : item,
        ),
      }));
      setVoiceGenerationProgress(100);
    } finally {
      queuedUtteranceIdsRef.current.delete(utterance.utteranceId);
      setGeneratingUtteranceIds((current) => ({
        ...current,
        [utterance.utteranceId]: false,
      }));
    }
  }

  async function generateChapterDubbing(forceConfirmed = false) {
    if (dubbingInFlightRef.current) return;
    if (!activeChapter) {
      setApiStatus("批量生成配音失败：请先选择章节");
      return;
    }
    if (!forceConfirmed && (!confirmed || hasPendingHumanReview)) {
      setApiStatus("批量生成配音失败：请先确认所有配音片段的台词与角色");
      return;
    }
    dubbingInFlightRef.current = true;
    setVoiceGenerationProgress(10);
    setWorkflowState((current) =>
      transitionWorkflow(current, { type: "CONTINUE" }),
    );
    setApiStatus("正在按角色/音色分组批量生成当前章节配音");
    try {
      const data = await requestJson<{
        status: string;
        success_count: number;
        skipped_count: number;
        failed_count: number;
        groups: { voice_resource_id: string; count: number }[];
        errors: { statement_id: string; message: string }[];
        utterances_by_paragraph: Record<string, ApiUtterance[]>;
      }>(`/dubbing-jobs/${activeChapter.chapterId}`, {
        method: "POST",
        body: JSON.stringify({
          roles: roles.map(toApiRole),
          utterances_by_paragraph: utteranceGroupsToApi(utterancesByParagraph),
        }),
      });
      setUtterancesByParagraph((current) =>
        mergeApiAudioByUtteranceId(
          current,
          data.utterances_by_paragraph,
          paragraphs,
          roles,
        ),
      );
      setVoiceGenerationProgress(100);
      setApiStatus(formatBatchDubbingStatus(data));
      setWorkflowState((current) =>
        transitionWorkflow(current, { type: "AGENT_COMPLETED" }),
      );
    } catch (error) {
      setVoiceGenerationProgress(100);
      setApiStatus(apiFailureMessage("批量生成配音失败", error));
    } finally {
      dubbingInFlightRef.current = false;
    }
  }

  async function exportChapterAudio() {
    if (!activeChapter) {
      setApiStatus("导出制作包失败：请先选择章节");
      return;
    }
    setApiStatus("正在导出当前章节完整 WAV/MP3、逐句音频和 manifest");
    try {
      const projectId = activeProject?.project_id ?? activeProjectId;
      const data = await requestJson<{
        status: string;
        item_count: number;
        missing_count: number;
        download_url: string;
        message: string;
        full_audio_path?: string | null;
        full_mp3_path?: string | null;
        package_files?: Record<string, string | null>;
      }>(`/projects/${encodeURIComponent(projectId)}/exports/${activeChapter.chapterId}`, {
        method: "POST",
        body: JSON.stringify({
          chapter_title: activeChapter.title,
          roles: roles.map(toApiRole),
          utterances_by_paragraph: utteranceGroupsToApi(utterancesByParagraph),
          pause_ms: exportOptions.pauseMs,
          speed: exportOptions.speed,
          trim_silence: exportOptions.trimSilence,
          normalize_audio: exportOptions.normalizeAudio,
          target_peak: exportOptions.targetPeak,
          export_formats: exportOptions.exportFormats,
        }),
      });
      const response = await fetch(mediaRequestUrl(data.download_url));
      if (!response.ok) throw new Error(`制作包下载失败：${response.status}`);
      const objectUrl = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = `${activeChapter.title || activeChapter.chapterId}-制作包.zip`;
      anchor.click();
      URL.revokeObjectURL(objectUrl);
      setApiStatus(
        `${EXPORT_PRESETS[exportPreset].label}制作包导出完成：${data.item_count} 条；完整 WAV/MP3、CSV 台本、SRT/LRC 字幕、角色表、音色表和失败清单已写入压缩包。${data.message}`,
      );
    } catch (error) {
      setApiStatus(apiFailureMessage("导出制作包失败", error));
    }
  }

  async function saveVoiceResource(
    payload: Omit<Partial<VoiceResource>, "suitableRoleTypes"> & {
      suitableRoleTypes?: string[] | string;
    },
  ): Promise<boolean> {
    try {
      const data = await requestJson<{
        voice: ApiVoiceResource;
        voices: ApiVoiceResource[];
      }>("/voice-profiles", {
        method: "POST",
        body: JSON.stringify(toApiVoice(payload)),
      });
      setVoices(data.voices.map(fromApiVoice));
      setApiStatus(`保存音色成功：${data.voice.name}`);
      return true;
    } catch (error) {
      setApiStatus(apiFailureMessage("保存音色失败", error));
      return false;
    }
  }

  async function updateVoiceResource(voice: VoiceResource) {
    try {
      const data = await requestJson<{
        voice: ApiVoiceResource;
        voices: ApiVoiceResource[];
      }>(`/voice-profiles/${voice.voiceId}`, {
        method: "PATCH",
        body: JSON.stringify(toApiVoice(voice)),
      });
      setVoices(data.voices.map(fromApiVoice));
      setApiStatus(`保存音色成功：${data.voice.name}`);
    } catch (error) {
      setApiStatus(apiFailureMessage("保存音色失败", error));
    }
  }

  async function handleReferenceAudioFile(
    event: ChangeEvent<HTMLInputElement>,
  ) {
    const file = event.target.files?.[0];
    if (!file) return;
    setApiStatus(`正在上传参考音频文件：${file.name}`);
    try {
      const form = new FormData();
      form.append("file", file);
      const data = await requestJson<{ reference_audio_path: string }>(
        "/voice-profiles/reference-audio",
        {
          method: "POST",
          body: form,
        },
      );
      if (newVoiceAudioPreviewUrl) URL.revokeObjectURL(newVoiceAudioPreviewUrl);
      setNewVoiceAudioPreviewUrl(URL.createObjectURL(file));
      setNewVoice((current) => ({
        ...current,
        referenceAudioPath: data.reference_audio_path,
        playableAudioPath: data.reference_audio_path,
      }));
      setApiStatus(`参考音频文件已选择：${file.name}`);
    } catch (error) {
      setApiStatus(
        error instanceof ApiRequestError && error.status === 0
          ? "没有连接后端，上传失败：ApiRequestError"
          : apiFailureMessage("上传失败", error),
      );
    }
  }

  async function generateVoiceResource() {
    setGeneratedVoiceProgress(12);
    setApiStatus("正在根据音色描述生成试听音色");
    try {
      const data = await requestJson<{
        voice: ApiVoiceResource;
        audio_url: string;
        generation_status: "succeeded" | "substitute";
        generation_note: string;
        model_requirement?: string | null;
      }>("/voice-profiles/generate", {
        method: "POST",
        body: JSON.stringify({
          name: generatedVoice.name,
          description: generatedVoice.description,
          gender: generatedVoice.gender,
          suitable_role_types: generatedVoice.suitableRoleTypes
            .split(/[，,、]/)
            .map((item) => item.trim())
            .filter(Boolean),
          reference_text:
            generatedVoice.referenceText || DEFAULT_GENERATED_VOICE_TEXT,
        }),
      });
      setGeneratedVoiceProgress(100);
      setGeneratedVoicePreview(fromApiVoice(data.voice));
      setGeneratedVoicePreviewUrl(data.audio_url);
      const prefix =
        data.generation_status === "substitute"
          ? "生成音色使用占位预览"
          : "生成音色成功";
      setApiStatus(`${prefix}：${data.generation_note}`);
    } catch (error) {
      setGeneratedVoiceProgress(100);
      setApiStatus(apiFailureMessage("生成音色失败", error));
    }
  }

  async function saveGeneratedVoiceResource() {
    if (!generatedVoicePreview) {
      setApiStatus("请先点击生成音色并试听结果");
      return;
    }
    if (await saveVoiceResource(generatedVoicePreview)) {
      setGeneratedVoicePreview(null);
      setGeneratedVoicePreviewUrl("");
      setGeneratedVoiceProgress(0);
    }
  }

  async function exportVoiceLibrary() {
    setApiStatus("正在导出音色库");
    try {
      const data = await requestJson<{
        status: string;
        voice_count: number;
        audio_count: number;
        download_url: string;
        message: string;
      }>("/voice-profiles/export", { method: "POST" });
      const response = await fetch(mediaRequestUrl(data.download_url));
      if (!response.ok) throw new Error(`音色库下载失败：${response.status}`);
      const objectUrl = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = `音色库-${new Date().toISOString().slice(0, 10)}.zip`;
      anchor.click();
      URL.revokeObjectURL(objectUrl);
      setApiStatus(
        data.message || `音色库导出完成：${data.voice_count} 个音色`,
      );
    } catch (error) {
      setApiStatus(apiFailureMessage("导出音色库失败", error));
    }
  }

  async function deleteSelectedVoices() {
    const selected = voices.filter((item) => selectedVoiceIds[item.voiceId]);
    if (selected.length === 0) {
      setApiStatus("删除选中音色失败：请先勾选至少一个音色");
      return;
    }
    try {
      let remaining = voices;
      for (const voice of selected) {
        const data = await requestJson<{ voices: ApiVoiceResource[] }>(
          `/voice-profiles/${voice.voiceId}`,
          {
            method: "DELETE",
          },
        );
        remaining = data.voices.map(fromApiVoice);
      }
      setVoices(remaining);
      setSelectedVoiceIds({});
      setApiStatus(`删除选中音色成功：${selected.length} 个`);
    } catch (error) {
      setApiStatus(apiFailureMessage("删除选中音色失败", error));
    }
  }

  function applyBackendApiBaseInput(): string {
    const normalized = runtimeConfig.setApiBase(backendApiBase);
    setBackendApiBase(normalized || "/api/v1");
    return normalized;
  }

  function saveBackendApiBase() {
    const normalized = applyBackendApiBaseInput();
    setApiStatus(`后端地址已保存：${normalized || "/api/v1"}`);
  }

  async function saveTextModelConfig() {
    applyBackendApiBaseInput();
    try {
      const secretPayload = await createSecretExchangePayload(textModelApiKey);
      const data = await requestJson<{ config: ModelConfig }>("/model-config", {
        method: "PATCH",
        body: JSON.stringify({
          text_model: modelConfig.text_model,
          ...(secretPayload ? { text_model_secret: secretPayload } : {}),
        }),
      });
      setModelConfig(normalizeModelConfig(data.config));
      setTextModelApiKey("");
      setApiStatus("文本模型配置保存成功；密钥仅保存在后端内存中");
    } catch (error) {
      setApiStatus(apiFailureMessage("文本模型配置保存失败", error));
    }
  }

  async function saveLocalModelConfig() {
    applyBackendApiBaseInput();
    try {
      const data = await requestJson<{ config: ModelConfig }>("/model-config", {
        method: "PATCH",
        body: JSON.stringify({ tts: modelConfig.tts }),
      });
      setModelConfig(normalizeModelConfig(data.config));
      setApiStatus("TTS模型配置保存成功");
    } catch (error) {
      setApiStatus(apiFailureMessage("TTS模型配置保存失败", error));
    }
  }

  async function testBackendConnection() {
    applyBackendApiBaseInput();
    try {
      const data =
        await requestJson<ConnectionTestResponse>("/connection-test");
      setApiStatus(data.message || "后端 API 连接成功");
    } catch (error) {
      setApiStatus(apiFailureMessage("测试连接失败", error));
    }
  }

  async function testModelApis() {
    if (localTtsStarting) return;
    applyBackendApiBaseInput();
    setLocalTtsStarting(true);
    setApiStatus("正在测试文本模型与 TTS 模型 API");
    try {
      const secretPayload = await createSecretExchangePayload(textModelApiKey);
      const data = await requestJson<ModelApisTestResponse>(
        "/model-config/models/test",
        {
          method: "POST",
          body: JSON.stringify({
            text_model: modelConfig.text_model,
            tts: modelConfig.tts,
            ...(secretPayload ? { text_model_secret: secretPayload } : {}),
          }),
        },
      );
      setTextModelApiKey("");
      setApiStatus(data.message || "模型 API 测试成功");
    } catch (error) {
      setApiStatus(apiFailureMessage("测试模型失败", error));
    } finally {
      setLocalTtsStarting(false);
    }
  }

  async function deployTtsModels() {
    if (ttsDeployment.status === "running") return;
    applyBackendApiBaseInput();
    setApiStatus(
      "已开始后台下载并部署 TTS 模型；其他不依赖 TTS 的功能可继续使用",
    );
    try {
      const data = await requestJson<{ deployment: TtsDeploymentStatus }>(
        "/model-config/tts/deploy",
        {
          method: "POST",
          body: JSON.stringify({ tts: modelConfig.tts }),
        },
      );
      const status = applyTtsDeployment(data.deployment);
      setApiStatus(status.message);
    } catch (error) {
      setApiStatus(apiFailureMessage("TTS模型下载并部署启动失败", error));
    }
  }

  function renderMainPage() {
    return (
      <main
        className={
          chapterSidebarCollapsed ? "workbench chapters-collapsed" : "workbench"
        }
        aria-label={`${APP_BRAND} v${APP_VERSION} 主页面`}
      >
        <aside
          className={
            chapterSidebarCollapsed
              ? "chapter-sidebar collapsed"
              : "chapter-sidebar"
          }
        >
          <button
            className="sidebar-toggle"
            type="button"
            aria-label={
              chapterSidebarCollapsed ? "展开小说章节边栏" : "收起小说章节边栏"
            }
            title={
              chapterSidebarCollapsed ? "展开小说章节边栏" : "收起小说章节边栏"
            }
            onClick={() => setChapterSidebarCollapsed((current) => !current)}
          >
            {chapterSidebarCollapsed ? "›" : "‹"}
          </button>
          {chapterSidebarCollapsed ? (
            <span className="collapsed-label">章节</span>
          ) : (
            <>
              <section className="panel">
                <div className="section-title">小说章节</div>
                <div className="toolbar-row">
                  <button
                    className="tool-button sky"
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    上传小说
                  </button>
                  <button
                    className="tool-button amber"
                    type="button"
                    onClick={() => void runAiChapterSplit()}
                  >
                    文档解析
                  </button>
                </div>
                <input
                  ref={fileInputRef}
                  className="hidden-input"
                  aria-label="上传小说"
                  type="file"
                  accept=".txt,.epub,text/plain,application/epub+zip"
                  onChange={handleTxtFile}
                />
                <ProgressBar label="上传小说进度" value={uploadProgress} />
                <ProgressBar
                  label="小说格式解析进度"
                  value={chapterSplitProgress}
                />
                <ProgressBar
                  label="配音编排 Agent 进度"
                  value={roleMatchingProgress}
                />
                <ProgressBar
                  label="语音生成进度"
                  value={voiceGenerationProgress}
                />
                <div className="novel-preview" aria-label="小说开头预览">
                  {novelPreview}
                </div>
                <small>{apiStatus}</small>
                <div className="chapter-list" aria-label="章节列表">
                  {chapters.map((chapter) => (
                    <button
                      className={
                        chapter.chapterId === activeChapterId ? "active" : ""
                      }
                      key={chapter.chapterId}
                      type="button"
                      onClick={() => void selectChapter(chapter.chapterId)}
                    >
                      {chapter.title}
                    </button>
                  ))}
                </div>
              </section>

              <section className="panel production-primary-panel">
                <div className="section-heading">
                  <div>
                    <div className="section-title">一键继续制作</div>
                    <small>主流程只需要跟随这个按钮；高级操作仍保留在当前章节区。</small>
                  </div>
                  <span className="production-step-badge">
                    {workflowState.mode === "automatic" ? "自动" : "分步"}
                  </span>
                </div>
                <button
                  className="production-primary-button"
                  type="button"
                  disabled={productionPrimaryAction.disabled}
                  onClick={() => void handleProductionPrimaryAction()}
                >
                  {productionPrimaryAction.label}
                </button>
                <small className="status-message">
                  {productionPrimaryAction.detail}
                </small>
              </section>

              <section className="panel project-workspace-panel">
                <div className="section-heading">
                  <div>
                    <div className="section-title">项目工作区</div>
                    <small>当前项目：{activeProject?.name ?? "default"}</small>
                  </div>
                  <button
                    className="tool-button sky"
                    type="button"
                    onClick={() => void loadProjects()}
                  >
                    刷新
                  </button>
                </div>
                <div className="toolbar-row">
                  <input
                    aria-label="新建项目名称"
                    placeholder="新建项目名称"
                    value={newProjectName}
                    onChange={(event) => setNewProjectName(event.target.value)}
                  />
                  <button
                    className="tool-button teal"
                    type="button"
                    onClick={() => void createProject()}
                  >
                    新建项目
                  </button>
                </div>
                <div className="project-roots">
                  <span>
                    音频：
                    {activeProject?.output_roots?.audio ??
                      "outputs/default/audio"}
                  </span>
                  <span>
                    导出：
                    {activeProject?.output_roots?.exports ??
                      "outputs/default/exports"}
                  </span>
                </div>
                <div className="section-title">最近项目</div>
                <div className="recent-project-list" aria-label="最近项目">
                  {projects.length === 0 ? (
                    <small>还没有项目记录，默认项目会兼容旧数据。</small>
                  ) : (
                    projects.map((project) => (
                      <article
                        className={
                          project.project_id === activeProjectId
                            ? "project-card active"
                            : "project-card"
                        }
                        key={project.project_id}
                      >
                        <button
                          type="button"
                          onClick={() => selectProject(project.project_id)}
                        >
                          <strong>{project.name}</strong>
                          <span>{project.project_id}</span>
                        </button>
                        <button
                          className="tool-button amber"
                          type="button"
                          disabled={project.project_id === "default"}
                          onClick={() => void deleteProject(project.project_id)}
                        >
                          删除项目
                        </button>
                      </article>
                    ))
                  )}
                </div>
              </section>

              <section className="panel blocker-panel">
                <div className="section-heading">
                  <div>
                    <div className="section-title">制作阻塞项</div>
                    <small>
                      汇总生成、导出和人工复核问题；每条都给出影响和推荐操作。
                    </small>
                  </div>
                  <strong className="blocker-count">{blockerItems.length}</strong>
                </div>
                <div className="toolbar-row">
                  <button
                    className="tool-button teal"
                    type="button"
                    onClick={() => void runQualityCheck("generate")}
                  >
                    刷新阻塞项
                  </button>
                  <button
                    className="tool-button amber"
                    type="button"
                    onClick={() => void runQualityCheck("export")}
                  >
                    导出阻塞项
                  </button>
                </div>
                <div className="quality-summary-grid" aria-label="制作阻塞项统计">
                  {QUALITY_SUMMARY_KEYS.map((key) => (
                    <button
                      className={
                        qualityReport.summary[key] > 0
                          ? "quality-summary-item active"
                          : "quality-summary-item"
                      }
                      key={key}
                      type="button"
                      onClick={() => void loadReviewQueue(key)}
                    >
                      <span>{QUALITY_LABELS[key]}</span>
                      <strong>{qualityReport.summary[key]}</strong>
                    </button>
                  ))}
                </div>
                <small className="status-message" aria-label="制作阻塞项反馈">
                  {qualityStatus}
                </small>

                <div className="blocker-action-row">
                  <button
                    className="tool-button teal"
                    type="button"
                    onClick={() => bulkConfirmReviewItems()}
                  >
                    批量确认
                  </button>
                  <button
                    className="tool-button sky"
                    type="button"
                    onClick={() => void bulkSplitLongUtterances()}
                  >
                    批量拆分超长台词
                  </button>
                  <button
                    className="tool-button sky"
                    type="button"
                    onClick={() => void bulkRetryDubbing()}
                  >
                    批量重试
                  </button>
                </div>
                <div className="bulk-role-row">
                  <label>
                    目标角色
                    <select
                      value={bulkRoleTargetId}
                      onChange={(event) => {
                        setBulkRoleTargetId(event.target.value);
                        setBulkRolePreviewArmed(false);
                      }}
                    >
                      <option value="">请选择目标角色</option>
                      {roles.map((role) => (
                        <option key={role.roleId} value={role.roleId}>
                          {role.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    className="tool-button amber"
                    type="button"
                    disabled={bulkRoleChangeIds.length === 0}
                    onClick={() => void bulkChangeReviewRole()}
                  >
                    {bulkRolePreviewArmed ? "确认批量改角色" : "预览批量改角色"}
                  </button>
                  <small>
                    预览影响 {bulkRoleChangeIds.length} 条台词；选择目标角色后需再次确认。
                  </small>
                </div>
                <div className="review-filter-row" aria-label="阻塞项筛选">
                  {(
                    [
                      "needs_human_review",
                      "unselected_role",
                      "long_utterance",
                      "dubbing_failed",
                    ] as (keyof QualitySummary)[]
                  ).map((issueType) => (
                    <button
                      key={issueType}
                      type="button"
                      onClick={() => void loadReviewQueue(issueType)}
                    >
                      {QUALITY_LABELS[issueType]}
                    </button>
                  ))}
                </div>
                <div className="blocker-list" aria-label="制作阻塞项列表">
                  {blockerItems.length === 0 ? (
                    <small>暂无制作阻塞项；刷新后会显示需要人工处理的事项。</small>
                  ) : (
                    blockerItems.map((item) => (
                      <button
                        className="blocker-card"
                        key={item.issue_id}
                        type="button"
                        onClick={() => focusQualityIssue(item)}
                      >
                        <strong>{QUALITY_LABELS[item.issue_type]}</strong>
                        <span>严重级别：{item.severity || "warning"}</span>
                        <span>影响：{item.message}</span>
                        <small>
                          推荐操作：{BLOCKER_RECOMMENDATIONS[item.issue_type]}
                        </small>
                        <small>
                          处理状态：{(item.actions ?? []).join(" / ") || "jump"}
                        </small>
                      </button>
                    ))
                  )}
                </div>

                <div className="planner-panel" aria-label="智能下一步助手">
                  <div className="section-heading">
                    <div>
                      <div className="section-title">智能下一步助手</div>
                      <small>
                        目标：{plannerGoal}。助手会把当前章节状态翻译成下一步建议。
                      </small>
                    </div>
                    <span className={`planner-status ${plannerRun?.status ?? "idle"}`}>
                      {plannerRun?.status ?? "idle"}
                    </span>
                  </div>
                  <button
                    className="tool-button purple"
                    type="button"
                    onClick={() => void refreshProductionAssistant()}
                  >
                    刷新建议
                  </button>
                  <small className="status-message" aria-label="智能下一步助手反馈">
                    {plannerStatus}
                  </small>
                  <div className="planner-step-list" aria-label="智能下一步建议">
                    {!plannerRun ? (
                      <small>尚未生成建议；点击刷新建议或使用主按钮继续制作。</small>
                    ) : (
                      plannerRun.steps.slice(0, 4).map((step, index) => (
                        <article
                          className={`planner-step-card ${step.status}`}
                          key={step.step_id}
                        >
                          <strong>
                            {index + 1}. {step.title}
                          </strong>
                          <span>{step.status}</span>
                          <small>
                            {step.tool_call?.tool_name ??
                              step.rationale ??
                              "reviewer checkpoint"}
                          </small>
                          {step.tool_result?.failure && (
                            <small>失败原因：{step.tool_result.failure}</small>
                          )}
                        </article>
                      ))
                    )}
                  </div>
                  {(plannerRun?.recovery_suggestions ?? []).length > 0 && (
                    <div className="planner-recovery-list">
                      {(plannerRun?.recovery_suggestions ?? []).map((item) => (
                        <small key={item.step_id}>
                          {item.title}：{item.message}
                        </small>
                      ))}
                    </div>
                  )}
                </div>
              </section>

              <section className="panel">
                <div className="section-heading">
                  <div className="section-title">角色列表</div>
                  <button
                    className="tool-button teal"
                    type="button"
                    onClick={() => void addRole()}
                  >
                    新增角色
                  </button>
                </div>
                <div className="role-stack">
                  {roles.map((role) => {
                    const voice = voices.find(
                      (item) => item.voiceId === role.voiceResourceId,
                    );
                    return (
                      <article className="role-card" key={role.roleId}>
                        <input
                          aria-label={`${role.name} 角色名展示`}
                          value={role.name}
                          onChange={(event) =>
                            updateRole(role.roleId, {
                              name: event.target.value,
                            })
                          }
                        />
                        <input
                          aria-label={`${role.name} 别名`}
                          placeholder="别名/称呼，用逗号分隔"
                          value={role.aliases.join("，")}
                          onChange={(event) =>
                            updateRole(role.roleId, {
                              aliases: event.target.value
                                .split(/[，,、]/)
                                .map((item) => item.trim())
                                .filter(Boolean),
                            })
                          }
                        />
                        <input
                          aria-label={`${role.name} 性别`}
                          placeholder="性别"
                          value={role.gender}
                          onChange={(event) =>
                            updateRole(role.roleId, {
                              gender: event.target.value,
                            })
                          }
                        />
                        <textarea
                          aria-label={`${role.name} 人设身份性格`}
                          placeholder="人设/身份/性格"
                          value={role.profile}
                          onChange={(event) =>
                            updateRole(role.roleId, {
                              profile: event.target.value,
                            })
                          }
                        />
                        <div className="inline-select">
                          <label>
                            音色选择
                            <select
                              value={role.voiceResourceId}
                              onChange={(event) =>
                                updateRole(role.roleId, {
                                  voiceResourceId: event.target.value,
                                })
                              }
                            >
                              <option value="">未选择音色</option>
                              {voices.map((item) => {
                                const owner = roles.find(
                                  (candidateRole) =>
                                    candidateRole.roleId !== role.roleId &&
                                    candidateRole.voiceResourceId ===
                                      item.voiceId,
                                );
                                return (
                                  <option
                                    disabled={Boolean(owner)}
                                    key={item.voiceId}
                                    value={item.voiceId}
                                  >
                                    {owner
                                      ? `${item.name}（已分配给${owner.name}）`
                                      : item.name}
                                  </option>
                                );
                              })}
                            </select>
                          </label>
                        </div>
                        <p>
                          <strong>音色描述</strong>
                          {voice?.description ||
                            role.voiceDescription ||
                            role.description ||
                            "未选择音色"}
                        </p>
                        <p>
                          <strong>语音具体内容</strong>
                          {voice?.referenceText ||
                            role.voiceSampleText ||
                            role.referenceText ||
                            "未选择音色"}
                        </p>
                        <p>
                          <strong>音色匹配</strong>
                          {role.voiceMatchReason ?? "用户可手动调整"}
                        </p>
                        {voice && (
                          <AuthorizedAudio source={voiceAudioSrc(voice)} />
                        )}
                        <button
                          className="tool-button amber"
                          type="button"
                          onClick={() => void deleteRole(role.roleId)}
                        >
                          删除角色
                        </button>
                      </article>
                    );
                  })}
                </div>
                {aiRoleCandidates.length > 0 && (
                  <div
                    className="role-analysis-panel"
                    aria-label="角色分析建议"
                  >
                    <div className="section-title">角色分析建议</div>
                    <small>
                      请检查角色列表，必要时手动调整角色或音色；随后点击章节顶部“配音编排
                      Agent”。模型建议仅作参考。
                    </small>
                    {aiRoleCandidates.map((candidate, index) => (
                      <article
                        className="role-candidate-card"
                        key={`${candidate.name ?? "unknown"}-${index}`}
                      >
                        <strong>{candidate.name ?? "未知角色"}</strong>
                        <p>
                          别名/称呼：
                          {candidate.aliases.length
                            ? candidate.aliases.join("、")
                            : "待确认"}
                        </p>
                        <p>性别：{candidate.gender ?? "待确认"}</p>
                        <p>人设/身份/性格：{candidate.profile ?? "待确认"}</p>
                        <p>
                          推荐音色方向：{candidate.voice_direction ?? "待确认"}
                        </p>
                        <p>
                          证据片段：{candidate.evidence.join(" / ") || "待确认"}
                        </p>
                        <p>
                          置信度：{Math.round(candidate.confidence * 100)}%；
                          {candidate.needs_human_review
                            ? "需要人工确认"
                            : "仍可人工编辑"}
                        </p>
                      </article>
                    ))}
                  </div>
                )}
              </section>
            </>
          )}
        </aside>

        <section className="main-panel">
          {!hasSplitChapters ? (
            <div className="empty-state">
              <div className="section-title">当前章节</div>
              <h2>尚未划分章节</h2>
              <p>上传小说后点击左侧“文档解析”，当前章节区暂不渲染具体正文。</p>
            </div>
          ) : !activeChapter ? (
            <div className="empty-state">
              <div className="section-title">当前章节</div>
              <h2>请选择小说章节</h2>
              <p>
                选择某个章节后，左侧显示完整正文，右侧显示配音编排 Agent
                生成后的台词。
              </p>
            </div>
          ) : (
            <>
              <header className="chapter-header">
                <div>
                  <div className="section-title">当前章节</div>
                  <h2>{activeChapter.title}</h2>
                </div>
                <div className="chapter-primary-action">
                  <button
                    className="production-primary-button"
                    type="button"
                    disabled={productionPrimaryAction.disabled}
                    onClick={() => void handleProductionPrimaryAction()}
                  >
                    {productionPrimaryAction.label}
                  </button>
                  <span>{productionPrimaryAction.detail}</span>
                </div>
                <details className="advanced-action-panel">
                  <summary>高级操作</summary>
                  <div className="gate">
                    <button
                      className="tool-button purple"
                      type="button"
                      onClick={() => void runAiRoleAnalysis()}
                      disabled={agentRunRunning || visibleParagraphs.length === 0}
                    >
                      角色分析 Agent
                    </button>
                    <button
                      className="tool-button purple"
                      type="button"
                      onClick={() => void runAiRoleMatching()}
                      disabled={
                        agentRunRunning ||
                        !agentRunWaitingForRoles ||
                        !agentRunThreadId
                      }
                    >
                      配音编排 Agent
                    </button>
                    <button
                      className="tool-button sky"
                      type="button"
                      onClick={() => void generateChapterDubbing()}
                      disabled={!confirmed || hasPendingHumanReview}
                    >
                      批量生成配音
                    </button>
                    <button
                      className="tool-button amber"
                      type="button"
                      onClick={() => void exportChapterAudio()}
                      disabled={!confirmed || hasPendingHumanReview}
                    >
                      导出制作包
                    </button>
                    <button
                      className="tool-button sky"
                      type="button"
                      onClick={() => toggleChapterPlayback()}
                      disabled={!hasGeneratedAudioUtterance}
                    >
                      {chapterPlaybackState === "playing"
                        ? "暂停播放"
                        : chapterPlaybackState === "paused"
                          ? "继续播放"
                          : "一键播放"}
                    </button>
                    <button
                      className="tool-button sky"
                      type="button"
                      onClick={() => playPreviousQueuedChapterAudio()}
                      disabled={!hasGeneratedAudioUtterance}
                    >
                      上一句
                    </button>
                    <button
                      className="tool-button sky"
                      type="button"
                      onClick={() => playNextQueuedChapterAudio()}
                      disabled={!hasGeneratedAudioUtterance}
                    >
                      下一句
                    </button>
                    <span>
                      {confirmed && !hasPendingHumanReview
                        ? "台词已确认，可以批量配音或导出"
                        : "请完成角色分析、配音编排并确认所有配音片段"}
                    </span>
                  </div>
                </details>
                <div className="delivery-hint" aria-label="整章播放列表控制">
                  整章播放列表支持播放、暂停、继续、上一句、下一句；当前播放台词高亮。
                  导出制作包包含完整 WAV/MP3、逐句音频 + manifest、CSV 台本、SRT/LRC 字幕、角色表、音色表和失败清单；
                  音频后期默认应用片段间停顿、头尾静音裁剪和响度归一化。
                </div>
                <div className="export-settings-panel" aria-label="导出制作包参数">
                  <div className="export-preset-row">
                    {(Object.entries(EXPORT_PRESETS) as [ExportPreset, ExportOptions][]).map(
                      ([preset, options]) => (
                        <button
                          className={exportPreset === preset ? "active" : ""}
                          key={preset}
                          type="button"
                          onClick={() => {
                            setExportPreset(preset);
                            setExportOptions(options);
                          }}
                        >
                          <strong>{options.label}</strong>
                          <small>{options.description}</small>
                        </button>
                      ),
                    )}
                  </div>
                  <div className="export-advanced-grid">
                    <label>
                      片段间停顿 ms
                      <input
                        type="number"
                        min="0"
                        value={exportOptions.pauseMs}
                        onChange={(event) =>
                          setExportOptions((current) => ({
                            ...current,
                            pauseMs: Math.max(0, Number(event.target.value) || 0),
                          }))
                        }
                      />
                    </label>
                    <label>
                      语速
                      <input
                        type="number"
                        min="0.5"
                        step="0.05"
                        value={exportOptions.speed}
                        onChange={(event) =>
                          setExportOptions((current) => ({
                            ...current,
                            speed: Math.max(0.5, Number(event.target.value) || 1),
                          }))
                        }
                      />
                    </label>
                    <label>
                      目标峰值
                      <input
                        type="number"
                        min="0.1"
                        max="1"
                        step="0.01"
                        value={exportOptions.targetPeak}
                        onChange={(event) =>
                          setExportOptions((current) => ({
                            ...current,
                            targetPeak: Math.min(
                              1,
                              Math.max(0.1, Number(event.target.value) || 0.9),
                            ),
                          }))
                        }
                      />
                    </label>
                    <label className="checkline">
                      <input
                        type="checkbox"
                        checked={exportOptions.trimSilence}
                        onChange={(event) =>
                          setExportOptions((current) => ({
                            ...current,
                            trimSilence: event.target.checked,
                          }))
                        }
                      />
                      头尾静音裁剪
                    </label>
                    <label className="checkline">
                      <input
                        type="checkbox"
                        checked={exportOptions.normalizeAudio}
                        onChange={(event) =>
                          setExportOptions((current) => ({
                            ...current,
                            normalizeAudio: event.target.checked,
                          }))
                        }
                      />
                      响度归一化
                    </label>
                  </div>
                </div>
                <div className="status-filter-bar" aria-label="状态筛选">
                  <span>状态筛选</span>
                  {PARAGRAPH_STATUS_FILTERS.map((status) => (
                    <button
                      className={[
                        "status-pill",
                        status,
                        activeParagraphStatusFilter === status ? "active" : "",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                      disabled={paragraphStatusCounts[status] === 0}
                      key={status}
                      type="button"
                      onClick={() => toggleParagraphStatusFilter(status)}
                    >
                      <span>{PARAGRAPH_STATUS_META[status].label}</span>
                      <strong>{paragraphStatusCounts[status]}</strong>
                    </button>
                  ))}
                </div>
              </header>
              <audio
                className="chapter-playback-audio"
                onEnded={() => playNextQueuedChapterAudio()}
                onError={() => playNextQueuedChapterAudio()}
                ref={chapterPlayerRef}
              />

              <section className="chapter-workspace-grid">
                <article
                  className="panel chapter-reader"
                  aria-label="当前章节完整小说内容"
                >
                  <div className="section-heading">
                    <div className="section-title">当前章节完整小说内容</div>
                    <div className="status-legend" aria-label="正文状态图例">
                      {Object.entries(PARAGRAPH_STATUS_META).map(
                        ([status, meta]) => (
                          <span
                            className={`status-legend-item ${status}`}
                            key={status}
                          >
                            <i />
                            {meta.label}
                          </span>
                        ),
                      )}
                    </div>
                  </div>
                  <div className="chapter-reader-body">
                    {paragraphStatusItems.length === 0
                      ? "当前章节正文为空。"
                      : paragraphStatusItems.map((item) => (
                          <section
                            className={[
                              "reader-paragraph",
                              item.status,
                              highlightParagraphId === item.paragraphId
                                ? "attention"
                                : "",
                              activeParagraphStatusFilter &&
                              activeParagraphStatusFilter !== item.status
                                ? "dimmed"
                                : "",
                            ]
                              .filter(Boolean)
                              .join(" ")}
                            data-reader-paragraph-id={item.paragraphId}
                            key={item.paragraphId}
                          >
                            <div className="reader-paragraph-meta">
                              <span className={`status-dot ${item.status}`} />
                              <strong>{item.label}</strong>
                              <span>{item.paragraphId}</span>
                            </div>
                            <p>{item.text}</p>
                          </section>
                        ))}
                  </div>
                </article>

                <article
                  className="panel statement-panel"
                  aria-label="划分台词与角色匹配"
                >
                  <div className="section-heading">
                    <div className="section-title">划分台词与角色匹配</div>
                    <div className="toolbar-row compact">
                      <button
                        className="tool-button amber"
                        type="button"
                        disabled={!hasUnselectedRoleUtterance}
                        onClick={() => jumpToFirstUnselectedRoleUtterance()}
                      >
                        跳转到未选择角色的台词
                      </button>
                      <button
                        className="tool-button amber"
                        type="button"
                        disabled={!hasUngeneratedAudioUtterance}
                        onClick={() => jumpToFirstUngeneratedAudioUtterance()}
                      >
                        跳转到未生成配音的台词
                      </button>
                      <button
                        className="tool-button teal"
                        type="button"
                        disabled={flattenedUtterances.length === 0}
                        onClick={() => confirmAllReadyUtterances()}
                      >
                        确认已选台词与角色
                      </button>
                    </div>
                  </div>
                  {paragraphStatusItems.length > 0 && (
                    <div
                      className="chapter-status-map"
                      aria-label="章节状态小地图"
                    >
                      {paragraphStatusItems.map((item, index) => (
                        <button
                          className={[
                            "status-map-cell",
                            item.status,
                            highlightParagraphId === item.paragraphId
                              ? "attention"
                              : "",
                            activeParagraphStatusFilter &&
                            activeParagraphStatusFilter !== item.status
                              ? "dimmed"
                              : "",
                          ]
                            .filter(Boolean)
                            .join(" ")}
                          key={item.paragraphId}
                          title={`${item.paragraphId} ${item.label}`}
                          type="button"
                          aria-label={`跳转到${item.paragraphId}：${item.label}`}
                          onClick={() =>
                            focusParagraphStatusItem(
                              item,
                              `已跳转到${item.label}段落：${item.paragraphId}`,
                            )
                          }
                        >
                          {index + 1}
                        </button>
                      ))}
                    </div>
                  )}
                  {flattenedUtterances.length === 0 ? (
                    <div className="statement-empty">
                      <span>
                        当前章节可手动添加台词、选择角色并生成配音；也可以稍后使用配音编排
                        Agent 自动辅助。
                      </span>
                      {primaryStatementParagraphId && (
                        <button
                          className="tool-button amber"
                          type="button"
                          onClick={() =>
                            addUtteranceAfter(primaryStatementParagraphId)
                          }
                        >
                          添加第一条台词
                        </button>
                      )}
                    </div>
                  ) : (
                    <div className="statement-list">
                      {flattenedUtterances.map((utterance) => (
                        <article
                          className={[
                            "utterance-card",
                            highlightUtteranceId === utterance.utteranceId
                              ? "attention"
                              : "",
                            chapterPlaybackUtteranceId === utterance.utteranceId
                              ? "playing"
                              : "",
                          ]
                            .filter(Boolean)
                            .join(" ")}
                          data-utterance-id={utterance.utteranceId}
                          key={utterance.utteranceId}
                        >
                          <div className="utterance-toolbar">
                            <strong>{utterance.utteranceId}</strong>
                            <button
                              className="tool-button amber"
                              type="button"
                              onClick={() =>
                                addCurrentUtteranceAfter(utterance)
                              }
                            >
                              在此后添加台词
                            </button>
                            <button
                              className="tool-button sky"
                              type="button"
                              onClick={() => void splitLongUtterance(utterance)}
                            >
                              一键拆分长台词
                            </button>
                            <button
                              className="tool-button teal"
                              type="button"
                              onClick={() => void mergeWithNextUtterance(utterance)}
                            >
                              合并相邻台词
                            </button>
                            <button
                              type="button"
                              onClick={() =>
                                deleteUtterance(
                                  utterance.paragraphId,
                                  utterance.utteranceId,
                                )
                              }
                            >
                              删除台词
                            </button>
                          </div>
                          <label className="utterance-wide">
                            台词文本
                            <input
                              value={utterance.text}
                              onChange={(event) =>
                                updateUtterance(
                                  utterance.paragraphId,
                                  utterance.utteranceId,
                                  "text",
                                  event.target.value,
                                )
                              }
                              aria-label={`${utterance.utteranceId} 台词文本`}
                            />
                          </label>
                          <label>
                            选择角色
                            <select
                              value={utterance.roleId}
                              onChange={(event) =>
                                updateUtterance(
                                  utterance.paragraphId,
                                  utterance.utteranceId,
                                  "roleId",
                                  event.target.value,
                                )
                              }
                            >
                              <option value="">请选择角色</option>
                              {roleOptions.map((option) => (
                                <option key={option.value} value={option.value}>
                                  {option.label}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label className="checkline utterance-check">
                            <input
                              type="checkbox"
                              checked={!utterance.needsHumanReview}
                              onChange={(event) => {
                                if (
                                  event.target.checked &&
                                  (!utterance.roleId || !utterance.text.trim())
                                ) {
                                  updateUtterance(
                                    utterance.paragraphId,
                                    utterance.utteranceId,
                                    "needsHumanReview",
                                    true,
                                  );
                                  setConfirmed(false);
                                  setApiStatus(
                                    "请选择角色并填写台词文本后再确认",
                                  );
                                  return;
                                }
                                updateUtterance(
                                  utterance.paragraphId,
                                  utterance.utteranceId,
                                  "needsHumanReview",
                                  !event.target.checked,
                                );
                                if (
                                  event.target.checked &&
                                  utterance.roleId &&
                                  utterance.text.trim()
                                ) {
                                  setConfirmed(true);
                                } else {
                                  setConfirmed(false);
                                }
                              }}
                            />
                            已确认台词与角色
                          </label>
                          {(() => {
                            const isGeneratingThisUtterance = Boolean(
                              generatingUtteranceIds[utterance.utteranceId],
                            );
                            return (
                              <button
                                className="tool-button sky"
                                type="button"
                                disabled={isGeneratingThisUtterance}
                                onClick={() => void generateAudio(utterance)}
                              >
                                {isGeneratingThisUtterance
                                  ? "正在生成"
                                  : "生成配音"}
                              </button>
                            );
                          })()}
                          <output>{utterance.audioStatus}</output>
                          {utteranceAudioSource(utterance) && (
                            <AuthorizedAudio
                              source={utteranceAudioSource(utterance) ?? ""}
                            />
                          )}
                        </article>
                      ))}
                    </div>
                  )}
                </article>
              </section>
            </>
          )}
        </section>
      </main>
    );
  }

  function renderVoiceLibraryPage() {
    return (
      <main className="library-page">
        <section className="panel">
          <div className="section-heading">
            <div className="section-title">音色列表</div>
            <button
              className="tool-button teal"
              type="button"
              onClick={() => void exportVoiceLibrary()}
            >
              导出音色库
            </button>
          </div>
          <small className="status-message" aria-label="音色库反馈">
            {apiStatus}
          </small>
          <div className="voice-grid">
            {voices.map((voice) => (
              <article className="voice-card" key={voice.voiceId}>
                <label className="checkline">
                  <input
                    type="checkbox"
                    checked={Boolean(selectedVoiceIds[voice.voiceId])}
                    onChange={(event) =>
                      setSelectedVoiceIds((current) => ({
                        ...current,
                        [voice.voiceId]: event.target.checked,
                      }))
                    }
                  />
                  勾选删除
                </label>
                <label>
                  音色名称
                  <input
                    value={voice.name}
                    onChange={(event) =>
                      setVoices((current) =>
                        current.map((item) =>
                          item.voiceId === voice.voiceId
                            ? { ...item, name: event.target.value }
                            : item,
                        ),
                      )
                    }
                  />
                </label>
                <label>
                  音色性别
                  <input
                    value={voice.gender}
                    onChange={(event) =>
                      setVoices((current) =>
                        current.map((item) =>
                          item.voiceId === voice.voiceId
                            ? { ...item, gender: event.target.value }
                            : item,
                        ),
                      )
                    }
                  />
                </label>
                <label>
                  音色描述
                  <textarea
                    value={voice.description}
                    onChange={(event) =>
                      setVoices((current) =>
                        current.map((item) =>
                          item.voiceId === voice.voiceId
                            ? { ...item, description: event.target.value }
                            : item,
                        ),
                      )
                    }
                  />
                </label>
                <label>
                  适合角色类型
                  <input
                    value={voice.suitableRoleTypes.join("，")}
                    onChange={(event) =>
                      setVoices((current) =>
                        current.map((item) =>
                          item.voiceId === voice.voiceId
                            ? {
                                ...item,
                                suitableRoleTypes: event.target.value
                                  .split(/[，,、]/)
                                  .map((part) => part.trim())
                                  .filter(Boolean),
                              }
                            : item,
                        ),
                      )
                    }
                  />
                </label>
                <label>
                  语音具体内容
                  <textarea
                    value={voice.referenceText}
                    onChange={(event) =>
                      setVoices((current) =>
                        current.map((item) =>
                          item.voiceId === voice.voiceId
                            ? { ...item, referenceText: event.target.value }
                            : item,
                        ),
                      )
                    }
                  />
                </label>
                <label>
                  参考音频文件
                  <input
                    value={voice.referenceAudioPath}
                    onChange={(event) =>
                      setVoices((current) =>
                        current.map((item) =>
                          item.voiceId === voice.voiceId
                            ? {
                                ...item,
                                referenceAudioPath: event.target.value,
                              }
                            : item,
                        ),
                      )
                    }
                  />
                </label>
                <AuthorizedAudio source={voiceAudioSrc(voice)} />
                <button
                  className="tool-button teal"
                  type="button"
                  onClick={() => void updateVoiceResource(voice)}
                >
                  保存音色
                </button>
              </article>
            ))}
          </div>
          <button
            className="tool-button amber"
            type="button"
            onClick={() => void deleteSelectedVoices()}
          >
            删除选中音色
          </button>
        </section>

        <section className="two-column">
          <div className="panel">
            <div className="section-title">添加音色</div>
            <input
              placeholder="音色名称"
              value={newVoice.name}
              onChange={(event) =>
                setNewVoice((current) => ({
                  ...current,
                  name: event.target.value,
                }))
              }
            />
            <input
              placeholder="音色性别"
              value={newVoice.gender}
              onChange={(event) =>
                setNewVoice((current) => ({
                  ...current,
                  gender: event.target.value,
                }))
              }
            />
            <textarea
              placeholder="音色描述"
              value={newVoice.description}
              onChange={(event) =>
                setNewVoice((current) => ({
                  ...current,
                  description: event.target.value,
                }))
              }
            />
            <input
              placeholder="适合角色类型，用逗号分隔"
              value={newVoice.suitableRoleTypes}
              onChange={(event) =>
                setNewVoice((current) => ({
                  ...current,
                  suitableRoleTypes: event.target.value,
                }))
              }
            />
            <textarea
              placeholder="语音具体内容"
              value={newVoice.referenceText}
              onChange={(event) =>
                setNewVoice((current) => ({
                  ...current,
                  referenceText: event.target.value,
                }))
              }
            />
            <input
              ref={voiceAudioInputRef}
              className="hidden-input"
              type="file"
              accept="audio/*"
              aria-label="添加参考音频文件"
              onChange={(event) => void handleReferenceAudioFile(event)}
            />
            <button
              className="tool-button sky"
              type="button"
              onClick={() => voiceAudioInputRef.current?.click()}
            >
              添加参考音频文件
            </button>
            {newVoice.referenceAudioPath && (
              <small>已选择：{newVoice.referenceAudioPath}</small>
            )}
            {newVoiceAudioPreviewUrl && (
              <AuthorizedAudio source={newVoiceAudioPreviewUrl} />
            )}
            <button
              className="tool-button teal"
              type="button"
              onClick={() => void saveVoiceResource(newVoice)}
            >
              保存音色
            </button>
          </div>

          <div className="panel">
            <div className="section-title">生成音色</div>
            <input
              placeholder="音色名称"
              value={generatedVoice.name}
              onChange={(event) =>
                setGeneratedVoice((current) => ({
                  ...current,
                  name: event.target.value,
                }))
              }
            />
            <input
              placeholder="音色性别"
              value={generatedVoice.gender}
              onChange={(event) =>
                setGeneratedVoice((current) => ({
                  ...current,
                  gender: event.target.value,
                }))
              }
            />
            <textarea
              placeholder="音色描述"
              value={generatedVoice.description}
              onChange={(event) =>
                setGeneratedVoice((current) => ({
                  ...current,
                  description: event.target.value,
                }))
              }
            />
            <input
              placeholder="适合角色类型，用逗号分隔"
              value={generatedVoice.suitableRoleTypes}
              onChange={(event) =>
                setGeneratedVoice((current) => ({
                  ...current,
                  suitableRoleTypes: event.target.value,
                }))
              }
            />
            <textarea
              placeholder="语音具体内容"
              value={generatedVoice.referenceText}
              onChange={(event) =>
                setGeneratedVoice((current) => ({
                  ...current,
                  referenceText: event.target.value,
                }))
              }
            />
            <ProgressBar label="生成音色进度" value={generatedVoiceProgress} />
            <button
              className="tool-button purple"
              type="button"
              onClick={() => void generateVoiceResource()}
            >
              生成音色
            </button>
            {generatedVoicePreviewUrl && (
              <div className="generated-preview">
                <small>试听生成音色：{generatedVoicePreview?.name}</small>
                <AuthorizedAudio source={generatedVoicePreviewUrl} />
              </div>
            )}
            <button
              className="tool-button teal"
              type="button"
              onClick={() => void saveGeneratedVoiceResource()}
            >
              保存音色
            </button>
          </div>
        </section>
      </main>
    );
  }

  function renderMemoryPage() {
    const trustedFacts = memoryContext?.facts_for_prompt ?? storyBibleFacts.filter(
      (fact) => ["user_confirmed", "system_verified"].includes(fact.confidence),
    );
    const candidateFacts = memoryContext?.candidate_facts ?? storyBibleFacts.filter(
      (fact) => fact.confidence === "model_suggested",
    );
    const rejectedFacts = memoryContext?.rejected_facts ?? storyBibleFacts.filter(
      (fact) => fact.confidence === "rejected",
    );
    const factCard = (fact: StoryBibleFact) => (
      <article className="memory-fact-card" key={fact.fact_id}>
        <strong>{fact.subject}</strong>
        <span>
          {fact.predicate}：{fact.object}
        </span>
        <small>
          {fact.confidence} · {fact.source_type ?? "manual"} · {fact.source_id ?? fact.fact_id}
        </small>
        {fact.notes && <small>备注：{fact.notes}</small>}
      </article>
    );

    return (
      <main className="memory-page">
        <section className="panel memory-control-panel">
          <div className="section-heading">
            <div>
              <div className="section-title">项目记忆</div>
              <h2>Story Bible / 证据面板</h2>
            </div>
            <button
              className="tool-button sky"
              type="button"
              onClick={() => void loadStoryBible()}
            >
              刷新记忆
            </button>
          </div>
          <small className="status-message" aria-label="项目记忆反馈">
            {memoryStatus}
          </small>
          <div className="toolbar-row">
            <input
              aria-label="项目记忆检索词"
              placeholder="输入角色、别名、术语或设定"
              value={memoryQuery}
              onChange={(event) => setMemoryQuery(event.target.value)}
            />
            <button
              className="tool-button purple"
              type="button"
              onClick={() => void searchStoryMemoryContext()}
            >
              检索证据
            </button>
          </div>
        </section>

        <section className="panel memory-evidence-panel">
          <div className="section-title">角色证据</div>
          <small>可信事实会进入 Agent prompt；候选事实只作为人工判断参考。</small>
          <div className="memory-fact-grid">
            {trustedFacts.length === 0 ? <small>暂无可信角色证据。</small> : trustedFacts.map(factCard)}
          </div>
        </section>

        <section className="panel memory-evidence-panel">
          <div className="section-title">设定记忆</div>
          <small>模型建议和被拒绝事实分开展示，避免错误记忆污染后续 Agent。</small>
          <div className="memory-two-column">
            <div>
              <strong>候选事实</strong>
              <div className="memory-fact-grid">
                {candidateFacts.length === 0 ? <small>暂无候选事实。</small> : candidateFacts.map(factCard)}
              </div>
            </div>
            <div>
              <strong>已拒绝事实</strong>
              <div className="memory-fact-grid">
                {rejectedFacts.length === 0 ? <small>暂无已拒绝事实。</small> : rejectedFacts.map(factCard)}
              </div>
            </div>
          </div>
        </section>

        <section className="panel memory-correction-panel">
          <div className="section-title">用户纠错</div>
          <small>人工写入默认保存为 user_confirmed，后续 Agent 优先使用。</small>
          <div className="memory-correction-grid">
            <input
              placeholder="主体，例如 林舟"
              value={memoryCorrection.subject}
              onChange={(event) =>
                setMemoryCorrection((current) => ({
                  ...current,
                  subject: event.target.value,
                }))
              }
            />
            <input
              placeholder="关系，例如 alias / pronunciation / identity"
              value={memoryCorrection.predicate}
              onChange={(event) =>
                setMemoryCorrection((current) => ({
                  ...current,
                  predicate: event.target.value,
                }))
              }
            />
            <input
              placeholder="事实内容"
              value={memoryCorrection.object}
              onChange={(event) =>
                setMemoryCorrection((current) => ({
                  ...current,
                  object: event.target.value,
                }))
              }
            />
            <input
              placeholder="备注，可选"
              value={memoryCorrection.notes}
              onChange={(event) =>
                setMemoryCorrection((current) => ({
                  ...current,
                  notes: event.target.value,
                }))
              }
            />
          </div>
          <button
            className="tool-button teal"
            type="button"
            onClick={() => void saveMemoryCorrection()}
          >
            写入用户纠错
          </button>
        </section>
      </main>
    );
  }

  function renderAgentTracePage() {
    const trace = selectedAgentTrace ?? agentTraces[0] ?? null;
    return (
      <main className="trace-page">
        <section className="panel trace-list-panel">
          <div className="section-heading">
            <div>
              <div className="section-title">运行审计</div>
              <h2>Run History</h2>
            </div>
            <button
              className="tool-button sky"
              type="button"
              onClick={() => void loadAgentRunHistory()}
            >
              刷新
            </button>
          </div>
          <small className="status-message" aria-label="运行审计反馈">
            {agentTraceStatus}
          </small>
          <div className="trace-run-list" aria-label="运行审计记录">
            {agentTraces.length === 0 ? (
              <article className="trace-run-card empty">
                <strong>暂无记录</strong>
                <small>
                  完成一次角色分析或配音编排后，这里会显示可审计的 Agent run。
                </small>
              </article>
            ) : (
              agentTraces.map((item) => (
                <button
                  className={
                    trace?.run_id === item.run_id &&
                    trace.agent_id === item.agent_id
                      ? "trace-run-card active"
                      : "trace-run-card"
                  }
                  key={`${item.run_id}-${item.agent_id}`}
                  type="button"
                  onClick={() => void selectAgentTrace(item)}
                >
                  <strong>{item.agent_name || item.agent_id}</strong>
                  <span>{item.chapter_id || "default chapter"}</span>
                  <small>
                    {formatTraceTimestamp(item.updated_at ?? item.created_at)}
                  </small>
                </button>
              ))
            )}
          </div>
        </section>

        <section
          className="panel trace-detail-panel"
          aria-label="运行审计详情"
        >
          <div className="section-heading">
            <div>
              <div className="section-title">追踪详情</div>
              <h2>{trace?.agent_name ?? "等待 Agent run"}</h2>
            </div>
            <small>{trace?.run_id ?? "run_id 待生成"}</small>
          </div>

          <div className="trace-metric-grid">
            <div>
              <span>Prompt版本</span>
              <strong>
                {trace
                  ? `${trace.prompt_id}.v${trace.prompt_version}`
                  : "未记录"}
              </strong>
            </div>
            <div>
              <span>Prompt SHA</span>
              <strong>{trace?.prompt_sha256 ?? "未记录"}</strong>
            </div>
            <div>
              <span>Token预算</span>
              <strong>
                {trace
                  ? `${trace.estimated_total_tokens}/${trace.context_window}`
                  : "等待估算"}
              </strong>
            </div>
            <div>
              <span>模型</span>
              <strong>{trace?.model_name || "未配置"}</strong>
            </div>
            <div>
              <span>JSON校验</span>
              <strong>{trace?.validation_status ?? "未运行"}</strong>
            </div>
            <div>
              <span>最终决策</span>
              <strong>{trace?.final_decision ?? "未运行"}</strong>
            </div>
          </div>

          <div className="trace-section">
            <div className="section-title">输入摘要</div>
            <p>{trace?.input_summary || "暂无输入摘要"}</p>
          </div>

          <div className="trace-section">
            <div className="section-title">上下文预算策略</div>
            <pre>
              {formatTraceJson(
                trace?.token_context_report ?? {
                  Prompt: "系统 prompt 必保留",
                  CurrentChapter: "当前章节优先",
                  RAGEvidence: "RAG 证据预留上限",
                  OutputTokens: "输出 tokens 必须预留",
                },
              )}
            </pre>
          </div>

          <div className="trace-section">
            <div className="section-title">Tool Calls</div>
            {(trace?.tool_calls ?? []).length === 0 ? (
              <p>暂无工具调用记录：参数摘要、返回摘要、失败原因将在工具执行后显示。</p>
            ) : (
              <div className="tool-call-list" aria-label="工具调用记录">
                {(trace?.tool_calls ?? []).map((toolCall) => (
                  <article className="tool-call-card" key={toolCall.tool_call_id}>
                    <div>
                      <strong>{toolCall.tool_name}</strong>
                      <span>{toolCall.status}</span>
                    </div>
                    <small>
                      {toolCall.permission_scope ?? "project scoped"} · {toolCall.duration_ms ?? 0} ms
                    </small>
                    <dl>
                      <dt>参数摘要</dt>
                      <dd>{toolCall.arguments_summary || "{}"}</dd>
                      <dt>返回摘要</dt>
                      <dd>{toolCall.output_summary || "{}"}</dd>
                      <dt>失败原因</dt>
                      <dd>{toolCall.failure || "无"}</dd>
                    </dl>
                  </article>
                ))}
              </div>
            )}
          </div>

          <div className="trace-section">
            <div className="section-title">模型输出</div>
            <pre>{formatTraceJson(trace?.raw_model_output)}</pre>
          </div>

          <div className="trace-section">
            <div className="section-title">解析结果</div>
            <pre>{formatTraceJson(trace?.parsed_output)}</pre>
          </div>

          <div className="trace-section">
            <div className="section-title">Reflection</div>
            <pre>
              {formatTraceJson({
                reflection_count: trace?.reflection_count ?? 0,
                reflection_trace: trace?.reflection_trace ?? [],
                validation_errors: trace?.validation_errors ?? [],
                human_review_count: trace?.human_review_count ?? 0,
              })}
            </pre>
          </div>
        </section>
      </main>
    );
  }

  function renderModelConfigPage() {
    return (
      <main className="model-page">
        <section className="panel">
          <div className="section-title">后端 API</div>
          <small className="status-message" aria-label="模型配置反馈">
            {apiStatus}
          </small>
          <label>
            Base URL
            <input
              aria-label="后端 API Base URL"
              placeholder="eg: https://faho62u6pf-8000.cnb.run/api/v1"
              value={backendApiBase}
              onChange={(event) => setBackendApiBase(event.target.value)}
            />
          </label>
          <div className="toolbar-row">
            <button
              className="tool-button teal"
              type="button"
              onClick={() => saveBackendApiBase()}
            >
              保存后端地址
            </button>
            <button
              className="tool-button sky"
              type="button"
              onClick={() => void testBackendConnection()}
            >
              测试连接
            </button>
          </div>
        </section>

        <section className="panel">
          <div className="section-title">文本模型</div>
          <label>
            Base URL
            <input
              placeholder="eg: https://api.deepseek.com"
              value={modelConfig.text_model.base_url}
              onChange={(event) =>
                setModelConfig((current) => ({
                  ...current,
                  text_model: {
                    ...current.text_model,
                    base_url: event.target.value,
                  },
                }))
              }
            />
          </label>
          <label>
            模型名称
            <input
              placeholder="eg: deepseek-v4-flash"
              value={modelConfig.text_model.model}
              onChange={(event) =>
                setModelConfig((current) => ({
                  ...current,
                  text_model: {
                    ...current.text_model,
                    model: event.target.value,
                  },
                }))
              }
            />
          </label>
          <label>
            API Key（仅本次运行）
            <input
              aria-label="文本模型 API Key"
              autoComplete="off"
              placeholder="sk-xxx..."
              type="password"
              value={textModelApiKey}
              onChange={(event) => setTextModelApiKey(event.target.value)}
            />
          </label>
          <p className="config-secret-status">
            临时密钥：
            {modelConfig.text_model.has_api_key ? "后端内存已配置" : "未输入"}
          </p>
          <div className="toolbar-row">
            <button
              className="tool-button teal"
              type="button"
              onClick={() => void saveTextModelConfig()}
            >
              保存模型配置
            </button>
            <button
              className="tool-button sky"
              type="button"
              onClick={() => void testBackendConnection()}
            >
              测试连接
            </button>
            <button
              className="tool-button purple"
              type="button"
              disabled={localTtsStarting}
              onClick={() => void testModelApis()}
            >
              {localTtsStarting ? "测试中" : "测试模型"}
            </button>
          </div>
        </section>

        <section className="panel">
          <div className="section-title">TTS模型</div>
          <label>
            Base URL
            <input
              value={modelConfig.tts.base_url}
              onChange={(event) =>
                setModelConfig((current) => ({
                  ...current,
                  tts: { ...current.tts, base_url: event.target.value },
                }))
              }
            />
          </label>
          <label>
            Base 模型权重路径
            <input
              value={modelConfig.tts.model_path}
              onChange={(event) =>
                setModelConfig((current) => ({
                  ...current,
                  tts: { ...current.tts, model_path: event.target.value },
                }))
              }
            />
          </label>
          <label>
            VoiceDesign 模型权重路径
            <input
              value={modelConfig.tts.voice_design_model_path}
              onChange={(event) =>
                setModelConfig((current) => ({
                  ...current,
                  tts: {
                    ...current.tts,
                    voice_design_model_path: event.target.value,
                  },
                }))
              }
            />
          </label>
          <ProgressBar
            label="TTS模型下载并部署进度"
            value={ttsDeployment.progress}
          />
          <small className="status-message" aria-label="TTS模型部署反馈">
            {ttsDeployment.message}
          </small>
          <div className="toolbar-row">
            <button
              className="tool-button teal"
              type="button"
              onClick={() => void saveLocalModelConfig()}
            >
              保存模型配置
            </button>
            <button
              className="tool-button amber"
              type="button"
              disabled={ttsDeployment.status === "running"}
              onClick={() => void deployTtsModels()}
            >
              {ttsDeployment.status === "running" ? "部署中" : "下载并部署"}
            </button>
            <button
              className="tool-button purple"
              type="button"
              disabled={localTtsStarting}
              onClick={() => void testModelApis()}
            >
              {localTtsStarting ? "测试中" : "测试模型"}
            </button>
          </div>
        </section>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <h1>
            <img
              className="brand-logo"
              src={`${runtimeConfig.pagesBase}shuyi-agent-zh.svg`}
              alt={APP_BRAND}
            />
            <span>v{APP_VERSION}</span>
          </h1>
          <p className="product-subtitle">
            基于 Agent 的多人有声书自动配音工作台
          </p>
        </div>
        <div className="topbar-actions">
          <div className="mode-selector" role="group" aria-label="配音模式">
            {[
              ["automatic", "自动配音"],
              ["step", "分步配音"],
            ].map(([mode, label]) => (
              <button
                aria-pressed={workflowState.mode === mode}
                className={workflowState.mode === mode ? "active" : ""}
                key={mode}
                type="button"
                onClick={() =>
                  setWorkflowState((current) =>
                    transitionWorkflow(current, {
                      type: "SET_MODE",
                      mode: mode as WorkflowMode,
                    }),
                  )
                }
              >
                {label}
              </button>
            ))}
          </div>
          <nav className="tabbar" aria-label="页面切换">
            {[
              ["main", "制作台"],
              ["voices", "音色库"],
              ["memory", "项目记忆"],
              ["agent-runs", "运行审计"],
              ["models", "设置"],
            ].map(([value, label]) => (
              <button
                className={page === value ? "active" : ""}
                key={value}
                type="button"
                onClick={() => setPage(value as Page)}
              >
                {label}
              </button>
            ))}
          </nav>
        </div>
      </header>
      {page === "main" && renderMainPage()}
      {page === "voices" && renderVoiceLibraryPage()}
      {page === "memory" && renderMemoryPage()}
      {page === "agent-runs" && renderAgentTracePage()}
      {page === "models" && renderModelConfigPage()}
    </div>
  );
}

export default App;
