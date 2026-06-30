"""
api/main.py — /policy REST API (FastAPI)

n8n → POST /api/policy/search → ChromaDB 검색 결과 반환
LLM 호출 없음, 인증 없음 (내부망 전용)
"""

from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.rag.chroma_store import search

app = FastAPI(title="InfraGuard Policy API", docs_url="/api/docs")


class PolicySearchRequest(BaseModel):
    query: str = ""
    n_results: int = 5
    sector: Optional[str] = None
    cert: Optional[str] = None
    law_type: Optional[str] = None


@app.post("/api/policy/search")
async def policy_search(req: PolicySearchRequest):
    """법령 조문 검색. chroma_store.search()를 직접 래핑."""
    if not req.query or not req.query.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "query는 필수 항목입니다."},
        )

    try:
        results = search(
            query=req.query,
            n_results=req.n_results,
            sector=req.sector,
            cert=req.cert,
            law_type=req.law_type,
        )
    except Exception:
        return JSONResponse(
            status_code=500,
            content={"error": "검색 중 오류가 발생했습니다."},
        )

    return {
        "query": req.query,
        "result_count": len(results),
        "results": results,
    }
