from __future__ import annotations

from fastapi.testclient import TestClient


def _memory_payload() -> dict:
    return {
        "chapters": [
            {
                "chapter_id": "chapter-0001",
                "title": "第一章",
                "paragraphs": [
                    {
                        "paragraph_id": "p-0001",
                        "text": "林舟又被称为小舟，出场时总是压低声音。玄衡城是他的故乡。",
                    }
                ],
            }
        ],
        "story_bible": [
            {
                "subject": "林舟",
                "predicate": "alias",
                "object": "小舟",
                "confidence": "user_confirmed",
                "source_id": "manual-bible",
            }
        ],
        "glossary": [{"term": "玄衡", "pronunciation": "xuan heng", "source_id": "glossary-001"}],
        "roles": [
            {
                "role_id": "role-linzhou",
                "name": "林舟",
                "aliases": ["小舟"],
                "profile": "压低声音的青年主角",
                "voice_resource_id": "voice-001",
            }
        ],
    }


def test_v0_62_story_memory_chunks_keep_citations_and_facts():
    """Story memory chunks preserve exact project/source anchors for grounded retrieval."""
    from backend.app.domain.story_memory import (
        build_story_memory_chunks,
        derive_story_bible_facts,
    )

    chunks = build_story_memory_chunks(project_id="project-a", payload=_memory_payload())

    novel_chunk = next(chunk for chunk in chunks if chunk["source_type"] == "novel")
    assert novel_chunk["project_id"] == "project-a"
    assert novel_chunk["source_id"] == "chapter-0001:p-0001"
    assert novel_chunk["chapter_id"] == "chapter-0001"
    assert novel_chunk["paragraph_id"] == "p-0001"
    assert novel_chunk["char_start"] == 0
    assert novel_chunk["char_end"] == len(novel_chunk["text"])
    assert novel_chunk["metadata"]["title"] == "第一章"
    assert "玄衡城" in novel_chunk["text"]

    facts = derive_story_bible_facts(project_id="project-a", chunks=chunks, payload=_memory_payload())
    assert any(fact["subject"] == "林舟" and fact["predicate"] == "alias" for fact in facts)
    assert any(fact["subject"] == "玄衡" and fact["predicate"] == "pronunciation" for fact in facts)
    assert all(fact["project_id"] == "project-a" for fact in facts)


def test_v0_62_memory_index_search_and_story_bible_api(monkeypatch, tmp_path):
    """Memory API indexes project-scoped sources and searches with source citations."""
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))
    from backend.app.api.app import create_app

    with TestClient(create_app()) as client:
        project = client.post("/api/v1/projects", json={"name": "RAG项目"}).json()["project"]
        project_id = project["project_id"]

        indexed = client.post(
            f"/api/v1/projects/{project_id}/memory/index",
            json=_memory_payload(),
        )
        assert indexed.status_code == 200
        index_data = indexed.json()
        assert index_data["project_id"] == project_id
        assert index_data["chunk_count"] >= 3
        assert index_data["fact_count"] >= 2
        assert index_data["embedding_status"] == "skipped_missing_api_key"
        assert "SHUYI_EMBEDDING_API_KEY" in index_data["message"]

        searched = client.post(
            f"/api/v1/projects/{project_id}/memory/search",
            json={"query": "小舟 声音 故乡", "top_k": 3},
        )
        assert searched.status_code == 200
        search_data = searched.json()
        assert search_data["retrieval_mode"] == "sqlite_lexical"
        assert search_data["results"]
        first = search_data["results"][0]
        assert first["project_id"] == project_id
        assert first["citation"]["source_id"] == "chapter-0001:p-0001"
        assert first["citation"]["chapter_id"] == "chapter-0001"
        assert first["citation"]["paragraph_id"] == "p-0001"
        assert "小舟" in first["citation"]["snippet"]

        story_bible = client.get(f"/api/v1/projects/{project_id}/story-bible")
        assert story_bible.status_code == 200
        facts = story_bible.json()["facts"]
        alias_fact = next(fact for fact in facts if fact["predicate"] == "alias")
        assert alias_fact["confidence"] == "user_confirmed"

        patched = client.patch(
            f"/api/v1/projects/{project_id}/story-bible/facts/{alias_fact['fact_id']}",
            json={"confidence": "rejected", "notes": "误识别别名"},
        )
        assert patched.status_code == 200
        assert patched.json()["fact"]["confidence"] == "rejected"
        assert patched.json()["fact"]["notes"] == "误识别别名"


def test_v0_62_embedding_and_qdrant_clients_build_provider_safe_payloads():
    """Embedding and Qdrant adapters keep API keys out of payloads and filter by project."""
    from backend.app.domain.story_memory import (
        OpenAICompatibleEmbeddingClient,
        QdrantMemoryStore,
    )

    calls: list[dict] = []

    def fake_post(url: str, headers: dict[str, str], payload: dict, timeout_seconds: int) -> dict:
        calls.append({"url": url, "headers": headers, "payload": payload, "timeout": timeout_seconds})
        return {"data": [{"embedding": [0.1, 0.2, 0.3]}]}

    embeddings = OpenAICompatibleEmbeddingClient(
        provider={
            "base_url": "https://embed.example.test/v1",
            "model": "text-embedding-test",
            "api_key_env": "SHUYI_EMBEDDING_API_KEY",
        },
        api_key_lookup=lambda name: "test-key" if name == "SHUYI_EMBEDDING_API_KEY" else None,
        http_post=fake_post,
    ).embed_texts(["林舟"])

    assert embeddings == [[0.1, 0.2, 0.3]]
    assert calls[0]["url"] == "https://embed.example.test/v1/embeddings"
    assert calls[0]["headers"]["Authorization"] == "Bearer test-key"
    assert calls[0]["payload"] == {"model": "text-embedding-test", "input": ["林舟"]}

    qdrant_calls: list[dict] = []

    def fake_request(method: str, path: str, payload: dict | None = None) -> dict:
        qdrant_calls.append({"method": method, "path": path, "payload": payload})
        return {"result": [{"id": "chunk-1", "score": 0.91, "payload": {"text": "林舟"}}]}

    store = QdrantMemoryStore(
        base_url="http://qdrant:6333",
        collection_name="shuyi_story_memory",
        request_json=fake_request,
    )
    store.search(project_id="project-a", embedding=[0.1, 0.2, 0.3], top_k=5)

    search_payload = qdrant_calls[-1]["payload"]
    assert qdrant_calls[-1]["path"] == "/collections/shuyi_story_memory/points/search"
    assert search_payload["limit"] == 5
    assert search_payload["filter"]["must"][0]["key"] == "project_id"
    assert search_payload["filter"]["must"][0]["match"]["value"] == "project-a"


def test_v0_62_memory_search_uses_qdrant_when_vector_store_is_configured(
    monkeypatch, tmp_path
):
    """Configured embedding + Qdrant turns memory search into grounded vector retrieval."""
    monkeypatch.setenv("SHUYI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SHUYI_EMBEDDING_API_KEY", "test-key")
    monkeypatch.setenv("SHUYI_QDRANT_URL", "http://qdrant.test")

    from backend.app.api import app as app_module

    indexed_chunks: list[dict] = []

    class FakeEmbeddingClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def embed_texts(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2, 0.3] for _ in texts]

    class FakeQdrantMemoryStore:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def ensure_collection(self, vector_size: int) -> dict:
            return {"vector_size": vector_size}

        def upsert(
            self,
            *,
            project_id: str,
            chunks: list[dict],
            embeddings: list[list[float]],
        ) -> dict:
            indexed_chunks[:] = chunks
            return {"project_id": project_id, "count": len(embeddings)}

        def search(self, *, project_id: str, embedding: list[float], top_k: int = 5) -> dict:
            assert project_id
            assert embedding == [0.1, 0.2, 0.3]
            novel_chunk = next(chunk for chunk in indexed_chunks if chunk["source_type"] == "novel")
            return {"result": [{"id": novel_chunk["chunk_id"], "score": 0.97, "payload": novel_chunk}]}

    monkeypatch.setattr(app_module, "OpenAICompatibleEmbeddingClient", FakeEmbeddingClient)
    monkeypatch.setattr(app_module, "QdrantMemoryStore", FakeQdrantMemoryStore)

    with TestClient(app_module.create_app()) as client:
        project_id = client.post("/api/v1/projects", json={"name": "向量项目"}).json()["project"][
            "project_id"
        ]

        indexed = client.post(f"/api/v1/projects/{project_id}/memory/index", json=_memory_payload())
        assert indexed.status_code == 200
        assert indexed.json()["embedding_status"] == "qdrant_indexed"

        searched = client.post(
            f"/api/v1/projects/{project_id}/memory/search",
            json={"query": "林舟", "top_k": 2},
        )
        assert searched.status_code == 200
        search_data = searched.json()
        assert search_data["retrieval_mode"] == "qdrant_vector"
        assert search_data["results"][0]["score"] == 0.97
        assert search_data["results"][0]["citation"]["source_id"] == "chapter-0001:p-0001"


def test_v0_62_agent_candidates_receive_grounded_citations_or_human_review():
    """Agent-facing role candidates expose source citations and mark unsupported facts for review."""
    from backend.app.domain.dubbing_workflow import RoleAnalysisCandidate
    from backend.app.domain.story_memory import attach_memory_citations_to_role_candidates

    candidates = [
        RoleAnalysisCandidate(name="林舟", confidence=0.82, needs_human_review=False),
        RoleAnalysisCandidate(name="未知剑客", confidence=0.7, needs_human_review=False),
    ]
    enriched = attach_memory_citations_to_role_candidates(
        candidates,
        search=lambda query, top_k=3: [
            {
                "score": 0.9,
                "citation": {
                    "source_id": "chapter-0001:p-0001",
                    "chapter_id": "chapter-0001",
                    "paragraph_id": "p-0001",
                    "char_start": 0,
                    "char_end": 18,
                    "snippet": "林舟又被称为小舟。",
                },
            }
        ]
        if query == "林舟"
        else [],
    )

    supported = enriched[0].to_dict()
    unsupported = enriched[1].to_dict()
    assert supported["source_citations"][0]["source_id"] == "chapter-0001:p-0001"
    assert supported["needs_human_review"] is False
    assert unsupported["source_citations"] == []
    assert unsupported["needs_human_review"] is True
