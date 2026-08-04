from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from backend.app.domain.dubbing_workflow import RoleAnalysisCandidate
from backend.app.domain.llm import MissingProviderCredential

HttpPost = Callable[[str, dict[str, str], dict[str, Any], int], dict[str, Any]]
QdrantRequest = Callable[[str, str, dict[str, Any] | None], dict[str, Any]]

DEFAULT_EMBEDDING_API_KEY_ENV = "SHUYI_EMBEDDING_API_KEY"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_QDRANT_COLLECTION = "shuyi_story_memory"


def build_story_memory_chunks(*, project_id: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    max_chars = int(payload.get("max_chunk_chars") or 800)
    overlap = int(payload.get("chunk_overlap_chars") or 80)

    for chapter in _list(payload.get("chapters")):
        chapter_id = _text(chapter.get("chapter_id") or chapter.get("chapterId"))
        title = _text(chapter.get("title") or chapter_id)
        for paragraph in _list(chapter.get("paragraphs")):
            paragraph_id = _text(paragraph.get("paragraph_id") or paragraph.get("paragraphId"))
            text = _text(paragraph.get("text"))
            if not text:
                continue
            source_id = f"{chapter_id}:{paragraph_id}" if paragraph_id else chapter_id
            chunks.extend(
                _split_text_chunk(
                    project_id=project_id,
                    source_id=source_id,
                    source_type="novel",
                    text=text,
                    max_chars=max_chars,
                    overlap=overlap,
                    chapter_id=chapter_id,
                    paragraph_id=paragraph_id,
                    utterance_id="",
                    metadata={"title": title},
                )
            )

    for fact in _list(payload.get("story_bible")):
        subject = _text(fact.get("subject"))
        predicate = _text(fact.get("predicate"))
        obj = _text(fact.get("object") or fact.get("value"))
        if not subject or not predicate or not obj:
            continue
        source_id = _text(fact.get("source_id")) or f"story-bible:{subject}:{predicate}:{obj}"
        chunks.append(
            _chunk(
                project_id=project_id,
                source_id=source_id,
                source_type="story_bible",
                text=f"{subject} {predicate}: {obj}",
                char_start=0,
                char_end=len(f"{subject} {predicate}: {obj}"),
                metadata={k: v for k, v in fact.items() if k not in {"source_id"}},
            )
        )

    for item in _list(payload.get("glossary")):
        term = _text(item.get("term"))
        pronunciation = _text(item.get("pronunciation") or item.get("reading"))
        if not term:
            continue
        source_id = _text(item.get("source_id")) or f"glossary:{term}"
        text = f"{term} pronunciation: {pronunciation}" if pronunciation else term
        chunks.append(
            _chunk(
                project_id=project_id,
                source_id=source_id,
                source_type="glossary",
                text=text,
                char_start=0,
                char_end=len(text),
                metadata={k: v for k, v in item.items() if k not in {"source_id"}},
            )
        )

    for role in _list(payload.get("roles")):
        role_id = _text(role.get("role_id") or role.get("roleId"))
        name = _text(role.get("name"))
        if not role_id and not name:
            continue
        aliases = "、".join(_text(alias) for alias in _list(role.get("aliases")) if _text(alias))
        parts = [
            f"角色：{name or role_id}",
            f"别名：{aliases}" if aliases else "",
            _text(role.get("profile")),
            _text(role.get("description")),
            _text(role.get("voice_description") or role.get("voiceDescription")),
            _text(role.get("voice_resource_id") or role.get("voiceResourceId")),
        ]
        text = "；".join(part for part in parts if part)
        chunks.append(
            _chunk(
                project_id=project_id,
                source_id=f"role:{role_id or name}",
                source_type="role_profile",
                text=text,
                char_start=0,
                char_end=len(text),
                metadata=role,
            )
        )

    for paragraph_id, utterances in (payload.get("utterances_by_paragraph") or {}).items():
        for utterance in _list(utterances):
            utterance_id = _text(utterance.get("utterance_id") or utterance.get("utteranceId"))
            text = _text(utterance.get("text"))
            if not utterance_id or not text:
                continue
            chunks.append(
                _chunk(
                    project_id=project_id,
                    source_id=f"utterance:{utterance_id}",
                    source_type="utterance",
                    text=text,
                    char_start=0,
                    char_end=len(text),
                    paragraph_id=_text(utterance.get("paragraph_id")) or str(paragraph_id),
                    utterance_id=utterance_id,
                    metadata=utterance,
                )
            )

    return chunks


def derive_story_bible_facts(
    *, project_id: str, chunks: list[dict[str, Any]], payload: dict[str, Any]
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for item in _list(payload.get("story_bible")):
        subject = _text(item.get("subject"))
        predicate = _text(item.get("predicate"))
        obj = _text(item.get("object") or item.get("value"))
        if subject and predicate and obj:
            facts.append(
                _fact(
                    project_id=project_id,
                    subject=subject,
                    predicate=predicate,
                    obj=obj,
                    confidence=_text(item.get("confidence")) or "model_suggested",
                    source_id=_text(item.get("source_id")) or "",
                    metadata=item,
                )
            )
    for item in _list(payload.get("glossary")):
        term = _text(item.get("term"))
        pronunciation = _text(item.get("pronunciation") or item.get("reading"))
        if term and pronunciation:
            facts.append(
                _fact(
                    project_id=project_id,
                    subject=term,
                    predicate="pronunciation",
                    obj=pronunciation,
                    confidence=_text(item.get("confidence")) or "user_confirmed",
                    source_id=_text(item.get("source_id")) or f"glossary:{term}",
                    metadata=item,
                )
            )
    for role in _list(payload.get("roles")):
        name = _text(role.get("name"))
        for alias in _list(role.get("aliases")):
            alias_text = _text(alias)
            if name and alias_text:
                facts.append(
                    _fact(
                        project_id=project_id,
                        subject=name,
                        predicate="alias",
                        obj=alias_text,
                        confidence="model_suggested",
                        source_id=f"role:{_text(role.get('role_id')) or name}",
                        metadata=role,
                    )
                )
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for fact in facts:
        if fact["fact_id"] in seen:
            continue
        seen.add(fact["fact_id"])
        unique.append(fact)
    return unique


def search_memory_chunks(
    *, chunks: list[dict[str, Any]], query: str, top_k: int = 5
) -> list[dict[str, Any]]:
    terms = _query_terms(query)
    results: list[dict[str, Any]] = []
    for chunk in chunks:
        text = _text(chunk.get("text"))
        score = _lexical_score(text, terms)
        if score <= 0:
            continue
        results.append(memory_result_from_chunk(chunk=chunk, score=score, query=query))
    return sorted(results, key=lambda item: item["score"], reverse=True)[: max(1, top_k)]


def memory_result_from_chunk(
    *,
    chunk: dict[str, Any],
    score: float,
    query: str,
) -> dict[str, Any]:
    text = _text(chunk.get("text"))
    return {
        "chunk_id": chunk["chunk_id"],
        "project_id": chunk["project_id"],
        "source_type": chunk["source_type"],
        "score": float(score),
        "text": text,
        "metadata": chunk.get("metadata") or {},
        "citation": _citation_for_chunk(chunk, query=query),
    }


def attach_memory_citations_to_role_candidates(
    candidates: list[RoleAnalysisCandidate],
    *,
    search: Callable[..., list[dict[str, Any]]],
) -> list[RoleAnalysisCandidate]:
    enriched: list[RoleAnalysisCandidate] = []
    for candidate in candidates:
        query = _text(candidate.name)
        citations = [item["citation"] for item in search(query, top_k=3)] if query else []
        enriched.append(
            replace(
                candidate,
                source_citations=citations,
                needs_human_review=candidate.needs_human_review or not citations,
            )
        )
    return enriched


def urllib_http_post(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


class OpenAICompatibleEmbeddingClient:
    def __init__(
        self,
        *,
        provider: dict[str, Any],
        api_key_lookup: Callable[[str], str | None] = os.environ.get,
        http_post: HttpPost = urllib_http_post,
    ):
        self.provider = provider
        self.api_key_lookup = api_key_lookup
        self.http_post = http_post

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        api_key_env = _text(self.provider.get("api_key_env")) or DEFAULT_EMBEDDING_API_KEY_ENV
        api_key = self.api_key_lookup(api_key_env)
        if not api_key:
            raise MissingProviderCredential(f"Missing API key environment variable: {api_key_env}")
        payload = {
            "model": _text(self.provider.get("model")) or DEFAULT_EMBEDDING_MODEL,
            "input": texts,
        }
        response = self.http_post(
            f"{_text(self.provider.get('base_url')).rstrip('/')}/embeddings",
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            payload,
            int(self.provider.get("timeout_seconds") or 60),
        )
        return [
            [float(value) for value in item["embedding"]]
            for item in response.get("data", [])
            if isinstance(item, dict) and isinstance(item.get("embedding"), list)
        ]


class QdrantMemoryStore:
    def __init__(
        self,
        *,
        base_url: str,
        collection_name: str = DEFAULT_QDRANT_COLLECTION,
        request_json: QdrantRequest | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.collection_name = collection_name
        self.request_json = request_json or self._request_json

    def ensure_collection(self, vector_size: int) -> dict[str, Any]:
        return self.request_json(
            "PUT",
            f"/collections/{self.collection_name}",
            {"vectors": {"size": vector_size, "distance": "Cosine"}},
        )

    def upsert(
        self,
        *,
        project_id: str,
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> dict[str, Any]:
        points = []
        for chunk, embedding in zip(chunks, embeddings, strict=False):
            points.append(
                {
                    "id": chunk["chunk_id"],
                    "vector": embedding,
                    "payload": {**chunk, "project_id": project_id},
                }
            )
        return self.request_json(
            "PUT",
            f"/collections/{self.collection_name}/points",
            {"points": points},
        )

    def search(self, *, project_id: str, embedding: list[float], top_k: int = 5) -> dict[str, Any]:
        return self.request_json(
            "POST",
            f"/collections/{self.collection_name}/points/search",
            {
                "vector": embedding,
                "limit": top_k,
                "with_payload": True,
                "filter": {
                    "must": [{"key": "project_id", "match": {"value": project_id}}],
                },
            },
        )

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}


def _split_text_chunk(
    *,
    project_id: str,
    source_id: str,
    source_type: str,
    text: str,
    max_chars: int,
    overlap: int,
    chapter_id: str = "",
    paragraph_id: str = "",
    utterance_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if len(text) <= max_chars:
        return [
            _chunk(
                project_id=project_id,
                source_id=source_id,
                source_type=source_type,
                text=text,
                char_start=0,
                char_end=len(text),
                chapter_id=chapter_id,
                paragraph_id=paragraph_id,
                utterance_id=utterance_id,
                metadata=metadata or {},
            )
        ]
    chunks: list[dict[str, Any]] = []
    start = 0
    safe_overlap = max(0, min(overlap, max_chars // 2))
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunks.append(
            _chunk(
                project_id=project_id,
                source_id=source_id,
                source_type=source_type,
                text=text[start:end],
                char_start=start,
                char_end=end,
                chapter_id=chapter_id,
                paragraph_id=paragraph_id,
                utterance_id=utterance_id,
                metadata=metadata or {},
            )
        )
        if end == len(text):
            break
        start = max(end - safe_overlap, start + 1)
    return chunks


def _chunk(
    *,
    project_id: str,
    source_id: str,
    source_type: str,
    text: str,
    char_start: int,
    char_end: int,
    chapter_id: str = "",
    paragraph_id: str = "",
    utterance_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    chunk_id = _stable_id(project_id, source_id, source_type, str(char_start), str(char_end), text)
    return {
        "chunk_id": chunk_id,
        "project_id": project_id,
        "source_id": source_id,
        "source_type": source_type,
        "chapter_id": chapter_id,
        "paragraph_id": paragraph_id,
        "utterance_id": utterance_id,
        "char_start": char_start,
        "char_end": char_end,
        "text": text,
        "metadata": metadata or {},
    }


def _fact(
    *,
    project_id: str,
    subject: str,
    predicate: str,
    obj: str,
    confidence: str,
    source_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fact_id = _stable_id(project_id, subject, predicate, obj, source_id)
    return {
        "fact_id": fact_id,
        "project_id": project_id,
        "subject": subject,
        "predicate": predicate,
        "object": obj,
        "confidence": confidence,
        "source_id": source_id,
        "metadata": metadata or {},
        "notes": _text((metadata or {}).get("notes")),
    }


def _citation_for_chunk(chunk: dict[str, Any], *, query: str) -> dict[str, Any]:
    text = _text(chunk.get("text"))
    snippet = _snippet(text, query)
    return {
        "source_id": chunk.get("source_id") or "",
        "source_type": chunk.get("source_type") or "",
        "chapter_id": chunk.get("chapter_id") or "",
        "paragraph_id": chunk.get("paragraph_id") or "",
        "utterance_id": chunk.get("utterance_id") or "",
        "char_start": chunk.get("char_start") or 0,
        "char_end": chunk.get("char_end") or len(text),
        "snippet": snippet,
    }


def _snippet(text: str, query: str) -> str:
    terms = _query_terms(query)
    first = min([text.find(term) for term in terms if term and text.find(term) >= 0] or [0])
    start = max(0, first - 20)
    end = min(len(text), first + 80)
    return text[start:end]


def _lexical_score(text: str, terms: list[str]) -> float:
    lowered = text.lower()
    score = 0.0
    for term in terms:
        if not term:
            continue
        score += lowered.count(term.lower()) * max(1.0, min(len(term), 8) / 2)
    return score


def _query_terms(query: str) -> list[str]:
    terms = [term for term in re.split(r"\s+", query.strip()) if term]
    compact = re.sub(r"\s+", "", query)
    if compact and not terms:
        terms.append(compact)
    if len(compact) >= 2:
        terms.extend(compact[index : index + 2] for index in range(len(compact) - 1))
    return list(dict.fromkeys(terms))


def _stable_id(*parts: str) -> str:
    joined = "\u241f".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:24]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
