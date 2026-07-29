import { ChangeEvent, useMemo, useState } from "react";

type VoiceMode = "voice_cloning" | "voice_design";

type Chapter = {
  chapterId: string;
  title: string;
  body: string;
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

type RoleCard = {
  roleId: string;
  name: string;
  description: string;
  voiceMode: VoiceMode;
  referenceAudioPath?: string;
  referenceText?: string;
  designPrompt?: string;
  sampleNote: string;
};

type UtteranceDraft = {
  utteranceId: string;
  text: string;
  roleId: string;
  speakerName: string;
  voiceMode: VoiceMode;
  emotion: string;
  speed: number;
  volume: number;
  designPrompt: string;
  audioStatus: string;
  audioUrl?: string;
};

const smokeNote = "功能烟测占位，不代表最终音色质量";

const sampleNovel = `第一章 初遇
夜色落在旧城墙上，风从窄巷里穿过。

男主说：“今晚的钟声好像比往常慢。”

女主回答：“也许是有人在等一个迟到的故事。”`;

const defaultRoles: RoleCard[] = [
  {
    roleId: "narrator",
    name: "旁白",
    description: "用于叙述性文本。",
    voiceMode: "voice_cloning",
    referenceAudioPath: "assets/samples/voices/cmn_qixinxieli_canonni_cc0.wav",
    referenceText: "齐心协力",
    sampleNote: smokeNote,
  },
  {
    roleId: "male_lead",
    name: "男主",
    description: "功能烟测默认角色，不代表最终项目必须只有一个男主。",
    voiceMode: "voice_cloning",
    referenceAudioPath: "assets/samples/voices/cmn_qixinxieli_canonni_cc0.wav",
    referenceText: "齐心协力",
    sampleNote: smokeNote,
  },
  {
    roleId: "female_lead",
    name: "女主",
    description: "功能烟测默认角色，不代表最终项目必须只有一个女主。",
    voiceMode: "voice_design",
    designPrompt: "清亮、温柔、自然的年轻女性声音",
    sampleNote: smokeNote,
  },
];

function parseChapters(text: string): Chapter[] {
  const headingPattern = /^(第[一二三四五六七八九十百千万零〇两\d]+[章节回].*)$/gm;
  const matches = Array.from(text.matchAll(headingPattern));
  if (matches.length === 0) {
    return [{ chapterId: "chapter-0001", title: "未分章正文", body: text.trim() }];
  }
  return matches.map((match, index) => {
    const next = matches[index + 1];
    const bodyStart = (match.index ?? 0) + match[0].length;
    const bodyEnd = next?.index ?? text.length;
    return {
      chapterId: `chapter-${String(index + 1).padStart(4, "0")}`,
      title: match[1].trim(),
      body: text.slice(bodyStart, bodyEnd).trim(),
    };
  });
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

function makeUtteranceDraft(paragraph: ParagraphModule, roles: RoleCard[]): UtteranceDraft {
  const narrator = roles[0];
  return {
    utteranceId: `${paragraph.paragraphId}-u-001`,
    text: paragraph.text,
    roleId: narrator.roleId,
    speakerName: narrator.name,
    voiceMode: narrator.voiceMode,
    emotion: "neutral",
    speed: 1,
    volume: 1,
    designPrompt: narrator.designPrompt ?? "",
    audioStatus: "尚未试听",
  };
}

function rolePatchField(field: keyof RoleCard): string {
  const fieldMap: Record<keyof RoleCard, string> = {
    roleId: "role_id",
    name: "name",
    description: "description",
    voiceMode: "voice_mode",
    referenceAudioPath: "reference_audio_path",
    referenceText: "reference_text",
    designPrompt: "design_prompt",
    sampleNote: "sample_note",
  };
  return fieldMap[field];
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

export default function App() {
  const [novelText, setNovelText] = useState(sampleNovel);
  const [chapters, setChapters] = useState<Chapter[]>(() => parseChapters(sampleNovel));
  const [activeChapterId, setActiveChapterId] = useState("chapter-0001");
  const [paragraphs, setParagraphs] = useState<ParagraphModule[]>(() =>
    paragraphsFromChapter(parseChapters(sampleNovel)[0]),
  );
  const [confirmed, setConfirmed] = useState(false);
  const [roles, setRoles] = useState<RoleCard[]>(defaultRoles);
  const [utterances, setUtterances] = useState<UtteranceDraft[]>([]);
  const [apiStatus, setApiStatus] = useState("等待导入小说");

  const activeChapter = chapters.find((chapter) => chapter.chapterId === activeChapterId) ?? chapters[0];
  const visibleParagraphs = paragraphs.filter((paragraph) => !paragraph.deleted);
  const roleOptions = useMemo(
    () => roles.map((role) => ({ value: role.roleId, label: role.name })),
    [roles],
  );

  async function importNovelText(text: string) {
    try {
      const data = await requestJson<{ chapters: ApiChapter[] }>("/api/novels/parse", {
        method: "POST",
        body: JSON.stringify({ text }),
      });
      const parsed = data.chapters.map(fromApiChapter);
      setChapters(parsed);
      setActiveChapterId(parsed[0]?.chapterId ?? "");
      setParagraphs(parsed[0] ? paragraphsFromChapter(parsed[0]) : []);
      setApiStatus("小说已导入后端工作流");
    } catch (error) {
      const parsed = parseChapters(text);
      setChapters(parsed);
      setActiveChapterId(parsed[0]?.chapterId ?? "");
      setParagraphs(parsed[0] ? paragraphsFromChapter(parsed[0]) : []);
      setApiStatus(`后端导入失败，已保留本地预览：${error instanceof Error ? error.message : String(error)}`);
    }
    setConfirmed(false);
    setUtterances([]);
  }

  function handleImport() {
    void importNovelText(novelText);
  }

  async function handleTxtFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    setNovelText(text);
    await importNovelText(text);
  }

  async function selectChapter(chapterId: string) {
    const chapter = chapters.find((item) => item.chapterId === chapterId);
    if (!chapter) return;
    setActiveChapterId(chapterId);
    try {
      const data = await requestJson<{
        chapter: ApiChapter;
        paragraphs: ApiParagraph[];
        can_segment: boolean;
      }>(`/api/chapters/${chapterId}`);
      setParagraphs(data.paragraphs.map(fromApiParagraph));
      setConfirmed(data.can_segment);
      setApiStatus("章节已从后端载入");
    } catch (error) {
      setParagraphs(paragraphsFromChapter(chapter));
      setConfirmed(false);
      setApiStatus(`后端章节载入失败，已保留本地预览：${error instanceof Error ? error.message : String(error)}`);
    }
    setUtterances([]);
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

  async function confirmParagraphs() {
    const first = visibleParagraphs[0];
    if (!first) return;
    try {
      await syncParagraph(first.paragraphId, { confirm_all: true });
      setApiStatus("段落已确认，可以执行语句划分");
    } catch (error) {
      setApiStatus(`确认失败：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  function fallbackImportCurrentText() {
    const parsed = parseChapters(novelText);
    setChapters(parsed);
    setActiveChapterId(parsed[0]?.chapterId ?? "");
    setParagraphs(parsed[0] ? paragraphsFromChapter(parsed[0]) : []);
    setConfirmed(false);
    setUtterances([]);
  }

  function updateParagraph(paragraphId: string, updates: Partial<ParagraphModule>) {
    setParagraphs((current) =>
      current.map((paragraph) =>
        paragraph.paragraphId === paragraphId ? { ...paragraph, ...updates } : paragraph,
      ),
    );
    if ("text" in updates || updates.deleted) {
      setConfirmed(false);
      setUtterances([]);
    }
    const payload: Record<string, unknown> = {};
    if ("text" in updates) payload.text = updates.text;
    if (updates.deleted) payload.deleted = true;
    if ("collapsed" in updates) payload.toggle = true;
    if (Object.keys(payload).length > 0) {
      syncParagraph(paragraphId, payload).catch((error) => {
        setApiStatus(`段落同步失败：${error instanceof Error ? error.message : String(error)}`);
      });
    }
  }

  function updateRole(roleId: string, field: keyof RoleCard, value: string) {
    setRoles((current) =>
      current.map((role) =>
        role.roleId === roleId
          ? {
              ...role,
              [field]: field === "voiceMode" ? (value as VoiceMode) : value,
            }
          : role,
      ),
    );
    requestJson<{ role: RoleCard; role_options: Array<{ value: string; label: string }> }>(
      `/api/roles/${roleId}`,
      {
        method: "PATCH",
        body: JSON.stringify({
          [rolePatchField(field)]: field === "voiceMode" ? (value as VoiceMode) : value,
        }),
      },
    ).catch((error) => {
      setApiStatus(`角色同步失败：${error instanceof Error ? error.message : String(error)}`);
    });
  }

  async function runSegmentation() {
    if (!confirmed) return;
    setApiStatus("正在调用 LLM 语句划分");
    const drafts: UtteranceDraft[] = [];
    for (const paragraph of visibleParagraphs) {
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
        drafts.push(
          ...result.utterances.map((utterance) => ({
            utteranceId: utterance.utterance_id,
            text: utterance.text,
            roleId: utterance.speaker_role_id ?? roles[0].roleId,
            speakerName: utterance.speaker_name,
            voiceMode: utterance.voice_mode,
            emotion: utterance.emotion,
            speed: utterance.speed,
            volume: utterance.volume,
            designPrompt: utterance.design_prompt ?? "",
            audioStatus: "尚未试听",
          })),
        );
      } catch (error) {
        drafts.push({
          ...makeUtteranceDraft(paragraph, roles),
          audioStatus: `语句划分失败：${error instanceof Error ? error.message : String(error)}`,
        });
      }
    }
    setUtterances(drafts);
    setApiStatus("语句划分完成；失败项保留为人工可编辑草稿");
  }

  function updateUtterance(
    utteranceId: string,
    field: keyof UtteranceDraft,
    value: string | number,
  ) {
    setUtterances((current) =>
      current.map((utterance) => {
        if (utterance.utteranceId !== utteranceId) return utterance;
        const updated = { ...utterance, [field]: value };
        if (field === "roleId") {
          const role = roles.find((item) => item.roleId === value);
          if (role) {
            updated.speakerName = role.name;
            updated.voiceMode = role.voiceMode;
            updated.designPrompt = role.designPrompt ?? "";
          }
        }
        return updated;
      }),
    );
  }

  async function previewTts(utterance: UtteranceDraft) {
    const role = roles.find((item) => item.roleId === utterance.roleId);
    if (!role) {
      updateUtterance(utterance.utteranceId, "audioStatus", "试听失败：角色不存在");
      return;
    } else if (utterance.voiceMode === "voice_cloning" && (!role.referenceAudioPath || !role.referenceText)) {
      updateUtterance(utterance.utteranceId, "audioStatus", "试听失败：voice cloning 缺少参考音频或参考文本");
      return;
    } else if (utterance.voiceMode === "voice_design" && !utterance.designPrompt.trim()) {
      updateUtterance(utterance.utteranceId, "audioStatus", "试听失败：voice design 缺少声音设计 prompt");
      return;
    }
    updateUtterance(utterance.utteranceId, "audioStatus", "正在调用本地 TTS");
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
      setUtterances((current) =>
        current.map((item) =>
          item.utteranceId === utterance.utteranceId
            ? {
                ...item,
                audioStatus: `生成音频：${result.voice_job.status}`,
                audioUrl: result.audio_url,
              }
            : item,
        ),
      );
    } catch (error) {
      updateUtterance(
        utterance.utteranceId,
        "audioStatus",
        `试听失败：${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  return (
    <main className="workbench" aria-label="人工主导小说配音辅助工作台">
      <aside className="sidebar">
        <section className="panel">
          <h1>NovelVoice-Agent v0.1</h1>
          <p>人工主导的人机协作版小说配音辅助工作台。</p>
        </section>

        <section className="panel">
          <div className="section-title">小说导入</div>
          <input
            aria-label="选择固定格式 txt 小说文件"
            type="file"
            accept=".txt,text/plain"
            onChange={handleTxtFile}
          />
          <textarea
            aria-label="固定格式 txt 小说导入"
            value={novelText}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setNovelText(event.target.value)}
          />
          <button type="button" onClick={handleImport}>导入 txt</button>
          <button type="button" onClick={fallbackImportCurrentText}>仅本地预览</button>
          <small>{apiStatus}</small>
        </section>

        <section className="panel">
          <div className="section-title">章节列表</div>
          <div className="chapter-list">
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
          <div className="section-title">角色卡</div>
          {roles.map((role) => (
            <article className="role-card" key={role.roleId}>
              <input
                aria-label={`${role.name} 角色姓名`}
                value={role.name}
                onChange={(event) => updateRole(role.roleId, "name", event.target.value)}
              />
              <textarea
                aria-label={`${role.name} 简介`}
                value={role.description}
                onChange={(event) => updateRole(role.roleId, "description", event.target.value)}
              />
              <select
                aria-label={`${role.name} 声音模式`}
                value={role.voiceMode}
                onChange={(event) => updateRole(role.roleId, "voiceMode", event.target.value)}
              >
                <option value="voice_cloning">voice_cloning</option>
                <option value="voice_design">voice_design</option>
              </select>
              <input
                aria-label={`${role.name} 参考音频`}
                value={role.referenceAudioPath ?? ""}
                onChange={(event) => updateRole(role.roleId, "referenceAudioPath", event.target.value)}
              />
              <input
                aria-label={`${role.name} 参考文本`}
                value={role.referenceText ?? ""}
                onChange={(event) => updateRole(role.roleId, "referenceText", event.target.value)}
              />
              <textarea
                aria-label={`${role.name} 声音设计 prompt`}
                value={role.designPrompt ?? ""}
                onChange={(event) => updateRole(role.roleId, "designPrompt", event.target.value)}
              />
              <small>{role.sampleNote}</small>
            </article>
          ))}
        </section>
      </aside>

      <section className="main-panel">
        <header className="chapter-header">
          <div>
            <div className="section-title">当前章节正文</div>
            <h2>{activeChapter?.title ?? "未选择章节"}</h2>
          </div>
          <div className="gate">
            <button type="button" onClick={() => void confirmParagraphs()} disabled={visibleParagraphs.length === 0}>
              确认无误
            </button>
            <button type="button" onClick={() => void runSegmentation()} disabled={!confirmed}>
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
                <button
                  type="button"
                  onClick={() => updateParagraph(paragraph.paragraphId, { collapsed: !paragraph.collapsed })}
                >
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
            </article>
          ))}
        </section>

        <section className="utterance-editor">
          <div className="section-title">子语句编辑和音频试听</div>
          {utterances.length === 0 ? (
            <p>确认段落后点击语句划分，每个模型子语句都可人工修改。</p>
          ) : (
            utterances.map((utterance) => (
              <article className="utterance-card" key={utterance.utteranceId}>
                <input
                  value={utterance.text}
                  onChange={(event) => updateUtterance(utterance.utteranceId, "text", event.target.value)}
                  aria-label={`${utterance.utteranceId} 文本`}
                />
                <select
                  value={utterance.roleId}
                  onChange={(event) => updateUtterance(utterance.utteranceId, "roleId", event.target.value)}
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
                    updateUtterance(utterance.utteranceId, "voiceMode", event.target.value as VoiceMode)
                  }
                >
                  <option value="voice_cloning">voice_cloning</option>
                  <option value="voice_design">voice_design</option>
                </select>
                <input
                  value={utterance.emotion}
                  onChange={(event) => updateUtterance(utterance.utteranceId, "emotion", event.target.value)}
                  aria-label="emotion"
                />
                <input
                  type="number"
                  step="0.1"
                  min="0.5"
                  max="2"
                  value={utterance.speed}
                  onChange={(event) => updateUtterance(utterance.utteranceId, "speed", Number(event.target.value))}
                  aria-label="speed"
                />
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  max="2"
                  value={utterance.volume}
                  onChange={(event) => updateUtterance(utterance.utteranceId, "volume", Number(event.target.value))}
                  aria-label="volume"
                />
                <textarea
                  value={utterance.designPrompt}
                  onChange={(event) =>
                    updateUtterance(utterance.utteranceId, "designPrompt", event.target.value)
                  }
                  aria-label="designPrompt"
                />
                <button type="button" onClick={() => void previewTts(utterance)}>TTS 试听</button>
                <output className="audio-preview">音频试听：{utterance.audioStatus}</output>
                {utterance.audioUrl && <audio controls src={utterance.audioUrl} />}
              </article>
            ))
          )}
        </section>
      </section>
    </main>
  );
}
