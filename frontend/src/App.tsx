import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";

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
    script_path: string | null;
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

type AiOneClickStartResponse = {
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

type AiOneClickResumeResponse = {
  status: string;
  thread_id: string;
  message: string;
  utterances_by_paragraph: Record<string, ApiUtterance[]>;
  role_selection_events: AiRoleSelectionEvent[];
  failure?: { paragraph_id: string; error_code: string; message: string } | null;
};

type ModelConfig = {
  llm: {
    base_url: string;
    model: string;
    api_key: string;
  };
  tts: {
    base_url: string;
    model_path: string;
    voice_design_model_path: string;
  };
  chapter_agent: {
    base_url: string;
    model: string;
    api_key: string;
  };
};

type LocalTtsStartResponse = {
  message: string;
  progress?: number;
};

const sampleNovel = `1.变成蘑菇的公爵千金
“放开我！你们是谁？快放开我！”

一醒来就发现自己被装麻袋了的伊南娜竭力扭动身体。

“佩罗，你昏迷术掺水了？这就醒了。”`;

const MAX_NOVEL_PREVIEW_CHARS = 700;
const DEFAULT_GENERATED_VOICE_TEXT = "这是一段用于试听新音色的语音。";
const DEFAULT_BASE_MODEL_PATH = "/Users/gaojing/Documents/models/Qwen3-TTS-12Hz-1.7B-Base";
const DEFAULT_VOICE_DESIGN_MODEL_PATH = "/Users/gaojing/Documents/models/Qwen3-TTS-12Hz-1.7B-VoiceDesign";

const defaultVoices: VoiceResource[] = [
  {
    voiceId: "voice-male-narrator",
    name: "男声旁白",
    gender: "男",
    description: "沉稳、叙事感强，适合旁白和长段说明。",
    suitableRoleTypes: ["旁白", "叙述", "长段说明"],
    referenceText: "探索那些被遗忘的地下空间，比如废弃的地铁站、防空洞。",
    referenceAudioPath: "/Users/gaojing/Downloads/真实测试样本/音频/男声旁白/男声旁白.mp3",
    playableAudioPath: "/Users/gaojing/Downloads/真实测试样本/音频/男声旁白/男声旁白.mp3",
    generated: false,
  },
  {
    voiceId: "voice-young-male",
    name: "年轻男",
    gender: "男",
    description: "清亮自然，适合年轻男性角色对白。",
    suitableRoleTypes: ["年轻男性", "对白"],
    referenceText: "光柱最终落在那株已经遍布猩红纹路的神木幼苗上。",
    referenceAudioPath: "/Users/gaojing/Downloads/真实测试样本/音频/年轻男/年轻男.mp3",
    playableAudioPath: "/Users/gaojing/Downloads/真实测试样本/音频/年轻男/年轻男.mp3",
    generated: false,
  },
  {
    voiceId: "voice-yujie",
    name: "御姐音",
    gender: "女",
    description: "成熟亲近，适合女性角色对白。",
    suitableRoleTypes: ["女性角色", "成熟", "对白"],
    referenceText: "宝宝，今天你可得好好陪我逛逛。",
    referenceAudioPath: "/Users/gaojing/Downloads/真实测试样本/音频/御姐音/御姐音.mp3",
    playableAudioPath: "/Users/gaojing/Downloads/真实测试样本/音频/御姐音/御姐音.mp3",
    generated: false,
  },
];

const defaultModelConfig: ModelConfig = {
  llm: {
    base_url: "https://api.siliconflow.cn/v1",
    model: "Qwen/Qwen3-8B",
    api_key: "",
  },
  tts: {
    base_url: "http://127.0.0.1:7811",
    model_path: DEFAULT_BASE_MODEL_PATH,
    voice_design_model_path: DEFAULT_VOICE_DESIGN_MODEL_PATH,
  },
  chapter_agent: {
    base_url: "https://api.deepseek.com",
    model: "deepseek-v4-flash",
    api_key: "",
  },
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
        // Try the next legacy Chinese encoding supported by the browser.
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
      preview: `已上传 EPUB：${file.name}\n\n点击“AI小说格式解析”后将由后端解析 EPUB 目录和正文。`,
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
      })),
    ]),
  );
}

function voiceAudioSrc(voice: VoiceResource): string {
  return `/api/voice-resources/${voice.voiceId}/audio`;
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
    voiceMatchReason: "默认角色绑定音色",
    voiceGeneratedByAi: voice.generated,
  };
}

function createDefaultRoles(voices: VoiceResource[]): RoleCard[] {
  const fallback = voices[0] ?? defaultVoices[0];
  const pick = (voiceId: string) => voices.find((voice) => voice.voiceId === voiceId) ?? fallback;
  return [
    roleFromVoice("narrator", "旁白", pick("voice-male-narrator")),
    roleFromVoice("male_lead", "年轻男", pick("voice-young-male")),
    roleFromVoice("female_lead", "御姐音", pick("voice-yujie")),
  ];
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail ?? data.error ?? response.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data as T;
}

function makeUtteranceDraft(paragraph: ParagraphModule): UtteranceDraft {
  return {
    utteranceId: `${paragraph.paragraphId}-u-001`,
    paragraphId: paragraph.paragraphId,
    text: paragraph.text,
    roleId: "",
    speakerName: "",
    audioStatus: "尚未生成",
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
  const audioUrl = audioPathToUrl(utterance.audio_path);
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
  };
}

function normalizeModelConfig(config: Partial<ModelConfig>): ModelConfig {
  return {
    llm: {
      base_url: config.llm?.base_url ?? defaultModelConfig.llm.base_url,
      model: config.llm?.model ?? defaultModelConfig.llm.model,
      api_key: config.llm?.api_key ?? "",
    },
    tts: {
      base_url: config.tts?.base_url ?? defaultModelConfig.tts.base_url,
      model_path: config.tts?.model_path ?? defaultModelConfig.tts.model_path,
      voice_design_model_path: config.tts?.voice_design_model_path ?? defaultModelConfig.tts.voice_design_model_path,
    },
    chapter_agent: {
      base_url: config.chapter_agent?.base_url ?? defaultModelConfig.chapter_agent.base_url,
      model: config.chapter_agent?.model ?? defaultModelConfig.chapter_agent.model,
      api_key: config.chapter_agent?.api_key ?? "",
    },
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
  const fullNovelTextRef = useRef(sampleNovel);
  const uploadedNovelFileRef = useRef<UploadedNovelFile | null>(null);
  const [page, setPage] = useState<Page>(() => initialPageFromUrl());
  const [novelPreview, setNovelPreview] = useState(() => makeNovelPreview(sampleNovel));
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [activeChapterId, setActiveChapterId] = useState("");
  const [paragraphs, setParagraphs] = useState<ParagraphModule[]>([]);
  const [chapterSidebarCollapsed, setChapterSidebarCollapsed] = useState(false);
  const [hasSplitChapters, setHasSplitChapters] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [voices, setVoices] = useState<VoiceResource[]>(defaultVoices);
  const [roles, setRoles] = useState<RoleCard[]>(() => createDefaultRoles(defaultVoices));
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
  const [apiStatus, setApiStatus] = useState("等待上传小说");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [chapterSplitProgress, setChapterSplitProgress] = useState(0);
  const [roleMatchingProgress, setRoleMatchingProgress] = useState(0);
  const [voiceGenerationProgress, setVoiceGenerationProgress] = useState(0);
  const [generatingUtteranceIds, setGeneratingUtteranceIds] = useState<Record<string, boolean>>({});
  const [generatedVoiceProgress, setGeneratedVoiceProgress] = useState(0);
  const [localTtsStartProgress, setLocalTtsStartProgress] = useState(0);
  const [localTtsStarting, setLocalTtsStarting] = useState(false);
  const [aiRoleCandidates, setAiRoleCandidates] = useState<AiRoleCandidate[]>([]);
  const [aiOneClickThreadId, setAiOneClickThreadId] = useState("");
  const [aiOneClickWaitingForRoles, setAiOneClickWaitingForRoles] = useState(false);
  const [aiOneClickRunning, setAiOneClickRunning] = useState(false);

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
  const primaryStatementParagraphId = visibleParagraphs[0]?.paragraphId ?? "";
  const roleOptions = useMemo(
    () => roles.map((role) => ({ value: role.roleId, label: role.name })),
    [roles],
  );

  function resetAiOneClickState() {
    setAiRoleCandidates([]);
    setAiOneClickThreadId("");
    setAiOneClickWaitingForRoles(false);
    setAiOneClickRunning(false);
  }

  useEffect(() => {
    requestJson<{ voices: ApiVoiceResource[] }>("/api/voice-resources")
      .then((data) => {
        const loaded = data.voices.map(fromApiVoice);
        if (loaded.length > 0) {
          setVoices(loaded);
          setRoles(createDefaultRoles(loaded));
        }
      })
      .catch((error) => setApiStatus(`音色资源库载入失败，已使用本地预览：${String(error)}`));

    requestJson<{ config: ModelConfig }>("/api/model-config")
      .then((data) => setModelConfig(normalizeModelConfig(data.config)))
      .catch(() => undefined);
  }, []);

  async function importNovelText(text: string) {
    fullNovelTextRef.current = text;
    setNovelPreview(makeNovelPreview(text));
    try {
      const data = await requestJson<{ chapters: ApiChapter[] }>("/api/novels/parse", {
        method: "POST",
        body: JSON.stringify({ text }),
      });
      const parsed = data.chapters.map(fromApiChapter);
      applyChapters(parsed, "小说已上传并由后端划分章节");
    } catch (error) {
      applyChapters(parseChapters(text), `后端导入失败，已使用本地章节预览：${String(error)}`);
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
    resetAiOneClickState();
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
    resetAiOneClickState();
    setUploadProgress(62);
    setApiStatus("小说已上传，仅展示开头预览；点击“AI小说格式解析”生成章节目录");
    setUploadProgress(100);
  }

  async function runAiChapterSplit() {
    setChapterSplitProgress(12);
    setApiStatus("AI小说格式解析智能体正在检查可复用脚本");
    try {
      const uploadedFile = uploadedNovelFileRef.current;
      const data = uploadedFile
        ? await requestJson<ApiChapterSplitResponse>("/api/novels/ai-chapter-split-file", {
            method: "POST",
            body: JSON.stringify({
              filename: uploadedFile.filename,
              content_base64: uploadedFile.contentBase64,
            }),
          })
        : await requestJson<ApiChapterSplitResponse>("/api/novels/ai-chapter-split", {
            method: "POST",
            body: JSON.stringify({ text: fullNovelTextRef.current }),
          });
      setChapterSplitProgress(84);
      const parsed = data.chapters.map(fromApiChapter);
      const scriptName = data.agent.script_path?.split(/[\\/]/).pop() ?? "未记录脚本";
      const agentStatus =
        data.agent.status === "script_reused"
          ? `AI小说格式解析完成：已复用 ${scriptName}`
          : `AI小说格式解析完成：已生成并保存 ${scriptName}`;
      applyChapters(parsed, `${agentStatus}；选择左侧章节后才加载该章正文`);
    } catch (error) {
      setChapterSplitProgress(76);
      const parsed = parseChapterIndex(fullNovelTextRef.current);
      applyChapters(parsed, `AI小说格式解析失败，已使用本地章节索引兜底：${String(error)}`);
    } finally {
      setChapterSplitProgress(100);
    }
  }

  async function selectChapter(chapterId: string) {
    const chapter = chapters.find((item) => item.chapterId === chapterId);
    if (!chapter) return;
    setActiveChapterId(chapterId);
    const body = extractChapterBody(fullNovelTextRef.current, chapter);
    setParagraphs(paragraphsFromChapter({ ...chapter, body }));
    setConfirmed(false);
    setChapterBackendSynced(false);
    setUtterancesByParagraph({});
    setRoleMatchingProgress(0);
    setVoiceGenerationProgress(0);
    setGeneratingUtteranceIds({});
    resetAiOneClickState();
    setApiStatus(`已加载章节：${chapter.title}`);
  }

  async function syncCurrentChapterParagraphs(
    confirm = false,
  ): Promise<{ paragraphs: ParagraphModule[]; canSegment: boolean; utteranceDrafts: ApiUtterance[] }> {
    if (!activeChapter) throw new Error("请选择章节");
    const data = await requestJson<ApiChapterParagraphsResponse>(
      `/api/chapters/${activeChapter.chapterId}/paragraphs`,
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
      resetAiOneClickState();
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
    setApiStatus(`已删除段落 ${paragraphId}；其余 AI角色匹配结果已保留`);
  }

  async function ensureChapterStatementsReady(): Promise<Record<string, UtteranceDraft[]>> {
    const hasStatementDrafts = visibleParagraphs.some(
      (paragraph) => (utterancesByParagraph[paragraph.paragraphId] ?? []).length > 0,
    );
    if (confirmed && hasStatementDrafts) return utterancesByParagraph;
    setApiStatus("正在同步当前章节并准备可匹配语句草稿");
    const synced = await syncCurrentChapterParagraphs(true);
    const draftsByParagraph = Object.fromEntries(
      synced.paragraphs.map((paragraph) => [
        paragraph.paragraphId,
        synced.utteranceDrafts.filter((utterance) => utterance.paragraph_id === paragraph.paragraphId),
      ]),
    );
    const nextUtterances = apiUtterancesToGroups(draftsByParagraph, synced.paragraphs, roles);
    setUtterancesByParagraph(nextUtterances);
    setApiStatus("当前章节已准备为可编辑语句草稿；AI角色匹配将自动完成语句划分和角色选择");
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
      setApiStatus("段落已确认，已默认按整段落生成语句文本；AI角色匹配将自动完成语句划分和角色选择");
    } catch (error) {
      setConfirmed(false);
      setChapterBackendSynced(false);
      setApiStatus(`段落确认失败：${String(error)}`);
    }
  }

  function applyVoiceToRole(role: RoleCard, voiceId: string): RoleCard {
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
    requestJson(`/api/roles/${roleId}`, {
      method: "PATCH",
      body: JSON.stringify(toApiRole(updatedRole)),
    }).catch((error) => setApiStatus(`角色同步失败：${String(error)}`));
  }

  async function addRole() {
    const voice = voices[0];
    if (!voice) {
      setApiStatus("新增角色失败：请先添加至少一个音色资源");
      return;
    }
    const role: RoleCard = {
      ...roleFromVoice(`custom_role_${Date.now()}`, `新角色${roles.length + 1}`, voice),
    };
    setRoles((current) => [...current, role]);
    try {
      const data = await requestJson<{ roles: ApiRoleCard[] }>("/api/roles", {
        method: "POST",
        body: JSON.stringify(toApiRole(role)),
      });
      setRoles(data.roles.map(fromApiRole));
      setApiStatus(`已新增角色：${role.name}`);
    } catch (error) {
      setApiStatus(`新增角色同步失败，已保留本地角色：${String(error)}`);
    }
  }

  async function deleteRole(roleId: string) {
    const payload = { roles: roles.map(toApiRole), utterances_by_paragraph: utteranceGroupsToApi(utterancesByParagraph) };
    try {
      const data = await requestJson<{ roles: ApiRoleCard[]; utterances_by_paragraph: Record<string, ApiUtterance[]> }>(
        `/api/roles/${roleId}`,
        { method: "DELETE", body: JSON.stringify(payload) },
      );
      setRoles(data.roles.map(fromApiRole));
      setUtterancesByParagraph(apiUtterancesToGroups(data.utterances_by_paragraph, paragraphs, data.roles.map(fromApiRole)));
      setApiStatus("角色删除成功");
    } catch (error) {
      const shouldUnbind = window.confirm(`角色正在被语句引用，是否解除这些语句的角色绑定并删除？\n${String(error)}`);
      if (!shouldUnbind) {
        setApiStatus(`角色删除已取消：${String(error)}`);
        return;
      }
      try {
        const data = await requestJson<{ roles: ApiRoleCard[]; utterances_by_paragraph: Record<string, ApiUtterance[]> }>(
          `/api/roles/${roleId}`,
          { method: "DELETE", body: JSON.stringify({ ...payload, action: "unbind" }) },
        );
        const nextRoles = data.roles.map(fromApiRole);
        setRoles(nextRoles);
        setUtterancesByParagraph(apiUtterancesToGroups(data.utterances_by_paragraph, paragraphs, nextRoles));
        setApiStatus("已解除引用语句的角色绑定并删除角色");
      } catch (secondError) {
        setApiStatus(`角色删除失败：${String(secondError)}`);
      }
    }
  }

  function playVoicePreview(voice?: VoiceResource) {
    if (!voice) {
      setApiStatus("播放音色失败：该角色尚未选择音色");
      return;
    }
    const audio = new Audio(voiceAudioSrc(voice));
    audio
      .play()
      .then(() => setApiStatus(`正在播放音色：${voice.name}`))
      .catch((error) => setApiStatus(`播放音色失败：${String(error)}`));
  }

  async function runAiRoleAnalysis() {
    if (!activeChapter || visibleParagraphs.length === 0) return;
    setAiOneClickRunning(true);
    setRoleMatchingProgress(8);
    setApiStatus("AI角色分析正在同步当前章节、创建角色并匹配音色");
    try {
      await syncCurrentChapterParagraphs(false);
      const data = await requestJson<AiOneClickStartResponse>(
        `/api/chapters/${activeChapter.chapterId}/ai-one-click-analysis/start`,
        { method: "POST", body: JSON.stringify({}) },
      );
      if (data.voices?.length) setVoices(data.voices.map(fromApiVoice));
      if (data.roles?.length) setRoles(data.roles.map(fromApiRole));
      setAiOneClickThreadId(data.thread_id);
      setAiRoleCandidates(data.role_candidates);
      setAiOneClickWaitingForRoles(true);
      setRoleMatchingProgress(35);
      const autoSummary = data.auto_role_report
        ? `自动新增 ${data.auto_role_report.added_count} 个角色，生成 ${data.auto_role_report.generated_voice_count} 个音色。`
        : "";
      setApiStatus(`${data.message} ${autoSummary} 请检查角色列表后点击“AI角色匹配”。`);
    } catch (error) {
      resetAiOneClickState();
      setRoleMatchingProgress(100);
      setApiStatus(`AI角色分析失败：${String(error)}`);
    } finally {
      setAiOneClickRunning(false);
    }
  }

  async function runAiRoleMatching() {
    if (!aiOneClickThreadId) return;
    setAiOneClickRunning(true);
    setAiOneClickWaitingForRoles(false);
    setRoleMatchingProgress(45);
    setApiStatus("AI角色匹配正在划分语句并为未绑定语句选择角色");
    try {
      const readyUtterances = await ensureChapterStatementsReady();
      const response = await fetch(`/api/ai-one-click-analysis/${aiOneClickThreadId}/roles-completed-stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          roles: roles.map(toApiRole),
          utterances_by_paragraph: utteranceGroupsToApi(readyUtterances),
        }),
      });
      if (!response.ok) throw new Error(await response.text());
      if (!response.body) throw new Error("AI角色匹配没有返回流式响应");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.trim()) continue;
          handleAiOneClickStreamEvent(JSON.parse(line));
        }
        if (done) break;
      }
      if (buffer.trim()) handleAiOneClickStreamEvent(JSON.parse(buffer));
    } catch (error) {
      setAiOneClickWaitingForRoles(true);
      setRoleMatchingProgress(100);
      setApiStatus(`AI角色匹配失败：${String(error)}`);
    } finally {
      setAiOneClickRunning(false);
    }
  }

  function handleAiOneClickStreamEvent(event: { event: string; data: any }) {
    if (event.event === "role_selected") {
      applyAiRoleSelectionEvent(event.data as AiRoleSelectionEvent);
      setRoleMatchingProgress((current) => Math.min(95, Math.max(current + 5, 55)));
      return;
    }
    if (event.event === "completed") {
      const data = event.data as AiOneClickResumeResponse;
      setUtterancesByParagraph(apiUtterancesToGroups(data.utterances_by_paragraph, paragraphs, roles));
      setConfirmed(true);
      setChapterBackendSynced(true);
      setAiOneClickWaitingForRoles(false);
      setRoleMatchingProgress(100);
      setApiStatus(data.message);
      return;
    }
    if (event.event === "failed") {
      const message = event.data?.failure?.message ?? event.data?.message ?? "模型输出未通过校验";
      setAiOneClickWaitingForRoles(true);
      setRoleMatchingProgress(100);
      setApiStatus(`AI角色匹配失败：${message}`);
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
        `/api/utterances/${utterance.utteranceId}/speech`,
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
      const message = error instanceof Error ? error.message : String(error);
      updateUtterance(utterance.paragraphId, utterance.utteranceId, "audioStatus", `音频生成失败：${message}`);
      setVoiceGenerationProgress(100);
    } finally {
      setGeneratingUtteranceIds((current) => ({ ...current, [utterance.utteranceId]: false }));
    }
  }

  async function generateChapterDubbing() {
    if (!activeChapter) {
      setApiStatus("一键生成配音失败：请先选择章节");
      return;
    }
    setVoiceGenerationProgress(10);
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
      }>(`/api/chapters/${activeChapter.chapterId}/speech/batch`, {
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
      setApiStatus(`一键生成配音完成：成功 ${data.success_count} 条，跳过 ${data.skipped_count} 条；分组 ${groupSummary || "无待生成"}${errorSummary}`);
    } catch (error) {
      setVoiceGenerationProgress(100);
      setApiStatus(`一键生成配音失败：${String(error)}`);
    }
  }

  async function exportChapterAudio() {
    if (!activeChapter) {
      setApiStatus("一键导出失败：请先选择章节");
      return;
    }
    setApiStatus("正在导出当前章节逐条音频和 manifest");
    try {
      const data = await requestJson<{
        export_dir: string;
        manifest_path: string;
        item_count: number;
        missing_count: number;
        full_audio_path: string | null;
        message: string;
      }>(`/api/chapters/${activeChapter.chapterId}/audio/export`, {
        method: "POST",
        body: JSON.stringify({
          chapter_title: activeChapter.title,
          roles: roles.map(toApiRole),
          utterances_by_paragraph: utteranceGroupsToApi(utterancesByParagraph),
          pause_ms: 300,
          speed: 1.0,
        }),
      });
      const fullAudio = data.full_audio_path ? `；完整音频：${data.full_audio_path}` : "";
      setApiStatus(`一键导出完成：${data.item_count} 条，manifest：${data.manifest_path}${fullAudio}；${data.message}`);
    } catch (error) {
      setApiStatus(`一键导出失败：${String(error)}`);
    }
  }

  async function saveVoiceResource(payload: Omit<Partial<VoiceResource>, "suitableRoleTypes"> & { suitableRoleTypes?: string[] | string }): Promise<boolean> {
    try {
      const data = await requestJson<{ voice: ApiVoiceResource; voices: ApiVoiceResource[] }>("/api/voice-resources", {
        method: "POST",
        body: JSON.stringify(toApiVoice(payload)),
      });
      setVoices(data.voices.map(fromApiVoice));
      setApiStatus(`保存音色成功：${data.voice.name}`);
      return true;
    } catch (error) {
      setApiStatus(`保存音色失败：${String(error)}`);
      return false;
    }
  }

  async function updateVoiceResource(voice: VoiceResource) {
    try {
      const data = await requestJson<{ voice: ApiVoiceResource; voices: ApiVoiceResource[] }>(`/api/voice-resources/${voice.voiceId}`, {
        method: "PATCH",
        body: JSON.stringify(toApiVoice(voice)),
      });
      setVoices(data.voices.map(fromApiVoice));
      setApiStatus(`保存音色成功：${data.voice.name}`);
    } catch (error) {
      setApiStatus(`保存音色失败：${String(error)}`);
    }
  }

  async function handleReferenceAudioFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setApiStatus(`正在上传参考音频文件：${file.name}`);
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result ?? ""));
      reader.onerror = () => reject(reader.error ?? new Error("读取参考音频失败"));
      reader.readAsDataURL(file);
    });
    const dataBase64 = dataUrl.split(",")[1] ?? "";
    const data = await requestJson<{ reference_audio_path: string }>("/api/voice-resources/reference-audio", {
      method: "POST",
      body: JSON.stringify({ filename: file.name, data_base64: dataBase64 }),
    });
    if (newVoiceAudioPreviewUrl) URL.revokeObjectURL(newVoiceAudioPreviewUrl);
    setNewVoiceAudioPreviewUrl(URL.createObjectURL(file));
    setNewVoice((current) => ({
      ...current,
      referenceAudioPath: data.reference_audio_path,
      playableAudioPath: data.reference_audio_path,
    }));
    setApiStatus(`参考音频文件已选择：${file.name}`);
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
        "/api/voice-resources/generate",
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
      const requirement = data.model_requirement ? `；${data.model_requirement}` : "";
      const prefix = data.generation_status === "substitute" ? "生成音色使用占位预览" : "生成音色成功";
      setApiStatus(`${prefix}：${data.generation_note}${requirement}`);
    } catch (error) {
      setGeneratedVoiceProgress(100);
      setApiStatus(`生成音色失败：${String(error)}`);
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
        const data = await requestJson<{ voices: ApiVoiceResource[] }>(`/api/voice-resources/${voice.voiceId}`, {
          method: "DELETE",
        });
        remaining = data.voices.map(fromApiVoice);
      }
      setVoices(remaining);
      setSelectedVoiceIds({});
      setApiStatus(`删除选中音色成功：${selected.length} 个`);
    } catch (error) {
      setApiStatus(`删除选中音色失败：${String(error)}`);
    }
  }

  async function saveRemoteModelConfig() {
    try {
      const data = await requestJson<{ config: ModelConfig }>("/api/model-config", {
        method: "PATCH",
        body: JSON.stringify({ llm: modelConfig.llm }),
      });
      setModelConfig(normalizeModelConfig(data.config));
      setApiStatus("远端模型配置保存成功");
    } catch (error) {
      setApiStatus(`远端模型配置保存失败：${String(error)}`);
    }
  }

  async function saveLocalModelConfig() {
    try {
      const data = await requestJson<{ config: ModelConfig }>("/api/model-config", {
        method: "PATCH",
        body: JSON.stringify({ tts: modelConfig.tts }),
      });
      setModelConfig(normalizeModelConfig(data.config));
      setApiStatus("本地模型配置保存成功");
    } catch (error) {
      setApiStatus(`本地模型配置保存失败：${String(error)}`);
    }
  }

  async function saveChapterAgentModelConfig() {
    try {
      const data = await requestJson<{ config: ModelConfig }>("/api/model-config", {
        method: "PATCH",
        body: JSON.stringify({ chapter_agent: modelConfig.chapter_agent }),
      });
      setModelConfig(normalizeModelConfig(data.config));
      setApiStatus("小说格式解析智能体配置保存成功");
    } catch (error) {
      setApiStatus(`小说格式解析智能体配置保存失败：${String(error)}`);
    }
  }

  async function testRemoteModelLink() {
    try {
      const data = await requestJson<{ message: string }>("/api/model-config/llm/test", {
        method: "POST",
        body: JSON.stringify({ llm: modelConfig.llm }),
      });
      setApiStatus(data.message || "远端模型连接成功");
    } catch (error) {
      setApiStatus(`测试链接失败：${String(error)}`);
    }
  }

  async function testChapterAgentModelLink() {
    try {
      const data = await requestJson<{ message: string }>("/api/model-config/chapter-agent/test", {
        method: "POST",
        body: JSON.stringify({ chapter_agent: modelConfig.chapter_agent }),
      });
      setApiStatus(data.message || "小说格式解析智能体连接成功");
    } catch (error) {
      setApiStatus(`小说格式解析智能体测试链接失败：${String(error)}`);
    }
  }

  async function startLocalTtsService() {
    if (localTtsStarting) return;
    setLocalTtsStarting(true);
    setLocalTtsStartProgress(8);
    setApiStatus("正在启动本地 TTS 服务并加载 Base/VoiceDesign 模型");
    let currentProgress = 8;
    const progressTimer = window.setInterval(() => {
      currentProgress = Math.min(95, currentProgress + (currentProgress < 60 ? 7 : 3));
      setLocalTtsStartProgress(currentProgress);
    }, 1000);
    try {
      const data = await requestJson<LocalTtsStartResponse>("/api/model-config/tts/start", {
        method: "POST",
        body: JSON.stringify({ tts: modelConfig.tts }),
      });
      setLocalTtsStartProgress(data.progress ?? 100);
      setApiStatus(data.message || "本地 TTS 服务启动成功，模型加载完成");
    } catch (error) {
      setLocalTtsStartProgress(100);
      setApiStatus(`启动服务失败：${String(error)}`);
    } finally {
      window.clearInterval(progressTimer);
      setLocalTtsStarting(false);
    }
  }

  function renderMainPage() {
    return (
      <main
        className={chapterSidebarCollapsed ? "workbench chapters-collapsed" : "workbench"}
        aria-label="NovelVoice-Agent v0.3.4 主页面"
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
                    AI小说格式解析
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
                <ProgressBar label="AI角色匹配进度" value={roleMatchingProgress} />
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
                              {voices.map((item) => (
                                <option key={item.voiceId} value={item.voiceId}>
                                  {item.name}
                                </option>
                              ))}
                            </select>
                          </label>
                          <button
                            aria-label="播放音色"
                            className="icon-button"
                            type="button"
                            title="播放音色"
                            onClick={() => playVoicePreview(voice)}
                          >
                            ▶
                          </button>
                        </div>
                        <button className="tool-button amber" type="button" onClick={() => void deleteRole(role.roleId)}>
                          删除角色
                        </button>
                        <p>
                          <strong>音色描述</strong>
                          {voice?.description ?? role.voiceDescription ?? role.description}
                        </p>
                        <p>
                          <strong>语音具体内容</strong>
                          {voice?.referenceText ?? role.voiceSampleText ?? role.referenceText}
                        </p>
                        <p>
                          <strong>音色匹配</strong>
                          {role.voiceMatchReason ?? "用户可手动调整"}
                        </p>
                        {voice && <audio controls src={voiceAudioSrc(voice)} />}
                      </article>
                    );
                  })}
                </div>
                {aiRoleCandidates.length > 0 && (
                  <div className="role-analysis-panel" aria-label="AI角色候选建议">
                    <div className="section-title">AI角色候选建议</div>
                    <small>请检查角色列表，必要时手动调整角色或音色；随后点击章节顶部“AI角色匹配”。模型建议仅作参考。</small>
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
              <p>上传小说后点击左侧“AI小说格式解析”，当前章节区暂不渲染具体正文。</p>
            </div>
          ) : !activeChapter ? (
            <div className="empty-state">
              <div className="section-title">当前章节</div>
              <h2>请选择小说章节</h2>
              <p>选择某个章节后，左侧显示完整正文，右侧显示 AI角色匹配后的台词。</p>
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
                    disabled={aiOneClickRunning || visibleParagraphs.length === 0}
                  >
                    AI角色分析
                  </button>
                  <button
                    className="tool-button purple"
                    type="button"
                    onClick={() => void runAiRoleMatching()}
                    disabled={aiOneClickRunning || !aiOneClickWaitingForRoles || !aiOneClickThreadId}
                  >
                    AI角色匹配
                  </button>
                  <button
                    className="tool-button sky"
                    type="button"
                    onClick={() => void generateChapterDubbing()}
                    disabled={!confirmed}
                  >
                    一键生成配音
                  </button>
                  <button
                    className="tool-button amber"
                    type="button"
                    onClick={() => void exportChapterAudio()}
                    disabled={!confirmed}
                  >
                    一键导出
                  </button>
                  <span>{confirmed ? "台词已生成，可人工检查、批量配音或导出" : "按流程先执行 AI角色分析，再执行 AI角色匹配"}</span>
                </div>
              </header>

              <section className="chapter-workspace-grid">
                <article className="panel chapter-reader" aria-label="当前章节完整小说内容">
                  <div className="section-title">当前章节完整小说内容</div>
                  <div className="chapter-reader-body">{currentChapterText || "当前章节正文为空。"}</div>
                </article>

                <article className="panel statement-panel" aria-label="划分语句与角色匹配">
                  <div className="section-heading">
                    <div className="section-title">划分语句与角色匹配</div>
                    {confirmed && primaryStatementParagraphId && (
                      <button className="tool-button amber" type="button" onClick={() => addUtteranceAfter(primaryStatementParagraphId)}>
                        添加音频生成
                      </button>
                    )}
                  </div>
                  {flattenedUtterances.length === 0 ? (
                    <div className="statement-empty">
                      点击“AI角色匹配”后，这里只显示拆分后的语句、匹配角色和音频生成控件。
                    </div>
	                  ) : (
	                    <div className="statement-list">
	                      {flattenedUtterances.map((utterance) => (
                        <article className="utterance-card" key={utterance.utteranceId}>
                          <div className="utterance-toolbar">
                            <strong>{utterance.utteranceId}</strong>
                            <button type="button" onClick={() => deleteUtterance(utterance.paragraphId, utterance.utteranceId)}>
                              删除音频生成
                            </button>
                          </div>
                          <label className="utterance-wide">
                            语句文本
                            <input
                              value={utterance.text}
                              onChange={(event) =>
                                updateUtterance(utterance.paragraphId, utterance.utteranceId, "text", event.target.value)
                              }
                              aria-label={`${utterance.utteranceId} 语句文本`}
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
                          {(() => {
                            const isGeneratingThisUtterance = Boolean(generatingUtteranceIds[utterance.utteranceId]);
                            return (
                              <button
                                className="tool-button sky"
                                type="button"
                                disabled={isGeneratingThisUtterance}
                                onClick={() => void generateAudio(utterance)}
                              >
                                {isGeneratingThisUtterance ? "正在生成" : "音频生成"}
                              </button>
                            );
                          })()}
                          <output>{utterance.audioStatus}</output>
                          {utterance.audioUrl && <audio controls src={utterance.audioUrl} />}
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
          <div className="section-title">音色资源库列表</div>
          <small className="status-message" aria-label="音色资源库反馈">{apiStatus}</small>
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
                <audio controls src={voiceAudioSrc(voice)} />
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
            <div className="section-title">添加资源到资源库列表</div>
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
            {newVoiceAudioPreviewUrl && <audio controls src={newVoiceAudioPreviewUrl} />}
            <button className="tool-button teal" type="button" onClick={() => void saveVoiceResource(newVoice)}>
              保存音色
            </button>
          </div>

          <div className="panel">
            <div className="section-title">生成资源到资源库列表</div>
            <small>
              当前 Base 模型不会凭描述生成新音色；若返回占位预览，请下载并启动 Qwen3-TTS-12Hz-1.7B-VoiceDesign。
              没有成功调用 VoiceDesign 模型时，会显示模型需求并播放本地占位预览。
            </small>
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
                <audio controls src={generatedVoicePreviewUrl} />
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
          <div className="section-title">远端模型</div>
          <small className="status-message" aria-label="模型配置反馈">{apiStatus}</small>
          <label>
            Base URL
            <input
              value={modelConfig.llm.base_url}
              onChange={(event) =>
                setModelConfig((current) => ({ ...current, llm: { ...current.llm, base_url: event.target.value } }))
              }
            />
          </label>
          <label>
            模型名称
            <input
              value={modelConfig.llm.model}
              onChange={(event) =>
                setModelConfig((current) => ({ ...current, llm: { ...current.llm, model: event.target.value } }))
              }
            />
          </label>
          <label>
            api_key
            <input
              type="password"
              value={modelConfig.llm.api_key}
              onChange={(event) =>
                setModelConfig((current) => ({ ...current, llm: { ...current.llm, api_key: event.target.value } }))
              }
            />
          </label>
          <div className="toolbar-row">
            <button className="tool-button teal" type="button" onClick={() => void saveRemoteModelConfig()}>
              保存模型配置
            </button>
            <button className="tool-button sky" type="button" onClick={() => void testRemoteModelLink()}>
              测试链接
            </button>
          </div>
        </section>

        <section className="panel">
          <div className="section-title">本地模型</div>
          <label>
            BASE_URL
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
          <div className="toolbar-row">
            <button className="tool-button teal" type="button" onClick={() => void saveLocalModelConfig()}>
              保存模型配置
            </button>
            <button className="tool-button purple" type="button" disabled={localTtsStarting} onClick={() => void startLocalTtsService()}>
              {localTtsStarting ? "启动中" : "启动服务"}
            </button>
          </div>
          <ProgressBar label="启动服务进度" value={localTtsStartProgress} />
        </section>

        <section className="panel">
          <div className="section-title">AI小说格式解析智能体</div>
          <label>
            Base URL
            <input
              value={modelConfig.chapter_agent.base_url}
              onChange={(event) =>
                setModelConfig((current) => ({
                  ...current,
                  chapter_agent: { ...current.chapter_agent, base_url: event.target.value },
                }))
              }
            />
          </label>
          <label>
            模型名称
            <input
              value={modelConfig.chapter_agent.model}
              onChange={(event) =>
                setModelConfig((current) => ({
                  ...current,
                  chapter_agent: { ...current.chapter_agent, model: event.target.value },
                }))
              }
            />
          </label>
          <label>
            api_key
            <input
              type="password"
              value={modelConfig.chapter_agent.api_key}
              onChange={(event) =>
                setModelConfig((current) => ({
                  ...current,
                  chapter_agent: { ...current.chapter_agent, api_key: event.target.value },
                }))
              }
            />
          </label>
          <div className="toolbar-row">
            <button className="tool-button teal" type="button" onClick={() => void saveChapterAgentModelConfig()}>
              保存智能体配置
            </button>
            <button className="tool-button sky" type="button" onClick={() => void testChapterAgentModelLink()}>
              测试链接
            </button>
          </div>
        </section>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <h1>NovelVoice-Agent v0.3.4</h1>
        <nav className="tabbar" aria-label="页面切换">
          {[
            ["main", "主页面"],
            ["voices", "音色资源库"],
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
      </header>
      {page === "main" && renderMainPage()}
      {page === "voices" && renderVoiceLibraryPage()}
      {page === "models" && renderModelConfigPage()}
    </div>
  );
}

export default App;
