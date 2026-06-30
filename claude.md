# 한국 법 자문 서비스 — InfraGuard-AI

프로젝트 명세: `korean_legal_advisory_service.md` 참고

---

## 프로젝트 개요

Streamlit 기반 한국 법률 자문 RAG 서비스. Rock 5 보드(ARM64)에서 Docker로 구동.

**기술 스택**
- Web UI: Streamlit (포트 8501, 컨테이너명: `infra-guard-ai`)
- 벡터 DB: ChromaDB (PersistentClient, `legal_advisory` 컬렉션)
- 임베딩: ko-sroberta-multitask (sentence-transformers, 로컬)
- LLM: Anthropic Claude API
- DB: SQLite
- 법령/판례 MCP: korean-law-mcp (별도 컨테이너, 포트 3000)

**주요 디렉토리**
```
app/          — Streamlit 페이지 (건드리지 말 것)
core/
  auth.py     — 인증 (건드리지 말 것)
  rag/
    chroma_store.py  — ChromaDB 저장/조회 (search() 함수 수정 금지)
    embedder.py      — 임베딩
    chunker.py       — 청킹
    collector.py     — 법령 수집
  advisor/
    claude_client.py — tool_use 루프 자문 생성 (무거움, 외부 API용으로 사용 X)
prompts/      — 프롬프트 파일
data/         — laws_registry.json, chroma_db
db/           — SQLite
```

---

## 작업 원칙

1. **`app/`, `core/auth.py` 등 기존 Streamlit/인증 로직은 절대 수정하지 않는다.**
2. **`core/rag/chroma_store.py`의 `search()` 함수는 수정하지 않고 import만 한다.**
3. **`core/advisor/claude_client.py`의 `generate_advisory()`는 외부 API에서 사용하지 않는다** (Claude API 비용/지연 큼).
4. 신규 기능은 별도 파일로 추가한다.
5. 기존 코드 스타일을 따른다: 한국어 docstring, 타입 힌트 사용.

---

## `/policy` API 엔드포인트 작업 컨텍스트

SOC Bot(Mattermost → n8n) 프로젝트에서 `/policy {키워드}` 명령어를 지원하기 위해
`infra-guard-ai` 컨테이너에 **FastAPI 기반 경량 REST API**를 추가하는 작업이 진행 중.

- n8n이 `POST /api/policy/search`를 호출 → ChromaDB 검색 결과(JSON) 반환
- LLM 호출 없음, `chroma_store.search()` 직접 래핑
- 인증 없음 (내부망 전용)

**미결 사항**
- [ ] 같은 컨테이너에 uvicorn 추가 vs 사이드카 컨테이너 분리
- [ ] API 포트 번호 확정
- [ ] n8n ↔ InfraGuard-AI 네트워크 경로 (Docker 내부 vs Cloudflare Tunnel)
