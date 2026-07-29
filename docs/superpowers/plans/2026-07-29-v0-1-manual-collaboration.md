# v0.1 Manual Collaboration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the v0.1 human-led novel dubbing workbench described in `spec/v0.1-manual-collaboration.md`, with executable checks mapped to `docs/development/acceptance-standard.md`.

**Architecture:** Keep parsing, role cards, LLM segmentation validation, provider registry, TTS request validation, API boundaries, and UI state separate. Model and TTS outputs remain editable drafts; provider details stay outside the UI. The frontend is a React + Vite + TypeScript workbench; the backend is Python/FastAPI-oriented domain and API code.

**Tech Stack:** Python 3.11+, FastAPI, uv, pytest, React, Vite, TypeScript.

---

## File Structure

- Create `tests/test_domain_workflow.py`: pytest coverage for chapter parsing, paragraph workflow gates, default roles, role sync, LLM schema/text conservation, provider registry, TTS request validation, and VoiceJob traceability.
- Create `tests/test_repository_acceptance.py`: repository-level acceptance checks for docs index, frontend structure, default sample labeling, and required source files.
- Create `backend/app/domain/novel.py`: chapter and paragraph parsing plus editable paragraph workflow state.
- Create `backend/app/domain/roles.py`: default role cards, editable role collection, and utterance role option projection.
- Create `backend/app/domain/providers.py`: OpenAI-compatible provider registry defaults for SiliconFlow and DeepSeek.
- Create `backend/app/domain/segmentation.py`: segmentation schema validation, one-time JSON repair, unknown-role handling, and text conservation.
- Create `backend/app/domain/audio.py`: TTS request validation and VoiceJob trace model.
- Create `backend/app/api/app.py`: FastAPI app factory and v0.1 resource routes matching the architecture contract.
- Create `backend/app/__init__.py`, `backend/app/api/__init__.py`, and `backend/app/domain/__init__.py`.
- Create `frontend/package.json`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/styles.css`, and `frontend/src/vite-env.d.ts`.
- Modify `pyproject.toml`: include local package/test path configuration if needed.
- Modify `docs/index.md`: link this plan and any new test/verification docs.
- Do not modify `docs/development/acceptance-standard.md`.

---

### Task 1: Acceptance Tests And Coverage Mapping

**Files:**
- Create: `tests/test_domain_workflow.py`
- Create: `tests/test_repository_acceptance.py`
- Modify: `docs/index.md`
- Do not modify: `backend/app/**`, `frontend/**`, `docs/development/acceptance-standard.md`

- [ ] **Step 1: Write failing tests for domain workflow**

Create pytest tests that import planned interfaces and fail because implementation modules do not exist yet:

```python
from backend.app.domain.novel import parse_novel_text, ChapterWorkbench
from backend.app.domain.roles import RoleCollection, default_role_cards
from backend.app.domain.segmentation import validate_segmentation_result
from backend.app.domain.providers import default_provider_registry
from backend.app.domain.audio import VoiceJob, build_tts_request
```

Required behaviors:

- AC-FLOW-02/03: sample txt splits into chapter objects with stable `chapter_id`, title, and body.
- AC-FLOW-04/05/06: chapter body becomes editable/deletable/collapsible paragraph modules; segmentation is blocked before confirmation and allowed after confirmation.
- AC-FLOW-07/08: segmentation utterances are editable drafts and role selector options track role card changes.
- AC-ROLE-01/02/03/04/05: default roles include `旁白`, `男主`, `女主`, include required voice fields, and default sample notes include “功能烟测占位，不代表最终音色质量”.
- AC-LLM-01/02/03/04/05/06/07: provider defaults, strict JSON, required utterance fields, one repair attempt, unknown role review flag, and text conservation.
- AC-AUDIO-07: VoiceJob traces utterance, role, provider, reference audio/text, and output path.

- [ ] **Step 2: Write repository acceptance tests**

Create tests that inspect files and fail until structure exists:

- AC-DOC-04: `docs/index.md` links new plan and existing docs.
- AC-FLOW-01/02/04/05/06/07/08: frontend source contains import, chapter list, editable/collapsible/deletable paragraph controls, confirm gate, segmentation button, utterance editor controls, and audio preview surface.
- AC-REAL-03: repository includes a reproducible UI evidence path or command note, even if real screenshot generation is environment-dependent.

- [ ] **Step 3: Run tests and verify RED**

Run:

```bash
uv run --group dev pytest tests/test_domain_workflow.py tests/test_repository_acceptance.py -q
```

Expected: fail because `backend.app.domain` and `frontend/` implementation files are missing.

- [ ] **Step 4: Report coverage map**

Return a concise AC coverage map:

- Covered by automated tests.
- Covered by structural checks.
- Requires real provider/TTS/UI evidence after implementation.

---

### Task 2: Backend Domain Implementation

**Files:**
- Create: `backend/app/domain/novel.py`
- Create: `backend/app/domain/roles.py`
- Create: `backend/app/domain/providers.py`
- Create: `backend/app/domain/segmentation.py`
- Create: `backend/app/domain/audio.py`
- Create: `backend/app/__init__.py`
- Create: `backend/app/domain/__init__.py`
- Modify only tests if an interface typo prevents a valid test from running.
- Do not modify: `docs/development/acceptance-standard.md`

- [ ] **Step 1: Run Task 1 tests to confirm RED**

Run:

```bash
uv run --group dev pytest tests/test_domain_workflow.py -q
```

Expected: import failures or assertion failures for missing implementation.

- [ ] **Step 2: Implement novel parsing and paragraph workflow**

Implement:

- `parse_novel_text(text: str) -> list[Chapter]` using fixed Chinese chapter heading regex such as `第[一二三四五六七八九十百千万零〇两\d]+[章节回].*`.
- Stable IDs: `chapter-0001`, `p-0001`, etc.
- Paragraph splitting by blank lines while preserving text order.
- `ChapterWorkbench` with paragraph modules containing `paragraph_id`, `text`, `collapsed`, `deleted`, `confirmed`, and methods `edit_paragraph`, `delete_paragraph`, `toggle_paragraph`, `confirm_paragraphs`, `can_segment`.

- [ ] **Step 3: Implement roles**

Implement:

- `default_role_cards()` returning narrator, male lead, and female lead cards.
- Each role has `role_id`, `name`, `description`, `voice_mode`, `reference_audio_path`, `reference_text`, `design_prompt`, and `sample_note`.
- `RoleCollection` supports add/update/remove/list and `utterance_role_options()`.

- [ ] **Step 4: Implement provider registry**

Implement `default_provider_registry()` returning:

- `siliconflow-qwen3-8b`: `base_url=https://api.siliconflow.cn/v1`, `model=Qwen/Qwen3-8B`, `api_key_env=SILICONFLOW_API_KEY`, `extra_body={"enable_thinking": False}`.
- `deepseek-harness`: `base_url=https://api.deepseek.com`, `model=deepseek-v4-flash`, `api_key_env=DEEPSEEK_API_KEY`.

- [ ] **Step 5: Implement segmentation validation**

Implement:

- Required utterance fields from `spec/llm-segmentation-contract.md`.
- Strict JSON parsing with at most one repair function attempt.
- Text conservation by normalized original paragraph text vs concatenated utterance text.
- Unknown role normalization: if speaker role is not known, `speaker_role_id=None` and `needs_human_review=True`.
- Failure result that preserves raw output and does not guess missing text.

- [ ] **Step 6: Implement audio request validation**

Implement:

- `build_tts_request(utterance, role)` that blocks voice cloning when reference audio/text is missing.
- Blocks voice design when design prompt is missing.
- `VoiceJob` dataclass/dict with trace fields from `spec/audio-synthesis-contract.md`.

- [ ] **Step 7: Run tests and verify GREEN**

Run:

```bash
uv run --group dev pytest tests/test_domain_workflow.py -q
```

Expected: pass.

---

### Task 3: FastAPI API Surface

**Files:**
- Create: `backend/app/api/app.py`
- Create: `backend/app/api/__init__.py`
- Modify: `tests/test_domain_workflow.py` only to add API tests if needed
- Do not modify: `backend/tts/qwen3_tts_server.py`, `docs/development/acceptance-standard.md`

- [ ] **Step 1: Write or confirm failing API tests**

Add tests that instantiate the FastAPI app when dependencies are available and verify route registration for:

- `POST /api/novels/parse`
- `GET /api/chapters`
- `GET /api/chapters/{chapter_id}`
- `PATCH /api/paragraphs/{paragraph_id}`
- `POST /api/paragraphs/{paragraph_id}/segment`
- `GET /api/roles`
- `POST /api/roles`
- `PATCH /api/roles/{role_id}`
- `POST /api/utterances/{utterance_id}/speech`

- [ ] **Step 2: Implement app factory**

Implement `create_app()` with in-memory v0.1 state suitable for the manual workbench. Keep provider API keys out of route handlers and UI payloads.

- [ ] **Step 3: Run API-related tests**

Run:

```bash
uv run --group dev pytest tests/test_domain_workflow.py -q
```

Expected: pass or skip only when FastAPI is not installed in the current environment.

---

### Task 4: React Manual Collaboration Workbench

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/styles.css`
- Create: `frontend/src/vite-env.d.ts`
- Modify: `tests/test_repository_acceptance.py`
- Do not modify: backend provider defaults, TTS service script, or acceptance standard

- [ ] **Step 1: Run repository acceptance tests to confirm RED**

Run:

```bash
uv run --group dev pytest tests/test_repository_acceptance.py -q
```

Expected: fail until frontend files exist and required UI terms are present.

- [ ] **Step 2: Implement React stateful workbench**

Implement a first-screen workbench with:

- Left side about 25% width: txt import, chapter list, role cards.
- Right side about 75% width: current chapter body, paragraph modules, confirm gate, segmentation action, utterance editor, and audio preview.
- Default roles: `旁白`, `男主`, `女主`.
- Paragraph modules: collapse, edit textarea, delete.
- Confirm gate: segmentation button hidden/disabled until confirmed.
- Segmentation draft: mock local draft generation only after confirmation; every utterance editable for text, role, voice mode, emotion, speed, volume, design prompt.
- Role selector options derived from role state so role card changes update utterance selectors.
- TTS preview button validates voice mode requirements and shows a generated-audio placeholder/error message without silently swallowing failures.

- [ ] **Step 3: Style for acceptance**

Implement clear two-column layout with stable controls and no overlapping text. Do not use provider API key/model details in UI.

- [ ] **Step 4: Run structural tests and optional frontend build**

Run:

```bash
uv run --group dev pytest tests/test_repository_acceptance.py -q
```

If dependencies are installed, also run:

```bash
cd frontend && npm install && npm run build
```

Expected: tests pass; frontend build passes when dependencies are available.

---

### Task 5: Final Verification And Review Evidence

**Files:**
- Modify: `docs/index.md`
- Create if useful: `docs/development/v0.1-verification.md`
- Do not modify: `docs/development/acceptance-standard.md`

- [ ] **Step 1: Run harness validation**

Run:

```bash
python3 scripts/validate_harness.py
```

Expected: pass.

- [ ] **Step 2: Run automated tests**

Run:

```bash
uv run --group dev pytest -q
```

Expected: pass.

- [ ] **Step 3: Run frontend build when dependencies are available**

Run:

```bash
cd frontend && npm install && npm run build
```

Expected: pass, or document dependency/network blocker if the environment cannot install packages.

- [ ] **Step 4: Record evidence gaps honestly**

Document:

- Real SiliconFlow segmentation was not run unless `SILICONFLOW_API_KEY` and network are available.
- Real Qwen3-TTS synthesis was not run unless local model path and runtime are available.
- Real UI screenshot evidence requires a local dev server/browser run.

- [ ] **Step 5: Independent reviews**

Dispatch:

- `acceptance-checker`: read-only AC coverage review.
- `visual-reviewer`: read-only review with screenshot/evidence if available, otherwise evidence insufficiency callout.
- `audio-reviewer`: read-only sample/TTS evidence review.
- `reviewer`: final spec and code quality review.

Resolve blocking findings before claiming v0.1 implementation is complete.
