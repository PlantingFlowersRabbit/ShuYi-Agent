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

type ApiChapter = {
  chapter_id: string;
  title: string;
  body: string;
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
  description: string;
  referenceText: string;
  referenceAudioPath: string;
  generated: boolean;
};

type ApiVoiceResource = {
  voice_id: string;
  name: string;
  description: string;
  reference_text: string;
  reference_audio_path: string;
  generated: boolean;
};

type RoleCard = {
  roleId: string;
  name: string;
  description: string;
  voiceMode: VoiceMode;
  voiceResourceId: string;
  referenceAudioPath: string;
  referenceText: string;
  designPrompt: string;
};

type ApiRoleCard = {
  role_id: string;
  name: string;
  description: string;
  voice_mode: VoiceMode;
  voice_resource_id: string | null;
  reference_audio_path: string | null;
  reference_text: string | null;
  design_prompt: string | null;
};

type UtteranceDraft = {
  utteranceId: string;
  paragraphId: string;
  text: string;
  roleId: string;
  speakerName: string;
  voiceMode: VoiceMode;
  voiceResourceId: string;
  emotion: string;
  language: string;
  xVectorOnly: boolean;
  speed: number;
  volume: number;
  otherControlText: string;
  audioStatus: string;
  audioUrl?: string;
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
  };
};

const sampleNovel = `1.变成蘑菇的公爵千金
“放开我！你们是谁？快放开我！”

一醒来就发现自己被装麻袋了的伊南娜竭力扭动身体。

“佩罗，你昏迷术掺水了？这就醒了。”`;

const MAX_NOVEL_PREVIEW_CHARS = 700;
const DEFAULT_GENERATED_VOICE_TEXT = "这是一段用于试听新音色的语音。";

const EMOTION_OPTIONS = ["", "中性", "开心", "悲伤", "愤怒", "害怕", "惊讶", "温柔", "紧张", "严肃"];
const LANGUAGE_OPTIONS = [
  { value: "Chinese", label: "中文" },
  { value: "English", label: "英文" },
];

const defaultVoices: VoiceResource[] = [
  {
    voiceId: "voice-male-narrator",
    name: "男声旁白",
    description: "沉稳、叙事感强，适合旁白和长段说明。",
    referenceText: "探索那些被遗忘的地下空间，比如废弃的地铁站、防空洞。",
    referenceAudioPath: "/Users/gaojing/Downloads/真实测试样本/音频/男声旁白/男声旁白.mp3",
    generated: false,
  },
  {
    voiceId: "voice-young-male",
    name: "年轻男",
    description: "清亮自然，适合年轻男性角色对白。",
    referenceText: "光柱最终落在那株已经遍布猩红纹路的神木幼苗上。",
    referenceAudioPath: "/Users/gaojing/Downloads/真实测试样本/音频/年轻男/年轻男.mp3",
    generated: false,
  },
  {
    voiceId: "voice-yujie",
    name: "御姐音",
    description: "成熟亲近，适合女性角色对白。",
    referenceText: "宝宝，今天你可得好好陪我逛逛。",
    referenceAudioPath: "/Users/gaojing/Downloads/真实测试样本/音频/御姐音/御姐音.mp3",
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
    model_path: "",
  },
};

function initialPageFromUrl(): Page {
  const page = new URLSearchParams(window.location.search).get("page");
  return page === "voices" || page === "models" ? page : "main";
}

function makeNovelPreview(text: string): string {
  const trimmed = text.trimStart();
  if (trimmed.length <= MAX_NOVEL_PREVIEW_CHARS) return trimmed;
  return `${trimmed.slice(0, MAX_NOVEL_PREVIEW_CHARS)}\n\n……仅展示开头预览，完整小说已保留用于章节划分。`;
}

function parseChapters(text: string): Chapter[] {
  const headingPattern =
    /^[ \t]*((?:第[一二三四五六七八九十百千万零〇两\d]+[章节回][^\n\r]*)|(?:\d+[.．、][^\n\r]*))$/gm;
  const matches = Array.from(text.matchAll(headingPattern));
  if (matches.length === 0) {
    return text.trim() ? [{ chapterId: "chapter-0001", title: "未分章正文", body: text.trim() }] : [];
  }
  return matches.map((match, index) => {
    const next = matches[index + 1];
    const bodyStart = (match.index ?? 0) + match[0].length;
    const bodyEnd = next?.index ?? text.length;
    return {
      chapterId: `chapter-${String(index + 1).padStart(4, "0")}`,
      title: match[1].trim(),
      body: text.slice(bodyStart, bodyEnd).replace(/^-{3,}\s*/, "").trim(),
    };
  });
}

function parseChapterIndex(text: string): Chapter[] {
  const headingPattern =
    /^[ \t]*((?:第[一二三四五六七八九十百千万零〇两\d]+[章节回][^\n\r]*)|(?:\d+[.．、][^\n\r]*))$/gm;
  const matches = Array.from(text.matchAll(headingPattern));
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
      title: match[1].trim(),
      body: "",
      bodyStart: (match.index ?? 0) + match[0].length,
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
    description: voice.description,
    referenceText: voice.reference_text,
    referenceAudioPath: voice.reference_audio_path,
    generated: voice.generated,
  };
}

function fromApiRole(role: ApiRoleCard): RoleCard {
  return {
    roleId: role.role_id,
    name: role.name,
    description: role.description,
    voiceMode: role.voice_mode,
    voiceResourceId: role.voice_resource_id ?? "",
    referenceAudioPath: role.reference_audio_path ?? "",
    referenceText: role.reference_text ?? "",
    designPrompt: role.design_prompt ?? "",
  };
}

function toApiVoice(voice: Partial<VoiceResource>): Record<string, unknown> {
  return {
    voice_id: voice.voiceId,
    name: voice.name,
    description: voice.description,
    reference_text: voice.referenceText,
    reference_audio_path: voice.referenceAudioPath,
    generated: voice.generated,
  };
}

function voiceAudioSrc(voice: VoiceResource): string {
  return `/api/voice-resources/${voice.voiceId}/audio`;
}

function createDefaultRoles(voices: VoiceResource[]): RoleCard[] {
  const fallback = voices[0] ?? defaultVoices[0];
  const pick = (voiceId: string) => voices.find((voice) => voice.voiceId === voiceId) ?? fallback;
  const narrator = pick("voice-male-narrator");
  const youngMale = pick("voice-young-male");
  const yujie = pick("voice-yujie");
  return [
    {
      roleId: "narrator",
      name: "旁白",
      description: narrator.description,
      voiceMode: "voice_cloning",
      voiceResourceId: narrator.voiceId,
      referenceAudioPath: narrator.referenceAudioPath,
      referenceText: narrator.referenceText,
      designPrompt: "",
    },
    {
      roleId: "male_lead",
      name: "年轻男",
      description: youngMale.description,
      voiceMode: "voice_cloning",
      voiceResourceId: youngMale.voiceId,
      referenceAudioPath: youngMale.referenceAudioPath,
      referenceText: youngMale.referenceText,
      designPrompt: "",
    },
    {
      roleId: "female_lead",
      name: "御姐音",
      description: yujie.description,
      voiceMode: "voice_cloning",
      voiceResourceId: yujie.voiceId,
      referenceAudioPath: yujie.referenceAudioPath,
      referenceText: yujie.referenceText,
      designPrompt: "",
    },
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

function makeUtteranceDraft(paragraph: ParagraphModule, roles: RoleCard[]): UtteranceDraft {
  const role = roles[0];
  return {
    utteranceId: `${paragraph.paragraphId}-u-001`,
    paragraphId: paragraph.paragraphId,
    text: paragraph.text,
    roleId: role.roleId,
    speakerName: role.name,
    voiceMode: role.voiceMode,
    voiceResourceId: role.voiceResourceId,
    emotion: "",
    language: "Chinese",
    xVectorOnly: false,
    speed: 1,
    volume: 1,
    otherControlText: "",
    audioStatus: "尚未生成",
  };
}

function fromApiUtterance(utterance: ApiUtterance, paragraph: ParagraphModule, roles: RoleCard[]): UtteranceDraft {
  const fallbackRole = roles[0];
  const role = roles.find((item) => item.roleId === utterance.speaker_role_id) ?? fallbackRole;
  return {
    utteranceId: utterance.utterance_id,
    paragraphId: utterance.paragraph_id ?? paragraph.paragraphId,
    text: utterance.text,
    roleId: role.roleId,
    speakerName: utterance.speaker_name || role.name,
    voiceMode: role.voiceMode,
    voiceResourceId: role.voiceResourceId,
    emotion: utterance.emotion || "",
    language: "Chinese",
    xVectorOnly: false,
    speed: utterance.speed ?? 1,
    volume: utterance.volume ?? 1,
    otherControlText: utterance.design_prompt ?? "",
    audioStatus: "尚未生成",
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
      model_path: config.tts?.model_path ?? "",
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
  const [page, setPage] = useState<Page>(() => initialPageFromUrl());
  const [novelPreview, setNovelPreview] = useState(() => makeNovelPreview(sampleNovel));
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [activeChapterId, setActiveChapterId] = useState("");
  const [paragraphs, setParagraphs] = useState<ParagraphModule[]>([]);
  const [hasSplitChapters, setHasSplitChapters] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [voices, setVoices] = useState<VoiceResource[]>(defaultVoices);
  const [roles, setRoles] = useState<RoleCard[]>(() => createDefaultRoles(defaultVoices));
  const [utterancesByParagraph, setUtterancesByParagraph] = useState<Record<string, UtteranceDraft[]>>({});
  const [chapterBackendSynced, setChapterBackendSynced] = useState(false);
  const [selectedVoiceIds, setSelectedVoiceIds] = useState<Record<string, boolean>>({});
  const [newVoice, setNewVoice] = useState({
    name: "",
    description: "",
    referenceText: "",
    referenceAudioPath: "",
  });
  const [generatedVoice, setGeneratedVoice] = useState({
    name: "",
    description: "",
    referenceText: DEFAULT_GENERATED_VOICE_TEXT,
  });
  const [newVoiceAudioPreviewUrl, setNewVoiceAudioPreviewUrl] = useState("");
  const [generatedVoicePreview, setGeneratedVoicePreview] = useState<VoiceResource | null>(null);
  const [generatedVoicePreviewUrl, setGeneratedVoicePreviewUrl] = useState("");
  const [modelConfig, setModelConfig] = useState<ModelConfig>(defaultModelConfig);
  const [apiStatus, setApiStatus] = useState("等待上传小说");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [chapterSplitProgress, setChapterSplitProgress] = useState(0);
  const [segmentationProgress, setSegmentationProgress] = useState(0);
  const [voiceGenerationProgress, setVoiceGenerationProgress] = useState(0);
  const [generatedVoiceProgress, setGeneratedVoiceProgress] = useState(0);

  const activeChapter = chapters.find((chapter) => chapter.chapterId === activeChapterId);
  const visibleParagraphs = paragraphs.filter((paragraph) => !paragraph.deleted);
  const roleOptions = useMemo(
    () => roles.map((role) => ({ value: role.roleId, label: role.name })),
    [roles],
  );

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
    setApiStatus(status);
  }

  async function handleTxtFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploadProgress(8);
    setApiStatus(`正在读取小说：${file.name}`);
    const text = await file.text();
    fullNovelTextRef.current = text;
    setNovelPreview(makeNovelPreview(text));
    setChapters([]);
    setActiveChapterId("");
    setParagraphs([]);
    setHasSplitChapters(false);
    setChapterBackendSynced(false);
    setChapterSplitProgress(0);
    setSegmentationProgress(0);
    setVoiceGenerationProgress(0);
    setUploadProgress(62);
    setApiStatus("小说已上传，仅展示开头预览；点击“划分章节”生成章节目录");
    setUploadProgress(100);
  }

  function splitChapters() {
    setChapterSplitProgress(12);
    const parsed = parseChapterIndex(fullNovelTextRef.current);
    setChapterSplitProgress(76);
    applyChapters(parsed, "章节目录已划分；选择左侧章节后才加载该章正文");
    setChapterSplitProgress(100);
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
    setSegmentationProgress(0);
    setVoiceGenerationProgress(0);
    setApiStatus(`已加载章节：${chapter.title}`);
  }

  async function syncCurrentChapterParagraphs(confirm = false) {
    if (!activeChapter) throw new Error("请选择章节");
    const data = await requestJson<{ paragraphs: ApiParagraph[]; can_segment: boolean }>(
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
    setParagraphs(data.paragraphs.map(fromApiParagraph));
    setConfirmed(data.can_segment);
    setChapterBackendSynced(true);
  }

  function updateParagraph(paragraphId: string, updates: Partial<ParagraphModule>) {
    setParagraphs((current) =>
      current.map((paragraph) =>
        paragraph.paragraphId === paragraphId ? { ...paragraph, ...updates } : paragraph,
      ),
    );
    if ("text" in updates || updates.deleted) {
      setConfirmed(false);
      setChapterBackendSynced(false);
      setUtterancesByParagraph({});
    }
  }

  async function confirmParagraphs() {
    if (visibleParagraphs.length === 0) return;
    setApiStatus("正在同步当前章节段落并确认");
    try {
      await syncCurrentChapterParagraphs(true);
      setApiStatus("段落已确认，可以使用 Qwen/Qwen3-8B 执行语句划分");
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
    };
  }

  function updateRole(roleId: string, updates: Partial<RoleCard>) {
    let updatedRole: RoleCard | undefined;
    setRoles((current) =>
      current.map((role) => {
        if (role.roleId !== roleId) return role;
        const merged = { ...role, ...updates };
        updatedRole = updates.voiceResourceId ? applyVoiceToRole(merged, updates.voiceResourceId) : merged;
        return updatedRole;
      }),
    );
    if (updatedRole) {
      requestJson(`/api/roles/${roleId}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: updatedRole.name,
          description: updatedRole.description,
          voice_mode: updatedRole.voiceMode,
          voice_resource_id: updatedRole.voiceResourceId,
          reference_audio_path: updatedRole.referenceAudioPath,
          reference_text: updatedRole.referenceText,
          design_prompt: updatedRole.designPrompt || null,
        }),
      }).catch((error) => setApiStatus(`角色同步失败：${String(error)}`));
    }
  }

  async function addRole() {
    const voice = voices[0];
    if (!voice) {
      setApiStatus("新增角色失败：请先添加至少一个音色资源");
      return;
    }
    const role: RoleCard = {
      roleId: `custom_role_${Date.now()}`,
      name: `新角色${roles.length + 1}`,
      description: voice.description,
      voiceMode: "voice_cloning",
      voiceResourceId: voice.voiceId,
      referenceAudioPath: voice.referenceAudioPath,
      referenceText: voice.referenceText,
      designPrompt: "",
    };
    setRoles((current) => [...current, role]);
    try {
      const data = await requestJson<{ roles: ApiRoleCard[] }>("/api/roles", {
        method: "POST",
        body: JSON.stringify({
          role_id: role.roleId,
          name: role.name,
          description: role.description,
          voice_mode: role.voiceMode,
          voice_resource_id: role.voiceResourceId,
          reference_audio_path: role.referenceAudioPath,
          reference_text: role.referenceText,
          design_prompt: null,
        }),
      });
      setRoles(data.roles.map(fromApiRole));
      setApiStatus(`已新增角色：${role.name}`);
    } catch (error) {
      setApiStatus(`新增角色同步失败，已保留本地角色：${String(error)}`);
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

  async function runSegmentation() {
    if (!confirmed) return;
    setApiStatus("正在使用 Qwen/Qwen3-8B 进行说话人粒度语句划分");
    setSegmentationProgress(0);
    if (!chapterBackendSynced) {
      await syncCurrentChapterParagraphs(true);
    }
    await runQwenSegmentation();
  }

  async function runQwenSegmentation() {
    const grouped: Record<string, UtteranceDraft[]> = {};
    try {
      for (const [index, paragraph] of visibleParagraphs.entries()) {
        const data = await requestJson<{ ok: boolean; utterances: ApiUtterance[]; error?: string }>(
          `/api/paragraphs/${paragraph.paragraphId}/segment`,
          { method: "POST", body: JSON.stringify({}) },
        );
        grouped[paragraph.paragraphId] = data.ok
          ? data.utterances.map((utterance) => fromApiUtterance(utterance, paragraph, roles))
          : [{ ...makeUtteranceDraft(paragraph, roles), audioStatus: `语句划分失败，请手动编辑：${data.error ?? "模型输出未通过校验"}` }];
        setSegmentationProgress(Math.round(((index + 1) / visibleParagraphs.length) * 100));
      }
      setUtterancesByParagraph(grouped);
      setApiStatus("已根据 Qwen/Qwen3-8B 生成可编辑语句草稿；子语句已嵌套在对应段落内");
    } catch (error) {
      setSegmentationProgress(100);
      setApiStatus(`语句划分失败：请检查远端模型配置、api_key 和网络连接。${String(error)}`);
    }
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
          if (role) {
            updated.speakerName = role.name;
            updated.voiceMode = role.voiceMode;
            updated.voiceResourceId = role.voiceResourceId;
            updated.otherControlText = updated.otherControlText || role.designPrompt || "";
          }
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
        ...makeUtteranceDraft({ ...paragraph, text: "" }, roles),
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
    updateUtterance(
      utterance.paragraphId,
      utterance.utteranceId,
      "audioStatus",
      "正在根据角色参考音频和其他控制文本生成音频",
    );
    setVoiceGenerationProgress(25);
    try {
      const result = await requestJson<{ audio_url: string; voice_job: { status: string }; warning?: string }>(
        `/api/utterances/${utterance.utteranceId}/speech`,
        {
          method: "POST",
          body: JSON.stringify({
            role_id: role.roleId,
            text: utterance.text,
            voice_mode: role.voiceMode,
            other_control_text: utterance.otherControlText,
            emotion: utterance.emotion,
            language: utterance.language,
            x_vector_only: utterance.xVectorOnly,
            speed: utterance.speed,
            volume: utterance.volume,
          }),
        },
      );
      const audioStatus =
        result.voice_job.status === "substitute"
          ? "本地 TTS 未启动，已生成可播放占位音频"
          : "音频生成完成";
      setUtterancesByParagraph((current) => ({
        ...current,
        [utterance.paragraphId]: (current[utterance.paragraphId] ?? []).map((item) =>
          item.utteranceId === utterance.utteranceId
            ? { ...item, audioStatus, audioUrl: result.audio_url }
            : item,
        ),
      }));
      setVoiceGenerationProgress(100);
    } catch (error) {
      updateUtterance(utterance.paragraphId, utterance.utteranceId, "audioStatus", `音频生成失败：${String(error)}`);
      setVoiceGenerationProgress(100);
    }
  }

  async function saveVoiceResource(payload: Partial<VoiceResource>): Promise<boolean> {
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
    setNewVoice((current) => ({ ...current, referenceAudioPath: data.reference_audio_path }));
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

  async function startLocalTtsService() {
    try {
      const data = await requestJson<{ message: string }>("/api/model-config/tts/start", {
        method: "POST",
        body: JSON.stringify({ tts: modelConfig.tts }),
      });
      setApiStatus(data.message || "本地 TTS 服务启动成功");
    } catch (error) {
      setApiStatus(`启动服务失败：${String(error)}`);
    }
  }

  function renderMainPage() {
    return (
      <main className="workbench" aria-label="NovelVoice-Agent v0.141 主页面">
        <aside className="sidebar">
          <section className="panel">
            <div className="section-title">小说章节</div>
            <div className="toolbar-row">
              <button className="tool-button sky" type="button" onClick={() => fileInputRef.current?.click()}>
                上传小说
              </button>
              <button className="tool-button amber" type="button" onClick={splitChapters}>
                划分章节
              </button>
            </div>
            <input
              ref={fileInputRef}
              className="hidden-input"
              aria-label="上传小说"
              type="file"
              accept=".txt,text/plain"
              onChange={handleTxtFile}
            />
            <ProgressBar label="上传小说进度" value={uploadProgress} />
            <ProgressBar label="章节划分进度" value={chapterSplitProgress} />
            <ProgressBar label="语句划分进度" value={segmentationProgress} />
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
                    <p>
                      <strong>音色描述</strong>
                      {voice?.description ?? role.description}
                    </p>
                    <p>
                      <strong>语音具体内容</strong>
                      {voice?.referenceText ?? role.referenceText}
                    </p>
                    {voice && <audio controls src={voiceAudioSrc(voice)} />}
                  </article>
                );
              })}
            </div>
          </section>
        </aside>

        <section className="main-panel">
          {!hasSplitChapters ? (
            <div className="empty-state">
              <div className="section-title">当前章节</div>
              <h2>尚未划分章节</h2>
              <p>上传小说后点击左侧“划分章节”，右侧暂不渲染具体章节内容。</p>
            </div>
          ) : !activeChapter ? (
            <div className="empty-state">
              <div className="section-title">当前章节</div>
              <h2>请选择左侧章节</h2>
              <p>选择某个章节后，才会加载并拆分这一章的正文。</p>
            </div>
          ) : (
            <>
              <header className="chapter-header">
                <div>
                  <div className="section-title">当前章节</div>
                  <h2>{activeChapter.title}</h2>
                </div>
                <div className="gate">
                  <button className="tool-button teal" type="button" onClick={() => void confirmParagraphs()}>
                    确认无误
                  </button>
                  <button className="tool-button purple" type="button" onClick={() => void runSegmentation()} disabled={!confirmed}>
                    语句划分
                  </button>
                  <span>{confirmed ? "已确认，可以执行语句划分" : "确认前不能执行语句划分"}</span>
                </div>
              </header>

              <section className="paragraph-stack">
                {visibleParagraphs.map((paragraph) => (
                  <article className="paragraph-card" key={paragraph.paragraphId}>
                    <div className="paragraph-toolbar">
                      <strong>{paragraph.paragraphId}</strong>
                      <button type="button" onClick={() => updateParagraph(paragraph.paragraphId, { collapsed: !paragraph.collapsed })}>
                        {paragraph.collapsed ? "展开" : "折叠"}
                      </button>
                      <button type="button" onClick={() => updateParagraph(paragraph.paragraphId, { deleted: true })}>
                        删除
                      </button>
                    </div>
                    {paragraph.collapsed ? null : (
                      <>
                        <textarea
                          value={paragraph.text}
                          onChange={(event) => updateParagraph(paragraph.paragraphId, { text: event.target.value })}
                        />
                        <div className="paragraph-utterances" aria-label={`${paragraph.paragraphId} 子语句`}>
                          {(utterancesByParagraph[paragraph.paragraphId] ?? []).map((utterance) => (
                            <article className="utterance-card" key={utterance.utteranceId}>
                              <div className="utterance-toolbar">
                                <strong>{utterance.utteranceId}</strong>
                                <button type="button" onClick={() => addUtteranceAfter(paragraph.paragraphId, utterance.utteranceId)}>
                                  添加音频生成
                                </button>
                                <button type="button" onClick={() => deleteUtterance(paragraph.paragraphId, utterance.utteranceId)}>
                                  删除音频生成
                                </button>
                              </div>
                              <label className="utterance-wide">
                                语句文本
                                <input
                                  value={utterance.text}
                                  onChange={(event) =>
                                    updateUtterance(paragraph.paragraphId, utterance.utteranceId, "text", event.target.value)
                                  }
                                  aria-label={`${utterance.utteranceId} 语句文本`}
                                />
                              </label>
                              <label>
                                选择角色
                                <select
                                  value={utterance.roleId}
                                  onChange={(event) =>
                                    updateUtterance(paragraph.paragraphId, utterance.utteranceId, "roleId", event.target.value)
                                  }
                                >
                                  {roleOptions.map((option) => (
                                    <option key={option.value} value={option.value}>
                                      {option.label}
                                    </option>
                                  ))}
                                </select>
                              </label>
                              <label>
                                情绪
                                <select
                                  value={utterance.emotion}
                                  onChange={(event) =>
                                    updateUtterance(paragraph.paragraphId, utterance.utteranceId, "emotion", event.target.value)
                                  }
                                  aria-label="情绪"
                                >
                                  <option value="">空</option>
                                  {EMOTION_OPTIONS.slice(1).map((emotion) => (
                                    <option key={emotion} value={emotion}>
                                      {emotion}
                                    </option>
                                  ))}
                                </select>
                              </label>
                              <label>
                                语言
                                <select
                                  value={utterance.language}
                                  onChange={(event) =>
                                    updateUtterance(paragraph.paragraphId, utterance.utteranceId, "language", event.target.value)
                                  }
                                >
                                  {LANGUAGE_OPTIONS.map((option) => (
                                    <option key={option.value} value={option.value}>
                                      {option.label}
                                    </option>
                                  ))}
                                </select>
                              </label>
                              <label className="checkline utterance-check">
                                <input
                                  type="checkbox"
                                  checked={utterance.xVectorOnly}
                                  onChange={(event) =>
                                    updateUtterance(paragraph.paragraphId, utterance.utteranceId, "xVectorOnly", event.target.checked)
                                  }
                                />
                                仅使用声纹
                                <small>只使用从参考音频提取的说话人声纹 embedding，尽量忽略参考音频里的情绪和语调。</small>
                              </label>
                              <label>
                                语速
                                <small>取值 0.5-2.0：1.0 为原速，越大越快。</small>
                                <input
                                  type="number"
                                  step="0.1"
                                  min="0.5"
                                  max="2"
                                  value={utterance.speed}
                                  onChange={(event) =>
                                    updateUtterance(paragraph.paragraphId, utterance.utteranceId, "speed", Number(event.target.value))
                                  }
                                  aria-label="语速"
                                />
                              </label>
                              <label>
                                音量
                                <small>取值 0.0-2.0：1.0 为原音量，0 为静音，2 为约两倍。</small>
                                <input
                                  type="number"
                                  step="0.1"
                                  min="0"
                                  max="2"
                                  value={utterance.volume}
                                  onChange={(event) =>
                                    updateUtterance(paragraph.paragraphId, utterance.utteranceId, "volume", Number(event.target.value))
                                  }
                                  aria-label="音量"
                                />
                              </label>
                              <label className="utterance-wide">
                                其他控制文本
                                <textarea
                                  value={utterance.otherControlText}
                                  onChange={(event) =>
                                    updateUtterance(paragraph.paragraphId, utterance.utteranceId, "otherControlText", event.target.value)
                                  }
                                  aria-label="其他控制文本"
                                  placeholder="例如：压低声音、急促、带害怕情绪"
                                />
                              </label>
                              <button className="tool-button sky" type="button" onClick={() => void generateAudio(utterance)}>
                                音频生成
                              </button>
                              <output>{utterance.audioStatus}</output>
                              {utterance.audioUrl && <audio controls src={utterance.audioUrl} />}
                            </article>
                          ))}
                          {confirmed && (
                            <button className="tool-button amber" type="button" onClick={() => addUtteranceAfter(paragraph.paragraphId)}>
                              添加音频生成
                            </button>
                          )}
                        </div>
                      </>
                    )}
              </article>
            ))}
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
            <textarea
              placeholder="音色描述"
              value={newVoice.description}
              onChange={(event) => setNewVoice((current) => ({ ...current, description: event.target.value }))}
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
            <textarea
              placeholder="音色描述"
              value={generatedVoice.description}
              onChange={(event) => setGeneratedVoice((current) => ({ ...current, description: event.target.value }))}
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
            模型权重路径
            <input
              value={modelConfig.tts.model_path}
              onChange={(event) =>
                setModelConfig((current) => ({ ...current, tts: { ...current.tts, model_path: event.target.value } }))
              }
            />
          </label>
          <div className="toolbar-row">
            <button className="tool-button teal" type="button" onClick={() => void saveLocalModelConfig()}>
              保存模型配置
            </button>
            <button className="tool-button purple" type="button" onClick={() => void startLocalTtsService()}>
              启动服务
            </button>
          </div>
        </section>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <h1>NovelVoice-Agent v0.141</h1>
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
