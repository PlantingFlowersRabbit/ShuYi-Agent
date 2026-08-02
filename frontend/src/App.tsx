import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  createWorkflowState,
  transitionWorkflow,
  type WorkflowMode,
} from "./features/agent-workflow/workflowMachine";
import { APP_BRAND, APP_VERSION, runtimeConfig } from "./shared/config/runtimeConfig";

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
    if (error.status === 0 || (error.status === 404 && ["Not Found", "请求失败"].includes(message))) {
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

export function isRoleDeleteReferenceConflict(error: unknown): error is ApiRequestError {
  if (!(error instanceof ApiRequestError) || error.status !== 409) return false;
  const detail = error.detail as { delete_result?: { referenced_count?: unknown } } | null;
  const referencedCount = detail?.delete_result?.referenced_count;
  return typeof referencedCount === "number" && referencedCount > 0;
}

type Page = "main" | "voices" | "models";
type VoiceMode = "voice_cloning" | "voice_design";

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
  auto_role_report?: { added_count: number; updated_count: number; generated_voice_count: number } | null;
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
  failure?: { paragraph_id: string; error_code: string; message: string } | null;
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
const DEFAULT_VOICE_DESIGN_MODEL_PATH = "/models/Qwen3-TTS-12Hz-1.7B-VoiceDesign";

const defaultVoices: VoiceResource[] = [];

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

function initialPageFromUrl(): Page {
  const page = new URLSearchParams(window.location.search).get("page");
  return page === "voices" || page === "models" ? page : "main";
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
  const isEpub = file.name.toLowerCase().endsWith(".epub") || file.type === "application/epub+zip";
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
  return candidates.sort((left, right) => compareChapterHeadingMatches(text, right, left))[0] ?? [];
}

function compareChapterHeadingMatches(text: string, left: ChapterHeadingMatch[], right: ChapterHeadingMatch[]): number {
  const leftScore = chapterHeadingScore(text, left);
  const rightScore = chapterHeadingScore(text, right);
  return leftScore[0] - rightScore[0] || leftScore[1] - rightScore[1] || leftScore[2] - rightScore[2];
}

function chapterHeadingScore(text: string, matches: ChapterHeadingMatch[]): [number, number, number] {
  const nonEmptyBodies = matches.filter((match, index) => {
    const next = matches[index + 1];
    const body = text.slice(match.index + match.text.length, next?.index ?? text.length).trim();
    return body.length > 0;
  }).length;
  const firstIndex = matches[0]?.index ?? text.length;
  return [nonEmptyBodies, matches.length, -firstIndex];
}

function parseChapters(text: string): Chapter[] {
  const matches = findChapterHeadingMatches(text);
  if (matches.length === 0) {
    return text.trim() ? [{ chapterId: "chapter-0001", title: "未分章正文", body: text.trim() }] : [];
  }
  return matches.map((match, index) => {
    const next = matches[index + 1];
    const bodyStart = match.index + match.text.length;
    const bodyEnd = next?.index ?? text.length;
    return {
      chapterId: `chapter-${String(index + 1).padStart(4, "0")}`,
      title: match.title,
      body: text.slice(bodyStart, bodyEnd).replace(/^-{3,}\s*/, "").trim(),
    };
  });
}

function parseChapterIndex(text: string): Chapter[] {
  const matches = findChapterHeadingMatches(text);
  if (matches.length === 0) {
    const stripped = text.trim();
    return stripped
      ? [{ chapterId: "chapter-0001", title: "未分章正文", body: "", bodyStart: 0, bodyEnd: text.length }]
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
  const body = text.slice(chapter.bodyStart ?? 0, chapter.bodyEnd ?? text.length);
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
    playableVoicePath: role.playable_voice_path ?? role.reference_audio_path ?? "",
    voiceMatchScore: role.voice_match_score,
    voiceMatchReason: role.voice_match_reason,
    voiceGeneratedByAi: Boolean(role.voice_generated_by_ai),
  };
}

function toApiVoice(voice: Omit<Partial<VoiceResource>, "suitableRoleTypes"> & { suitableRoleTypes?: string[] | string }): Record<string, unknown> {
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

function utteranceGroupsToApi(groups: Record<string, UtteranceDraft[]>): Record<string, Record<string, unknown>[]> {
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
        audio_status: utterance.audioPath ? "success" : undefined,
        audio_path: utterance.audioPath,
        audio_duration: utterance.audioDuration,
        audio_provider: utterance.audioProvider,
        audio_model: utterance.audioModel,
        needs_human_review: utterance.needsHumanReview,
      })),
    ]),
  );
}

function voiceAudioSrc(voice: VoiceResource): string {
  return runtimeConfig.apiUrl(`/voice-profiles/${voice.voiceId}/audio`);
}

function roleFromVoice(roleId: string, name: string, voice: VoiceResource): RoleCard {
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
    throw new ApiRequestError(response.status, data.detail ?? data.error ?? response.statusText);
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
  return Uint8Array.from(window.atob(value), (character) => character.charCodeAt(0));
}

async function createSecretExchangePayload(secret: string): Promise<SecretExchangePayload | null> {
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
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
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

  return playableUrl ? <audio controls src={playableUrl} /> : <small>音频暂不可用</small>;
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

function makeWholeParagraphUtteranceGroups(paragraphs: ParagraphModule[]): Record<string, UtteranceDraft[]> {
  return Object.fromEntries(
    paragraphs.map((paragraph) => [paragraph.paragraphId, [makeUtteranceDraft(paragraph)]]),
  );
}

function apiUtterancesToGroups(
  groups: Record<string, ApiUtterance[]>,
  paragraphs: ParagraphModule[],
  roles: RoleCard[],
): Record<string, UtteranceDraft[]> {
  return Object.fromEntries(
    Object.entries(groups).map(([paragraphId, utterances]) => {
      const paragraph = paragraphs.find((item) => item.paragraphId === paragraphId) ?? {
        paragraphId,
        text: "",
        collapsed: false,
        deleted: false,
      };
      return [paragraphId, utterances.map((utterance) => fromApiUtterance(utterance, paragraph, roles))];
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

function fromApiUtterance(utterance: ApiUtterance, paragraph: ParagraphModule, roles: RoleCard[]): UtteranceDraft {
  const role = roles.find((item) => item.roleId === utterance.speaker_role_id);
  const audioUrl = utterance.audio_url ?? audioPathToUrl(utterance.audio_path);
  return {
    utteranceId: utterance.utterance_id,
    paragraphId: utterance.paragraph_id ?? paragraph.paragraphId,
    text: utterance.text,
    roleId: role?.roleId ?? utterance.speaker_role_id ?? "",
    speakerName: utterance.speaker_name || role?.name || "",
    audioStatus: utterance.audio_status === "success" ? "音频生成完成" : "尚未生成",
    audioUrl,
    audioPath: utterance.audio_path,
    audioDuration: utterance.audio_duration,
    audioProvider: utterance.audio_provider,
    audioModel: utterance.audio_model,
    needsHumanReview: Boolean(utterance.needs_human_review),
  };
}

function normalizeModelConfig(config: Partial<ModelConfig> & { llm?: Partial<ModelConfig["text_model"]>; chapter_agent?: Partial<ModelConfig["text_model"]> }): ModelConfig {
  const textModel = config.text_model ?? config.chapter_agent ?? config.llm ?? {};
  return {
    text_model: {
      base_url: textModel.base_url ?? defaultModelConfig.text_model.base_url,
      model: textModel.model ?? defaultModelConfig.text_model.model,
      has_api_key: textModel.has_api_key ?? false,
    },
    tts: {
      base_url: config.tts?.base_url ?? defaultModelConfig.tts.base_url,
      model_path: config.tts?.model_path ?? defaultModelConfig.tts.model_path,
      voice_design_model_path: config.tts?.voice_design_model_path ?? defaultModelConfig.tts.voice_design_model_path,
    },
  };
}

function normalizeTtsDeployment(status: Partial<TtsDeploymentStatus> | null | undefined): TtsDeploymentStatus {
  return {
    ...defaultTtsDeployment,
    ...(status ?? {}),
    progress: Number.isFinite(status?.progress) ? Number(status?.progress) : defaultTtsDeployment.progress,
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
      <div className="progress-bar" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={normalized}>
        <span style={{ width: `${normalized}%` }} />
      </div>
    </div>
  );
}

function App() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const voiceAudioInputRef = useRef<HTMLInputElement>(null);
  const fullNovelTextRef = useRef("");
  const uploadedNovelFileRef = useRef<UploadedNovelFile | null>(null);
  const automaticDubbingStartedRef = useRef(false);
  const automaticRoleMatchingAttemptedRef = useRef(false);
  const dubbingInFlightRef = useRef(false);
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
  const [utterancesByParagraph, setUtterancesByParagraph] = useState<Record<string, UtteranceDraft[]>>({});
  const [chapterBackendSynced, setChapterBackendSynced] = useState(false);
  const [selectedVoiceIds, setSelectedVoiceIds] = useState<Record<string, boolean>>({});
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
  const [generatedVoicePreview, setGeneratedVoicePreview] = useState<VoiceResource | null>(null);
  const [generatedVoicePreviewUrl, setGeneratedVoicePreviewUrl] = useState("");
  const [modelConfig, setModelConfig] = useState<ModelConfig>(defaultModelConfig);
  const [textModelApiKey, setTextModelApiKey] = useState("");
  const [apiStatus, setApiStatus] = useState("等待上传小说");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [chapterSplitProgress, setChapterSplitProgress] = useState(0);
  const [roleMatchingProgress, setRoleMatchingProgress] = useState(0);
  const [voiceGenerationProgress, setVoiceGenerationProgress] = useState(0);
  const [generatingUtteranceIds, setGeneratingUtteranceIds] = useState<Record<string, boolean>>({});
  const [generatedVoiceProgress, setGeneratedVoiceProgress] = useState(0);
  const [localTtsStarting, setLocalTtsStarting] = useState(false);
  const [ttsDeployment, setTtsDeployment] = useState<TtsDeploymentStatus>(defaultTtsDeployment);
  const [aiRoleCandidates, setAiRoleCandidates] = useState<AiRoleCandidate[]>([]);
  const [agentRunThreadId, setAgentRunThreadId] = useState("");
  const [agentRunWaitingForRoles, setAgentRunWaitingForRoles] = useState(false);
  const [agentRunRunning, setAgentRunRunning] = useState(false);
  const [workflowState, setWorkflowState] = useState(() => createWorkflowState("automatic"));

  const activeChapter = chapters.find((chapter) => chapter.chapterId === activeChapterId);
  const visibleParagraphs = paragraphs.filter((paragraph) => !paragraph.deleted);
  const currentChapterText = useMemo(
    () => visibleParagraphs.map((paragraph) => paragraph.text).join("\n\n"),
    [visibleParagraphs],
  );
  const flattenedUtterances = useMemo(
    () => visibleParagraphs.flatMap((paragraph) => utterancesByParagraph[paragraph.paragraphId] ?? []),
    [utterancesByParagraph, visibleParagraphs],
  );
  const hasPendingHumanReview = flattenedUtterances.some(
    (utterance) => utterance.needsHumanReview || !utterance.roleId || !utterance.text.trim(),
  );
  const primaryStatementParagraphId = visibleParagraphs[0]?.paragraphId ?? "";
  const roleOptions = useMemo(
    () => roles.map((role) => ({ value: role.roleId, label: role.name })),
    [roles],
  );

  function resetAgentRunState() {
    setAiRoleCandidates([]);
    setAgentRunThreadId("");
    setAgentRunWaitingForRoles(false);
    setAgentRunRunning(false);
  }

  function applyTtsDeployment(status: Partial<TtsDeploymentStatus> | null | undefined) {
    const normalized = normalizeTtsDeployment(status);
    setTtsDeployment(normalized);
    if (normalized.model_path || normalized.voice_design_model_path) {
      setModelConfig((current) => ({
        ...current,
        tts: {
          ...current.tts,
          ...(normalized.model_path ? { model_path: normalized.model_path } : {}),
          ...(normalized.voice_design_model_path
            ? { voice_design_model_path: normalized.voice_design_model_path }
            : {}),
        },
      }));
    }
    return normalized;
  }

  useEffect(() => {
    requestJson<{ voices: ApiVoiceResource[] }>("/voice-profiles")
      .then((data) => setVoices(data.voices.map(fromApiVoice)))
      .catch((error) => setApiStatus(apiFailureMessage("音色库载入失败，已保持空列表", error)));

    requestJson<{ roles: ApiRoleCard[] }>("/characters")
      .then((data) => setRoles(data.roles.map(fromApiRole)))
      .catch((error) => setApiStatus(apiFailureMessage("角色列表载入失败，已保持空列表", error)));

    requestJson<{ config: ModelConfig }>("/model-config")
      .then((data) => setModelConfig(normalizeModelConfig(data.config)))
      .catch(() => undefined);

    requestJson<{ deployment: TtsDeploymentStatus }>("/model-config/tts/deployment")
      .then((data) => applyTtsDeployment(data.deployment))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (ttsDeployment.status !== "running") return undefined;
    let cancelled = false;
    const poll = () => {
      requestJson<{ deployment: TtsDeploymentStatus }>("/model-config/tts/deployment")
        .then((data) => {
          if (cancelled) return;
          const status = applyTtsDeployment(data.deployment);
          if (status.status !== "running") setApiStatus(status.message);
        })
        .catch((error) => {
          if (!cancelled) setApiStatus(apiFailureMessage("TTS模型部署进度读取失败", error));
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
    if (workflowState.mode !== "automatic" || workflowState.status !== "running") return;
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
      const data = await requestJson<{ chapters: ApiChapter[] }>("/books/parse", {
        method: "POST",
        body: JSON.stringify({ text }),
      });
      const parsed = data.chapters.map(fromApiChapter);
      applyChapters(parsed, "小说已上传并由后端划分章节");
    } catch (error) {
      applyChapters(parseChapters(text), apiFailureMessage("后端导入失败，已使用本地章节预览", error));
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
        ? await requestJson<ApiChapterSplitResponse>("/books/agent-chapter-split-file", (() => {
            const form = new FormData();
            form.append(
              "file",
              new File(
                [Uint8Array.from(atob(uploadedFile.contentBase64), (character) => character.charCodeAt(0))],
                uploadedFile.filename,
                { type: "application/epub+zip" },
              ),
            );
            return { method: "POST", body: form };
          })())
        : await requestJson<ApiChapterSplitResponse>("/books/agent-chapter-split", {
            method: "POST",
            body: JSON.stringify({ text: fullNovelTextRef.current }),
          });
      setChapterSplitProgress(84);
      const parsed = data.chapters.map(fromApiChapter);
      const ruleName = data.agent.rule_path?.split(/[\\/]/).pop() ?? "未记录规则";
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

  async function syncCurrentChapterParagraphs(
    confirm = false,
  ): Promise<{ paragraphs: ParagraphModule[]; canSegment: boolean; utteranceDrafts: ApiUtterance[] }> {
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

  function updateParagraph(paragraphId: string, updates: Partial<ParagraphModule>) {
    setParagraphs((current) =>
      current.map((paragraph) =>
        paragraph.paragraphId === paragraphId ? { ...paragraph, ...updates } : paragraph,
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
        paragraph.paragraphId === paragraphId ? { ...paragraph, deleted: true } : paragraph,
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

  async function ensureChapterStatementsReady(): Promise<Record<string, UtteranceDraft[]>> {
    const hasStatementDrafts = visibleParagraphs.some(
      (paragraph) => (utterancesByParagraph[paragraph.paragraphId] ?? []).length > 0,
    );
    if (confirmed && hasStatementDrafts) return utterancesByParagraph;
    setApiStatus("正在同步当前章节并准备可匹配台词草稿");
    const synced = await syncCurrentChapterParagraphs(true);
    const draftsByParagraph = Object.fromEntries(
      synced.paragraphs.map((paragraph) => [
        paragraph.paragraphId,
        synced.utteranceDrafts.filter((utterance) => utterance.paragraph_id === paragraph.paragraphId),
      ]),
    );
    const nextUtterances = apiUtterancesToGroups(draftsByParagraph, synced.paragraphs, roles);
    setUtterancesByParagraph(nextUtterances);
    setApiStatus("当前章节已准备为可编辑台词草稿；配音编排 Agent 将自动完成台词划分和角色选择");
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
          synced.utteranceDrafts.filter((utterance) => utterance.paragraph_id === paragraph.paragraphId),
        ]),
      );
      setUtterancesByParagraph(apiUtterancesToGroups(draftsByParagraph, synced.paragraphs, roles));
      setApiStatus("段落已确认，已默认按整段落生成台词文本；配音编排 Agent 将自动完成台词划分和角色选择");
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
    const merged = { ...currentRole, ...updates };
    const updatedRole =
      updates.voiceResourceId !== undefined ? applyVoiceToRole(merged, updates.voiceResourceId) : merged;
    setRoles((current) => current.map((role) => (role.roleId === roleId ? updatedRole : role)));
    requestJson(`/characters/${roleId}`, {
      method: "PATCH",
      body: JSON.stringify(toApiRole(updatedRole)),
    }).catch((error) => setApiStatus(apiFailureMessage("角色同步失败", error)));
  }

  async function addRole() {
    const voice = voices[0];
    const roleId = `custom_role_${Date.now()}`;
    const roleName = `新角色${roles.length + 1}`;
    const role = voice ? roleFromVoice(roleId, roleName, voice) : createBlankRole(roleId, roleName);
    setRoles((current) => [...current, role]);
    try {
      const data = await requestJson<{ roles: ApiRoleCard[] }>("/characters", {
        method: "POST",
        body: JSON.stringify(toApiRole(role)),
      });
      setRoles(data.roles.map(fromApiRole));
      setApiStatus(`已新增角色：${role.name}`);
    } catch (error) {
      setApiStatus(apiFailureMessage("新增角色同步失败，已保留本地角色", error));
    }
  }

  async function deleteRole(roleId: string) {
    const payload = { roles: roles.map(toApiRole), utterances_by_paragraph: utteranceGroupsToApi(utterancesByParagraph) };
    try {
      const data = await requestJson<{ roles: ApiRoleCard[]; utterances_by_paragraph: Record<string, ApiUtterance[]> }>(
        `/characters/${roleId}`,
        { method: "DELETE", body: JSON.stringify(payload) },
      );
      setRoles(data.roles.map(fromApiRole));
      setUtterancesByParagraph(apiUtterancesToGroups(data.utterances_by_paragraph, paragraphs, data.roles.map(fromApiRole)));
      setApiStatus("角色删除成功");
    } catch (error) {
      if (!isRoleDeleteReferenceConflict(error)) {
        setApiStatus(apiFailureMessage("角色删除失败", error));
        return;
      }
      const detail = error.detail as { delete_result?: { referenced_count?: number } };
      const referencedCount = detail.delete_result?.referenced_count ?? 0;
      const shouldUnbind = window.confirm(
        `角色正在被 ${referencedCount} 条台词引用，是否解除这些台词的角色绑定并删除？`,
      );
      if (!shouldUnbind) {
        setApiStatus("角色删除已取消：仍保留角色和台词绑定");
        return;
      }
      try {
        const data = await requestJson<{ roles: ApiRoleCard[]; utterances_by_paragraph: Record<string, ApiUtterance[]> }>(
          `/characters/${roleId}`,
          { method: "DELETE", body: JSON.stringify({ ...payload, action: "unbind" }) },
        );
        const nextRoles = data.roles.map(fromApiRole);
        setRoles(nextRoles);
        setUtterancesByParagraph(apiUtterancesToGroups(data.utterances_by_paragraph, paragraphs, nextRoles));
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
    setWorkflowState((current) => transitionWorkflow(current, { type: "START" }));
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
      setWorkflowState((current) => transitionWorkflow(current, { type: "AGENT_COMPLETED" }));
      setRoleMatchingProgress(35);
      const autoSummary = data.auto_role_report
        ? `自动新增 ${data.auto_role_report.added_count} 个角色，生成 ${data.auto_role_report.generated_voice_count} 个音色。`
        : "";
      setApiStatus(`${data.message} ${autoSummary} 请检查角色列表后点击“配音编排 Agent”。`);
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
    setWorkflowState((current) => transitionWorkflow(current, { type: "CONTINUE" }));
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
          const response = await fetchApi(`/agent-runs/${agentRunThreadId}/events`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              ...(lastEventId ? { "Last-Event-ID": String(lastEventId) } : {}),
            },
            body: requestBody,
          });
          if (!response.ok) throw new Error(await response.text());
          if (!response.body) throw new Error("配音编排 Agent 没有返回进度流");
          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";
          while (true) {
            const { value, done } = await reader.read();
            buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
            const parsed = parseAgentSseBuffer(buffer);
            buffer = parsed.remainder;
            for (const event of parsed.events) {
              lastEventId = Math.max(lastEventId, event.id);
              handleAgentRunStreamEvent(event);
              terminalReceived ||= event.event === "completed" || event.event === "failed";
            }
            if (done) break;
          }
          if (!terminalReceived && attempt < 2) {
            await new Promise((resolve) => window.setTimeout(resolve, 250 * 2 ** attempt));
          }
        } catch (error) {
          if (attempt >= 2) throw error;
          await new Promise((resolve) => window.setTimeout(resolve, 250 * 2 ** attempt));
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
      setRoleMatchingProgress((current) => Math.min(95, Math.max(current + 5, 55)));
      return;
    }
    if (event.event === "completed") {
      const data = event.data as DubbingArrangementResponse;
      setUtterancesByParagraph(apiUtterancesToGroups(data.utterances_by_paragraph, paragraphs, roles));
      const requiresHumanReview = data.status === "needs_human_review" ||
        data.role_selection_events.some((item) => item.needs_human_review);
      setConfirmed(!requiresHumanReview);
      setChapterBackendSynced(true);
      setAgentRunWaitingForRoles(false);
      setRoleMatchingProgress(100);
      setApiStatus(data.message);
      setWorkflowState((current) =>
        transitionWorkflow(current, {
          type: data.status === "needs_human_review" ? "PAUSE" : "AGENT_COMPLETED",
        }),
      );
      return;
    }
    if (event.event === "failed") {
      const message = event.data?.failure?.message ?? event.data?.message ?? "模型输出未通过校验";
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
        audioStatus: event.needs_human_review ? "AI已选择角色，请人工确认" : "AI已选择角色",
        needsHumanReview: event.needs_human_review,
      };
      const found = list.some((item) => item.utteranceId === event.utterance_id);
      return {
        ...current,
        [event.paragraph_id]: found
          ? list.map((item) => (item.utteranceId === event.utterance_id ? { ...item, ...next } : item))
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
          updated.needsHumanReview = false;
        }
        return updated;
      }),
    }));
  }

  function addUtteranceAfter(paragraphId: string, afterUtteranceId?: string) {
    const paragraph = paragraphs.find((item) => item.paragraphId === paragraphId);
    if (!paragraph) return;
    setUtterancesByParagraph((current) => {
      const list = current[paragraphId] ?? [];
      const nextNumber = list.reduce((max, utterance) => {
        const match = utterance.utteranceId.match(/-u-(\d+)$/);
        return Math.max(max, match ? Number(match[1]) : 0);
      }, 0) + 1;
      const draft = {
        ...makeUtteranceDraft({ ...paragraph, text: "" }),
        utteranceId: `${paragraphId}-u-${String(nextNumber).padStart(3, "0")}`,
      };
      const insertIndex = afterUtteranceId ? list.findIndex((item) => item.utteranceId === afterUtteranceId) + 1 : list.length;
      const safeIndex = insertIndex <= 0 ? list.length : insertIndex;
      return {
        ...current,
        [paragraphId]: [...list.slice(0, safeIndex), draft, ...list.slice(safeIndex)],
      };
    });
  }

  function deleteUtterance(paragraphId: string, utteranceId: string) {
    setUtterancesByParagraph((current) => ({
      ...current,
      [paragraphId]: (current[paragraphId] ?? []).filter((utterance) => utterance.utteranceId !== utteranceId),
    }));
  }

  async function generateAudio(utterance: UtteranceDraft) {
    const role = roles.find((item) => item.roleId === utterance.roleId);
    if (!role) {
      updateUtterance(utterance.paragraphId, utterance.utteranceId, "audioStatus", "音频生成失败：角色不存在");
      return;
    }
    setGeneratingUtteranceIds((current) => ({ ...current, [utterance.utteranceId]: true }));
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
        voice_job: { status: string; output_path?: string; provider?: string; response_format?: string };
        warning?: string;
      }>(
        `/dubbing-segments/${utterance.utteranceId}/dubbing-jobs`,
        {
          method: "POST",
          body: JSON.stringify({
            role_id: role.roleId,
            voice_resource_id: role.voiceResourceId,
            text: utterance.text,
            voice_mode: role.voiceMode,
            language: "Auto",
          }),
        },
      );
      const audioStatus =
        result.voice_job.status === "substitute" ? "本地 TTS 未启动，已生成可播放占位音频" : "音频生成完成";
      setUtterancesByParagraph((current) => ({
        ...current,
        [utterance.paragraphId]: (current[utterance.paragraphId] ?? []).map((item) =>
          item.utteranceId === utterance.utteranceId
            ? {
                ...item,
                audioStatus,
                audioUrl: result.audio_url,
                audioPath: result.voice_job.output_path,
                audioDuration: result.duration_seconds,
                audioProvider: result.voice_job.provider,
                audioModel: result.voice_job.response_format,
              }
            : item,
        ),
      }));
      setVoiceGenerationProgress(100);
    } catch (error) {
      updateUtterance(utterance.paragraphId, utterance.utteranceId, "audioStatus", apiFailureMessage("音频生成失败", error));
      setVoiceGenerationProgress(100);
    } finally {
      setGeneratingUtteranceIds((current) => ({ ...current, [utterance.utteranceId]: false }));
    }
  }

  async function generateChapterDubbing() {
    if (dubbingInFlightRef.current) return;
    if (!activeChapter) {
      setApiStatus("批量生成配音失败：请先选择章节");
      return;
    }
    if (!confirmed || hasPendingHumanReview) {
      setApiStatus("批量生成配音失败：请先确认所有配音片段的台词与角色");
      return;
    }
    dubbingInFlightRef.current = true;
    setVoiceGenerationProgress(10);
    setWorkflowState((current) => transitionWorkflow(current, { type: "CONTINUE" }));
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
      setUtterancesByParagraph(apiUtterancesToGroups(data.utterances_by_paragraph, paragraphs, roles));
      setVoiceGenerationProgress(100);
      const groupSummary = data.groups.map((group) => `${group.voice_resource_id}×${group.count}`).join("，");
      const errorSummary = data.failed_count ? `；失败 ${data.failed_count} 条：${data.errors[0]?.message ?? "请检查详情"}` : "";
      setApiStatus(`批量生成配音完成：成功 ${data.success_count} 条，跳过 ${data.skipped_count} 条；分组 ${groupSummary || "无待生成"}${errorSummary}`);
      setWorkflowState((current) => transitionWorkflow(current, { type: "AGENT_COMPLETED" }));
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
    setApiStatus("正在导出当前章节逐条音频和 manifest");
    try {
      const data = await requestJson<{
        status: string;
        item_count: number;
        missing_count: number;
        download_url: string;
        message: string;
      }>(`/exports/${activeChapter.chapterId}`, {
        method: "POST",
        body: JSON.stringify({
          chapter_title: activeChapter.title,
          roles: roles.map(toApiRole),
          utterances_by_paragraph: utteranceGroupsToApi(utterancesByParagraph),
          pause_ms: 300,
          speed: 1.0,
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
      setApiStatus(`制作包导出完成：${data.item_count} 条；${data.message}`);
    } catch (error) {
      setApiStatus(apiFailureMessage("导出制作包失败", error));
    }
  }

  async function saveVoiceResource(payload: Omit<Partial<VoiceResource>, "suitableRoleTypes"> & { suitableRoleTypes?: string[] | string }): Promise<boolean> {
    try {
      const data = await requestJson<{ voice: ApiVoiceResource; voices: ApiVoiceResource[] }>("/voice-profiles", {
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
      const data = await requestJson<{ voice: ApiVoiceResource; voices: ApiVoiceResource[] }>(`/voice-profiles/${voice.voiceId}`, {
        method: "PATCH",
        body: JSON.stringify(toApiVoice(voice)),
      });
      setVoices(data.voices.map(fromApiVoice));
      setApiStatus(`保存音色成功：${data.voice.name}`);
    } catch (error) {
      setApiStatus(apiFailureMessage("保存音色失败", error));
    }
  }

  async function handleReferenceAudioFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setApiStatus(`正在上传参考音频文件：${file.name}`);
    try {
      const form = new FormData();
      form.append("file", file);
      const data = await requestJson<{ reference_audio_path: string }>("/voice-profiles/reference-audio", {
        method: "POST",
        body: form,
      });
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
      }>(
        "/voice-profiles/generate",
        {
          method: "POST",
          body: JSON.stringify({
            name: generatedVoice.name,
            description: generatedVoice.description,
            gender: generatedVoice.gender,
            suitable_role_types: generatedVoice.suitableRoleTypes
              .split(/[，,、]/)
              .map((item) => item.trim())
              .filter(Boolean),
            reference_text: generatedVoice.referenceText || DEFAULT_GENERATED_VOICE_TEXT,
          }),
        },
      );
      setGeneratedVoiceProgress(100);
      setGeneratedVoicePreview(fromApiVoice(data.voice));
      setGeneratedVoicePreviewUrl(data.audio_url);
      const prefix = data.generation_status === "substitute" ? "生成音色使用占位预览" : "生成音色成功";
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

  async function deleteSelectedVoices() {
    const selected = voices.filter((item) => selectedVoiceIds[item.voiceId]);
    if (selected.length === 0) {
      setApiStatus("删除选中音色失败：请先勾选至少一个音色");
      return;
    }
    try {
      let remaining = voices;
      for (const voice of selected) {
        const data = await requestJson<{ voices: ApiVoiceResource[] }>(`/voice-profiles/${voice.voiceId}`, {
          method: "DELETE",
        });
        remaining = data.voices.map(fromApiVoice);
      }
      setVoices(remaining);
      setSelectedVoiceIds({});
      setApiStatus(`删除选中音色成功：${selected.length} 个`);
    } catch (error) {
      setApiStatus(apiFailureMessage("删除选中音色失败", error));
    }
  }

  async function saveTextModelConfig() {
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
    try {
      const data = await requestJson<ConnectionTestResponse>("/connection-test");
      setApiStatus(data.message || "后端 API 连接成功");
    } catch (error) {
      setApiStatus(apiFailureMessage("测试连接失败", error));
    }
  }

  async function testModelApis() {
    if (localTtsStarting) return;
    setLocalTtsStarting(true);
    setApiStatus("正在测试文本模型与 TTS 模型 API");
    try {
      const secretPayload = await createSecretExchangePayload(textModelApiKey);
      const data = await requestJson<ModelApisTestResponse>("/model-config/models/test", {
        method: "POST",
        body: JSON.stringify({
          text_model: modelConfig.text_model,
          tts: modelConfig.tts,
          ...(secretPayload ? { text_model_secret: secretPayload } : {}),
        }),
      });
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
    setApiStatus("已开始后台下载并部署 TTS 模型；其他不依赖 TTS 的功能可继续使用");
    try {
      const data = await requestJson<{ deployment: TtsDeploymentStatus }>("/model-config/tts/deploy", {
        method: "POST",
        body: JSON.stringify({ tts: modelConfig.tts }),
      });
      const status = applyTtsDeployment(data.deployment);
      setApiStatus(status.message);
    } catch (error) {
      setApiStatus(apiFailureMessage("TTS模型下载并部署启动失败", error));
    }
  }

  function renderMainPage() {
    return (
      <main
        className={chapterSidebarCollapsed ? "workbench chapters-collapsed" : "workbench"}
        aria-label={`${APP_BRAND} v${APP_VERSION} 主页面`}
      >
        <aside className={chapterSidebarCollapsed ? "chapter-sidebar collapsed" : "chapter-sidebar"}>
          <button
            className="sidebar-toggle"
            type="button"
            aria-label={chapterSidebarCollapsed ? "展开小说章节边栏" : "收起小说章节边栏"}
            title={chapterSidebarCollapsed ? "展开小说章节边栏" : "收起小说章节边栏"}
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
                  <button className="tool-button sky" type="button" onClick={() => fileInputRef.current?.click()}>
                    上传小说
                  </button>
                  <button className="tool-button amber" type="button" onClick={() => void runAiChapterSplit()}>
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
                <ProgressBar label="小说格式解析进度" value={chapterSplitProgress} />
                <ProgressBar label="配音编排 Agent 进度" value={roleMatchingProgress} />
                <ProgressBar label="语音生成进度" value={voiceGenerationProgress} />
                <div className="novel-preview" aria-label="小说开头预览">
                  {novelPreview}
                </div>
                <small>{apiStatus}</small>
                <div className="chapter-list" aria-label="章节列表">
                  {chapters.map((chapter) => (
                    <button
                      className={chapter.chapterId === activeChapterId ? "active" : ""}
                      key={chapter.chapterId}
                      type="button"
                      onClick={() => void selectChapter(chapter.chapterId)}
                    >
                      {chapter.title}
                    </button>
                  ))}
                </div>
              </section>

              <section className="panel">
                <div className="section-heading">
                  <div className="section-title">角色列表</div>
                  <button className="tool-button teal" type="button" onClick={() => void addRole()}>
                    新增角色
                  </button>
                </div>
                <div className="role-stack">
                  {roles.map((role) => {
                    const voice = voices.find((item) => item.voiceId === role.voiceResourceId);
                    return (
                      <article className="role-card" key={role.roleId}>
                        <input
                          aria-label={`${role.name} 角色名展示`}
                          value={role.name}
                          onChange={(event) => updateRole(role.roleId, { name: event.target.value })}
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
                          onChange={(event) => updateRole(role.roleId, { gender: event.target.value })}
                        />
                        <textarea
                          aria-label={`${role.name} 人设身份性格`}
                          placeholder="人设/身份/性格"
                          value={role.profile}
                          onChange={(event) => updateRole(role.roleId, { profile: event.target.value })}
                        />
                        <div className="inline-select">
                          <label>
                            音色选择
                            <select
                              value={role.voiceResourceId}
                              onChange={(event) => updateRole(role.roleId, { voiceResourceId: event.target.value })}
                            >
                              <option value="">未选择音色</option>
                              {voices.map((item) => (
                                <option key={item.voiceId} value={item.voiceId}>
                                  {item.name}
                                </option>
                              ))}
                            </select>
                          </label>
                        </div>
                        <p>
                          <strong>音色描述</strong>
                          {voice?.description || role.voiceDescription || role.description || "未选择音色"}
                        </p>
                        <p>
                          <strong>语音具体内容</strong>
                          {voice?.referenceText || role.voiceSampleText || role.referenceText || "未选择音色"}
                        </p>
                        <p>
                          <strong>音色匹配</strong>
                          {role.voiceMatchReason ?? "用户可手动调整"}
                        </p>
                        {voice && <AuthorizedAudio source={voiceAudioSrc(voice)} />}
                        <button className="tool-button amber" type="button" onClick={() => void deleteRole(role.roleId)}>
                          删除角色
                        </button>
                      </article>
                    );
                  })}
                </div>
                {aiRoleCandidates.length > 0 && (
                  <div className="role-analysis-panel" aria-label="角色分析建议">
                    <div className="section-title">角色分析建议</div>
                    <small>请检查角色列表，必要时手动调整角色或音色；随后点击章节顶部“配音编排 Agent”。模型建议仅作参考。</small>
                    {aiRoleCandidates.map((candidate, index) => (
                      <article className="role-candidate-card" key={`${candidate.name ?? "unknown"}-${index}`}>
                        <strong>{candidate.name ?? "未知角色"}</strong>
                        <p>别名/称呼：{candidate.aliases.length ? candidate.aliases.join("、") : "待确认"}</p>
                        <p>性别：{candidate.gender ?? "待确认"}</p>
                        <p>人设/身份/性格：{candidate.profile ?? "待确认"}</p>
                        <p>推荐音色方向：{candidate.voice_direction ?? "待确认"}</p>
                        <p>证据片段：{candidate.evidence.join(" / ") || "待确认"}</p>
                        <p>置信度：{Math.round(candidate.confidence * 100)}%；{candidate.needs_human_review ? "需要人工确认" : "仍可人工编辑"}</p>
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
              <p>选择某个章节后，左侧显示完整正文，右侧显示配音编排 Agent 生成后的台词。</p>
            </div>
          ) : (
            <>
              <header className="chapter-header">
                <div>
                  <div className="section-title">当前章节</div>
                  <h2>{activeChapter.title}</h2>
                </div>
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
                    disabled={agentRunRunning || !agentRunWaitingForRoles || !agentRunThreadId}
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
                  <span>
                    {confirmed && !hasPendingHumanReview
                      ? "台词已确认，可以批量配音或导出"
                      : "请完成角色分析、配音编排并确认所有配音片段"}
                  </span>
                </div>
              </header>

              <section className="chapter-workspace-grid">
                <article className="panel chapter-reader" aria-label="当前章节完整小说内容">
                  <div className="section-title">当前章节完整小说内容</div>
                  <div className="chapter-reader-body">{currentChapterText || "当前章节正文为空。"}</div>
                </article>

                <article className="panel statement-panel" aria-label="划分台词与角色匹配">
                  <div className="section-heading">
                    <div className="section-title">划分台词与角色匹配</div>
                  </div>
                  {flattenedUtterances.length === 0 ? (
                    <div className="statement-empty">
                      <span>当前章节可手动添加台词、选择角色并生成配音；也可以稍后使用配音编排 Agent 自动辅助。</span>
                      {primaryStatementParagraphId && (
                        <button
                          className="tool-button amber"
                          type="button"
                          onClick={() => addUtteranceAfter(primaryStatementParagraphId)}
                        >
                          添加第一条台词
                        </button>
                      )}
                    </div>
                  ) : (
                    <div className="statement-list">
                      {flattenedUtterances.map((utterance) => (
                        <article className="utterance-card" key={utterance.utteranceId}>
                          <div className="utterance-toolbar">
                            <strong>{utterance.utteranceId}</strong>
                            <button
                              className="tool-button amber"
                              type="button"
                              onClick={() => addUtteranceAfter(utterance.paragraphId, utterance.utteranceId)}
                            >
                              在此后添加台词
                            </button>
                            <button type="button" onClick={() => deleteUtterance(utterance.paragraphId, utterance.utteranceId)}>
                              删除台词
                            </button>
                          </div>
                          <label className="utterance-wide">
                            台词文本
                            <input
                              value={utterance.text}
                              onChange={(event) =>
                                updateUtterance(utterance.paragraphId, utterance.utteranceId, "text", event.target.value)
                              }
                              aria-label={`${utterance.utteranceId} 台词文本`}
                            />
                          </label>
                          <label>
                            选择角色
                            <select
                              value={utterance.roleId}
                              onChange={(event) =>
                                updateUtterance(utterance.paragraphId, utterance.utteranceId, "roleId", event.target.value)
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
                                updateUtterance(
                                  utterance.paragraphId,
                                  utterance.utteranceId,
                                  "needsHumanReview",
                                  !event.target.checked,
                                );
                                if (event.target.checked && utterance.roleId && utterance.text.trim()) {
                                  setConfirmed(true);
                                }
                              }}
                            />
                            已确认台词与角色
                          </label>
                          {(() => {
                            const isGeneratingThisUtterance = Boolean(generatingUtteranceIds[utterance.utteranceId]);
                            return (
                              <button
                                className="tool-button sky"
                                type="button"
                                disabled={isGeneratingThisUtterance}
                                onClick={() => void generateAudio(utterance)}
                              >
                                {isGeneratingThisUtterance ? "正在生成" : "生成配音"}
                              </button>
                            );
                          })()}
                          <output>{utterance.audioStatus}</output>
                          {utterance.audioUrl && (
                            <AuthorizedAudio source={utterance.audioUrl} />
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
          <div className="section-title">音色列表</div>
          <small className="status-message" aria-label="音色库反馈">{apiStatus}</small>
          <div className="voice-grid">
            {voices.map((voice) => (
              <article className="voice-card" key={voice.voiceId}>
                <label className="checkline">
                  <input
                    type="checkbox"
                    checked={Boolean(selectedVoiceIds[voice.voiceId])}
                    onChange={(event) =>
                      setSelectedVoiceIds((current) => ({ ...current, [voice.voiceId]: event.target.checked }))
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
                          item.voiceId === voice.voiceId ? { ...item, name: event.target.value } : item,
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
                          item.voiceId === voice.voiceId ? { ...item, gender: event.target.value } : item,
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
                          item.voiceId === voice.voiceId ? { ...item, description: event.target.value } : item,
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
                          item.voiceId === voice.voiceId ? { ...item, referenceText: event.target.value } : item,
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
                          item.voiceId === voice.voiceId ? { ...item, referenceAudioPath: event.target.value } : item,
                        ),
                      )
                    }
                  />
                </label>
                <AuthorizedAudio source={voiceAudioSrc(voice)} />
                <button className="tool-button teal" type="button" onClick={() => void updateVoiceResource(voice)}>
                  保存音色
                </button>
              </article>
            ))}
          </div>
          <button className="tool-button amber" type="button" onClick={() => void deleteSelectedVoices()}>
            删除选中音色
          </button>
        </section>

        <section className="two-column">
          <div className="panel">
            <div className="section-title">添加音色</div>
            <input
              placeholder="音色名称"
              value={newVoice.name}
              onChange={(event) => setNewVoice((current) => ({ ...current, name: event.target.value }))}
            />
            <input
              placeholder="音色性别"
              value={newVoice.gender}
              onChange={(event) => setNewVoice((current) => ({ ...current, gender: event.target.value }))}
            />
            <textarea
              placeholder="音色描述"
              value={newVoice.description}
              onChange={(event) => setNewVoice((current) => ({ ...current, description: event.target.value }))}
            />
            <input
              placeholder="适合角色类型，用逗号分隔"
              value={newVoice.suitableRoleTypes}
              onChange={(event) => setNewVoice((current) => ({ ...current, suitableRoleTypes: event.target.value }))}
            />
            <textarea
              placeholder="语音具体内容"
              value={newVoice.referenceText}
              onChange={(event) => setNewVoice((current) => ({ ...current, referenceText: event.target.value }))}
            />
            <input
              ref={voiceAudioInputRef}
              className="hidden-input"
              type="file"
              accept="audio/*"
              aria-label="添加参考音频文件"
              onChange={(event) => void handleReferenceAudioFile(event)}
            />
            <button className="tool-button sky" type="button" onClick={() => voiceAudioInputRef.current?.click()}>
              添加参考音频文件
            </button>
            {newVoice.referenceAudioPath && <small>已选择：{newVoice.referenceAudioPath}</small>}
            {newVoiceAudioPreviewUrl && (
              <AuthorizedAudio source={newVoiceAudioPreviewUrl} />
            )}
            <button className="tool-button teal" type="button" onClick={() => void saveVoiceResource(newVoice)}>
              保存音色
            </button>
          </div>

          <div className="panel">
            <div className="section-title">生成音色</div>
            <input
              placeholder="音色名称"
              value={generatedVoice.name}
              onChange={(event) => setGeneratedVoice((current) => ({ ...current, name: event.target.value }))}
            />
            <input
              placeholder="音色性别"
              value={generatedVoice.gender}
              onChange={(event) => setGeneratedVoice((current) => ({ ...current, gender: event.target.value }))}
            />
            <textarea
              placeholder="音色描述"
              value={generatedVoice.description}
              onChange={(event) => setGeneratedVoice((current) => ({ ...current, description: event.target.value }))}
            />
            <input
              placeholder="适合角色类型，用逗号分隔"
              value={generatedVoice.suitableRoleTypes}
              onChange={(event) => setGeneratedVoice((current) => ({ ...current, suitableRoleTypes: event.target.value }))}
            />
            <textarea
              placeholder="语音具体内容"
              value={generatedVoice.referenceText}
              onChange={(event) => setGeneratedVoice((current) => ({ ...current, referenceText: event.target.value }))}
            />
            <ProgressBar label="生成音色进度" value={generatedVoiceProgress} />
            <button className="tool-button purple" type="button" onClick={() => void generateVoiceResource()}>
              生成音色
            </button>
            {generatedVoicePreviewUrl && (
              <div className="generated-preview">
                <small>试听生成音色：{generatedVoicePreview?.name}</small>
                <AuthorizedAudio source={generatedVoicePreviewUrl} />
              </div>
            )}
            <button className="tool-button teal" type="button" onClick={() => void saveGeneratedVoiceResource()}>
              保存音色
            </button>
          </div>
        </section>
      </main>
    );
  }

  function renderModelConfigPage() {
    return (
      <main className="model-page">
        <section className="panel">
          <div className="section-title">文本模型</div>
          <small className="status-message" aria-label="模型配置反馈">{apiStatus}</small>
          <label>
            Base URL
            <input
              placeholder="eg: https://api.deepseek.com"
              value={modelConfig.text_model.base_url}
              onChange={(event) =>
                setModelConfig((current) => ({
                  ...current,
                  text_model: { ...current.text_model, base_url: event.target.value },
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
                  text_model: { ...current.text_model, model: event.target.value },
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
          <p className="config-secret-status">临时密钥：{modelConfig.text_model.has_api_key ? "后端内存已配置" : "未输入"}</p>
          <div className="toolbar-row">
            <button className="tool-button teal" type="button" onClick={() => void saveTextModelConfig()}>
              保存模型配置
            </button>
            <button className="tool-button sky" type="button" onClick={() => void testBackendConnection()}>
              测试连接
            </button>
            <button className="tool-button purple" type="button" disabled={localTtsStarting} onClick={() => void testModelApis()}>
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
                setModelConfig((current) => ({ ...current, tts: { ...current.tts, base_url: event.target.value } }))
              }
            />
          </label>
          <label>
            Base 模型权重路径
            <input
              value={modelConfig.tts.model_path}
              onChange={(event) =>
                setModelConfig((current) => ({ ...current, tts: { ...current.tts, model_path: event.target.value } }))
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
                  tts: { ...current.tts, voice_design_model_path: event.target.value },
                }))
              }
            />
          </label>
          <ProgressBar label="TTS模型下载并部署进度" value={ttsDeployment.progress} />
          <small className="status-message" aria-label="TTS模型部署反馈">{ttsDeployment.message}</small>
          <div className="toolbar-row">
            <button className="tool-button teal" type="button" onClick={() => void saveLocalModelConfig()}>
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
            <button className="tool-button purple" type="button" disabled={localTtsStarting} onClick={() => void testModelApis()}>
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
            <img className="brand-logo" src={`${runtimeConfig.pagesBase}shuyi-agent-zh.svg`} alt={APP_BRAND} />
            <span>v{APP_VERSION}</span>
          </h1>
          <p className="product-subtitle">基于 Agent 的多人有声书自动配音工作台</p>
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
                    transitionWorkflow(current, { type: "SET_MODE", mode: mode as WorkflowMode }),
                  )
                }
              >
                {label}
              </button>
            ))}
          </div>
          <nav className="tabbar" aria-label="页面切换">
            {[
              ["main", "主页面"],
              ["voices", "音色库"],
              ["models", "模型配置"],
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
      {page === "models" && renderModelConfigPage()}
    </div>
  );
}

export default App;
