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

type UtteranceDraft = {
  utteranceId: string;
  paragraphId: string;
  text: string;
  roleId: string;
  speakerName: string;
  voiceMode: VoiceMode;
  voiceResourceId: string;
  emotion: string;
  speed: number;
  volume: number;
  designPrompt: string;
  audioStatus: string;
  audioUrl?: string;
};

type ModelConfig = {
  llm: {
    provider: string;
    base_url: string;
    model: string;
    api_key_env: string;
    timeout_seconds: number;
    max_retries: number;
  };
  tts: {
    provider: string;
    base_url: string;
    model_path_env: string;
    device_env: string;
    timeout_seconds: number;
  };
};

const sampleNovel = `1.变成蘑菇的公爵千金
“放开我！你们是谁？快放开我！”

一醒来就发现自己被装麻袋了的伊南娜竭力扭动身体。

“佩罗，你昏迷术掺水了？这就醒了。”`;

const MAX_NOVEL_PREVIEW_CHARS = 700;

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
    provider: "siliconflow-qwen3-8b",
    base_url: "https://api.siliconflow.cn/v1",
    model: "Qwen/Qwen3-8B",
    api_key_env: "SILICONFLOW_API_KEY",
    timeout_seconds: 60,
    max_retries: 2,
  },
  tts: {
    provider: "local-qwen3-tts",
    base_url: "http://127.0.0.1:7811",
    model_path_env: "QWEN3_TTS_MODEL_PATH",
    device_env: "QWEN3_TTS_DEVICE",
    timeout_seconds: 120,
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
    emotion: "neutral",
    speed: 1,
    volume: 1,
    designPrompt: role.designPrompt,
    audioStatus: "尚未试听",
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
  });
  const [modelConfig, setModelConfig] = useState<ModelConfig>(defaultModelConfig);
  const [apiStatus, setApiStatus] = useState("等待上传小说");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [chapterSplitProgress, setChapterSplitProgress] = useState(0);
  const [segmentationProgress, setSegmentationProgress] = useState(0);
  const [voiceGenerationProgress, setVoiceGenerationProgress] = useState(0);

  const activeChapter = chapters.find((chapter) => chapter.chapterId === activeChapterId) ?? chapters[0];
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
      .then((data) => setModelConfig(data.config))
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
    setUtterancesByParagraph({});
    setSegmentationProgress(0);
    setVoiceGenerationProgress(0);
    setApiStatus(`已加载章节：${chapter.title}`);
  }

  async function syncParagraph(paragraphId: string, payload: Record<string, unknown>) {
    const data = await requestJson<{ paragraphs: ApiParagraph[]; can_segment: boolean }>(
      `/api/paragraphs/${paragraphId}`,
      {
        method: "PATCH",
        body: JSON.stringify(payload),
      },
    );
    setParagraphs(data.paragraphs.map(fromApiParagraph));
    setConfirmed(data.can_segment);
  }

  function updateParagraph(paragraphId: string, updates: Partial<ParagraphModule>) {
    setParagraphs((current) =>
      current.map((paragraph) =>
        paragraph.paragraphId === paragraphId ? { ...paragraph, ...updates } : paragraph,
      ),
    );
    if ("text" in updates || updates.deleted) {
      setConfirmed(false);
      setUtterancesByParagraph({});
    }
    const payload: Record<string, unknown> = {};
    if ("text" in updates) payload.text = updates.text;
    if (updates.deleted) payload.deleted = true;
    if ("collapsed" in updates) payload.toggle = true;
    if (Object.keys(payload).length > 0) {
      syncParagraph(paragraphId, payload).catch((error) => {
        setApiStatus(`段落同步失败：${String(error)}`);
      });
    }
  }

  async function confirmParagraphs() {
    const first = visibleParagraphs[0];
    if (!first) return;
    try {
      await syncParagraph(first.paragraphId, { confirm_all: true });
      setApiStatus("段落已确认，可以执行语句划分");
    } catch (error) {
      setConfirmed(true);
      setApiStatus(`后端确认失败，已使用本地确认状态：${String(error)}`);
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

  async function runSegmentation() {
    if (!confirmed) return;
    setApiStatus("正在调用 LLM 语句划分");
    setSegmentationProgress(0);
    const grouped: Record<string, UtteranceDraft[]> = {};
    for (const [index, paragraph] of visibleParagraphs.entries()) {
      try {
        const result = await requestJson<{
          ok: boolean;
          utterances: Array<{
            utterance_id: string;
            text: string;
            speaker_role_id: string | null;
            speaker_name: string;
            voice_mode: VoiceMode;
            emotion: string;
            speed: number;
            volume: number;
            design_prompt: string | null;
          }>;
          error?: string;
          error_code?: string;
        }>(`/api/paragraphs/${paragraph.paragraphId}/segment`, {
          method: "POST",
          body: JSON.stringify({}),
        });
        if (!result.ok) {
          throw new Error(result.error ?? result.error_code ?? "语句划分失败");
        }
        grouped[paragraph.paragraphId] = result.utterances.map((utterance) => {
          const role = roles.find((item) => item.roleId === utterance.speaker_role_id) ?? roles[0];
          return {
            utteranceId: utterance.utterance_id,
            paragraphId: paragraph.paragraphId,
            text: utterance.text,
            roleId: role.roleId,
            speakerName: utterance.speaker_name,
            voiceMode: utterance.voice_mode,
            voiceResourceId: role.voiceResourceId,
            emotion: utterance.emotion,
            speed: utterance.speed,
            volume: utterance.volume,
            designPrompt: utterance.design_prompt ?? role.designPrompt,
            audioStatus: "尚未试听",
          };
        });
      } catch (error) {
        grouped[paragraph.paragraphId] = [
          {
            ...makeUtteranceDraft(paragraph, roles),
            audioStatus: `语句划分失败：${String(error)}`,
          },
        ];
      }
      setSegmentationProgress(Math.round(((index + 1) / visibleParagraphs.length) * 100));
    }
    setUtterancesByParagraph(grouped);
    setApiStatus("语句划分完成；子语句已嵌套在对应段落内");
  }

  function updateUtterance(
    paragraphId: string,
    utteranceId: string,
    field: keyof UtteranceDraft,
    value: string | number,
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
            updated.designPrompt = role.designPrompt;
          }
        }
        return updated;
      }),
    }));
  }

  async function previewTts(utterance: UtteranceDraft) {
    const role = roles.find((item) => item.roleId === utterance.roleId);
    if (!role) {
      updateUtterance(utterance.paragraphId, utterance.utteranceId, "audioStatus", "试听失败：角色不存在");
      return;
    }
    updateUtterance(utterance.paragraphId, utterance.utteranceId, "audioStatus", "正在调用本地 TTS");
    setVoiceGenerationProgress(25);
    try {
      const result = await requestJson<{ audio_url: string; voice_job: { status: string } }>(
        `/api/utterances/${utterance.utteranceId}/speech`,
        {
          method: "POST",
          body: JSON.stringify({
            role_id: role.roleId,
            text: utterance.text,
            voice_mode: utterance.voiceMode,
            design_prompt: utterance.designPrompt,
          }),
        },
      );
      setUtterancesByParagraph((current) => ({
        ...current,
        [utterance.paragraphId]: (current[utterance.paragraphId] ?? []).map((item) =>
          item.utteranceId === utterance.utteranceId
            ? { ...item, audioStatus: `生成音频：${result.voice_job.status}`, audioUrl: result.audio_url }
            : item,
        ),
      }));
      setVoiceGenerationProgress(100);
    } catch (error) {
      updateUtterance(utterance.paragraphId, utterance.utteranceId, "audioStatus", `试听失败：${String(error)}`);
      setVoiceGenerationProgress(100);
    }
  }

  async function saveVoiceResource(payload: Partial<VoiceResource>) {
    const data = await requestJson<{ voice: ApiVoiceResource; voices: ApiVoiceResource[] }>("/api/voice-resources", {
      method: "POST",
      body: JSON.stringify(toApiVoice(payload)),
    });
    setVoices(data.voices.map(fromApiVoice));
    setApiStatus(`音色已保存：${data.voice.name}`);
  }

  async function updateVoiceResource(voice: VoiceResource) {
    const data = await requestJson<{ voices: ApiVoiceResource[] }>(`/api/voice-resources/${voice.voiceId}`, {
      method: "PATCH",
      body: JSON.stringify(toApiVoice(voice)),
    });
    setVoices(data.voices.map(fromApiVoice));
  }

  async function generateVoiceResource() {
    const data = await requestJson<{ voice: ApiVoiceResource; voices: ApiVoiceResource[] }>(
      "/api/voice-resources/generate",
      {
        method: "POST",
        body: JSON.stringify({
          name: generatedVoice.name,
          description: generatedVoice.description,
        }),
      },
    );
    setVoices(data.voices.map(fromApiVoice));
    setApiStatus(`生成音色已保存为可编辑草稿：${data.voice.name}`);
  }

  async function deleteSelectedVoices() {
    let remaining = voices;
    for (const voice of voices.filter((item) => selectedVoiceIds[item.voiceId])) {
      const data = await requestJson<{ voices: ApiVoiceResource[] }>(`/api/voice-resources/${voice.voiceId}`, {
        method: "DELETE",
      });
      remaining = data.voices.map(fromApiVoice);
    }
    setVoices(remaining);
    setSelectedVoiceIds({});
  }

  async function saveModelConfig() {
    const data = await requestJson<{ config: ModelConfig }>("/api/model-config", {
      method: "PATCH",
      body: JSON.stringify(modelConfig),
    });
    setModelConfig(data.config);
    setApiStatus("模型配置已保存");
  }

  function renderMainPage() {
    return (
      <main className="workbench" aria-label="NovelVoice-Agent v0.12 主页面">
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
            <div className="section-title">角色列表</div>
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
                      <button className="icon-button" type="button" title="播放音色">
                        播放音色
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
                    {!paragraph.collapsed && (
                      <textarea
                        value={paragraph.text}
                        onChange={(event) => updateParagraph(paragraph.paragraphId, { text: event.target.value })}
                      />
                    )}
                    <div className="paragraph-utterances" aria-label={`${paragraph.paragraphId} 子语句`}>
                      {(utterancesByParagraph[paragraph.paragraphId] ?? []).map((utterance) => (
                        <article className="utterance-card" key={utterance.utteranceId}>
                      <input
                        value={utterance.text}
                        onChange={(event) =>
                          updateUtterance(paragraph.paragraphId, utterance.utteranceId, "text", event.target.value)
                        }
                        aria-label={`${utterance.utteranceId} 文本`}
                      />
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
                      <select
                        value={utterance.voiceMode}
                        onChange={(event) =>
                          updateUtterance(
                            paragraph.paragraphId,
                            utterance.utteranceId,
                            "voiceMode",
                            event.target.value as VoiceMode,
                          )
                        }
                      >
                        <option value="voice_cloning">voice_cloning</option>
                        <option value="voice_design">voice_design</option>
                      </select>
                      <input
                        value={utterance.emotion}
                        onChange={(event) =>
                          updateUtterance(paragraph.paragraphId, utterance.utteranceId, "emotion", event.target.value)
                        }
                        aria-label="emotion"
                      />
                      <input
                        type="number"
                        step="0.1"
                        min="0.5"
                        max="2"
                        value={utterance.speed}
                        onChange={(event) =>
                          updateUtterance(paragraph.paragraphId, utterance.utteranceId, "speed", Number(event.target.value))
                        }
                        aria-label="speed"
                      />
                      <input
                        type="number"
                        step="0.1"
                        min="0"
                        max="2"
                        value={utterance.volume}
                        onChange={(event) =>
                          updateUtterance(paragraph.paragraphId, utterance.utteranceId, "volume", Number(event.target.value))
                        }
                        aria-label="volume"
                      />
                      <textarea
                        value={utterance.designPrompt}
                        onChange={(event) =>
                          updateUtterance(paragraph.paragraphId, utterance.utteranceId, "designPrompt", event.target.value)
                        }
                        aria-label="designPrompt"
                      />
                      <button className="tool-button sky" type="button" onClick={() => void previewTts(utterance)}>
                        音频试听
                      </button>
                      <output>{utterance.audioStatus}</output>
                      {utterance.audioUrl && <audio controls src={utterance.audioUrl} />}
                    </article>
                  ))}
                </div>
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
              placeholder="参考音频文件"
              value={newVoice.referenceAudioPath}
              onChange={(event) => setNewVoice((current) => ({ ...current, referenceAudioPath: event.target.value }))}
            />
            {newVoice.referenceAudioPath && <audio controls src={newVoice.referenceAudioPath} />}
            <button className="tool-button teal" type="button" onClick={() => void saveVoiceResource(newVoice)}>
              保存音色
            </button>
          </div>

          <div className="panel">
            <div className="section-title">生成资源到资源库列表</div>
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
            <button className="tool-button purple" type="button" onClick={() => void generateVoiceResource()}>
              生成音色
            </button>
            <button className="tool-button teal" type="button" onClick={() => void generateVoiceResource()}>
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
          <div className="section-title">LLM Provider</div>
          <label>
            Provider
            <input
              value={modelConfig.llm.provider}
              onChange={(event) =>
                setModelConfig((current) => ({ ...current, llm: { ...current.llm, provider: event.target.value } }))
              }
            />
          </label>
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
            Model
            <input
              value={modelConfig.llm.model}
              onChange={(event) =>
                setModelConfig((current) => ({ ...current, llm: { ...current.llm, model: event.target.value } }))
              }
            />
          </label>
          <label>
            api_key_env
            <input
              value={modelConfig.llm.api_key_env}
              onChange={(event) =>
                setModelConfig((current) => ({
                  ...current,
                  llm: { ...current.llm, api_key_env: event.target.value },
                }))
              }
            />
          </label>
          <div className="compact-grid">
            <label>
              Timeout
              <input
                type="number"
                value={modelConfig.llm.timeout_seconds}
                onChange={(event) =>
                  setModelConfig((current) => ({
                    ...current,
                    llm: { ...current.llm, timeout_seconds: Number(event.target.value) },
                  }))
                }
              />
            </label>
            <label>
              Retries
              <input
                type="number"
                value={modelConfig.llm.max_retries}
                onChange={(event) =>
                  setModelConfig((current) => ({
                    ...current,
                    llm: { ...current.llm, max_retries: Number(event.target.value) },
                  }))
                }
              />
            </label>
          </div>
        </section>

        <section className="panel">
          <div className="section-title">TTS Provider</div>
          <label>
            Provider
            <input
              value={modelConfig.tts.provider}
              onChange={(event) =>
                setModelConfig((current) => ({ ...current, tts: { ...current.tts, provider: event.target.value } }))
              }
            />
          </label>
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
            Model Path Env
            <input value={modelConfig.tts.model_path_env} readOnly />
          </label>
          <label>
            Device Env
            <input value={modelConfig.tts.device_env} readOnly />
          </label>
          <label>
            Timeout
            <input
              type="number"
              value={modelConfig.tts.timeout_seconds}
              onChange={(event) =>
                setModelConfig((current) => ({
                  ...current,
                  tts: { ...current.tts, timeout_seconds: Number(event.target.value) },
                }))
              }
            />
          </label>
          <button className="tool-button sky" type="button" onClick={() => void saveModelConfig()}>
            保存模型配置
          </button>
        </section>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <h1>NovelVoice-Agent v0.12</h1>
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
