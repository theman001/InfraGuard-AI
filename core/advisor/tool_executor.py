"""
core/advisor/tool_executor.py — Tool 실행 분기

Claude tool_use 루프에서 호출되는 진입점.

  rag_search                → execute_rag_tool()    (ChromaDB)
  search_decisions          → execute_mcp_tool()    (korean-law MCP)
  get_decision_text         → execute_mcp_tool()    (korean-law MCP)
"""

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

# chroma_store는 실제 RAG 검색 시점에 지연 임포트

# 로컬 korean-law-mcp 빌드 경로 (npx 원격 다운로드 불필요)
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_LOCAL_MCP_JS = _PROJECT_ROOT / "korean-law-mcp" / "build" / "index.js"


def _resolve_node() -> str:
    """node 실행 경로 반환."""
    found = shutil.which("node")
    if found:
        return found
    if sys.platform == "win32":
        candidates = [
            r"C:\Program Files\nodejs\node.exe",
            r"C:\Program Files (x86)\nodejs\node.exe",
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
    return "node"


def _resolve_mcp_cmd() -> list[str]:
    """
    MCP 서버 실행 커맨드 결정.
    우선순위:
      1. 로컬 build/index.js (node 직접 실행) — 빠르고 안정적
      2. npx korean-law-mcp (폴백)
    """
    if _LOCAL_MCP_JS.exists():
        node = _resolve_node()
        return [node, str(_LOCAL_MCP_JS)]

    # npx 폴백
    npx = shutil.which("npx") or shutil.which("npx.cmd") or "npx"
    return [npx, "-y", "korean-law-mcp"]


_MCP_CMD = _resolve_mcp_cmd()
_MCP_ENV = {**os.environ, "LAW_OC": os.environ.get("LAW_OC_ID", "")}

# MCP JSON-RPC 타임아웃 (초)
_MCP_TIMEOUT = 30


# ─────────────────────────────────────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────────────────────────────────────

def execute_tool(tool_name: str, tool_input: dict, law_api_key: str = "") -> str:
    """Claude tool_use에서 호출. tool_name에 따라 RAG 또는 MCP로 분기."""
    if tool_name == "rag_search":
        return execute_rag_tool(tool_input)
    elif tool_name in ("search_decisions", "get_decision_text"):
        return execute_mcp_tool(tool_name, tool_input, law_api_key=law_api_key)
    else:
        return f"[ERROR] 알 수 없는 tool: {tool_name}"


# ─────────────────────────────────────────────────────────────────────────────
# RAG: ChromaDB 검색
# ─────────────────────────────────────────────────────────────────────────────

def execute_rag_tool(tool_input: dict) -> str:
    """
    rag_search 실행.
    ChromaDB search() → 결과 포맷팅 → 문자열 반환
    """
    query: str = tool_input.get("query", "")
    sector: str | None = tool_input.get("sector")
    cert: str | None = tool_input.get("cert")
    n_results: int = min(int(tool_input.get("n_results", 5)), 20)

    if not query:
        return "[ERROR] rag_search: query가 비어 있습니다."

    try:
        from core.rag.chroma_store import search
        results = search(query=query, n_results=n_results, sector=sector, cert=cert)
    except Exception as e:
        return f"[ERROR] ChromaDB 검색 실패: {e}"

    if not results:
        return (
            "관련 법령 조문을 찾지 못했습니다. "
            "다른 키워드로 재검색하거나, 법령 범위 밖의 질문일 수 있습니다."
        )

    lines = [f"법령 조문 검색 결과 ({len(results)}건):\n"]
    for i, r in enumerate(results, 1):
        lines.append(
            f"[{i}] {r['law_name']} {r['article_label']}\n"
            f"    시행일: {r['effective_date']}\n"
            f"    내용: {r['full_text']}\n"
        )

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# MCP: korean-law stdio JSON-RPC
# ─────────────────────────────────────────────────────────────────────────────

def execute_mcp_tool(tool_name: str, tool_input: dict, law_api_key: str = "") -> str:
    """
    korean-law MCP 서버 subprocess 호출 (stdio JSON-RPC).

    프로토콜:
      1. initialize  (capabilities 핸드셰이크)
      2. tools/call  (실제 tool 실행)
      3. 프로세스 종료
    """
    # law_api_key 우선순위: 인자 > 환경변수
    _effective_law_key = law_api_key.strip() or os.environ.get("LAW_OC_ID", "")
    try:
        proc = subprocess.Popen(
            _MCP_CMD,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,  # 디버그용: stderr 캡처
            env=_MCP_ENV,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError:
        return (
            f"[ERROR] Node.js를 찾을 수 없습니다.\n"
            f"  시도한 커맨드: {_MCP_CMD}\n"
            f"  node 경로: {_resolve_node()}"
        )

    try:
        result_text = _run_mcp_session(proc, tool_name, tool_input, _effective_law_key)
    finally:
        try:
            proc.stdin.close()  # type: ignore[union-attr]
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    return result_text


def _run_mcp_session(
    proc: subprocess.Popen,
    tool_name: str,
    tool_input: dict,
    law_api_key: str = "",
) -> str:
    """
    MCP 세션 진행 (queue 기반 reader):
      1. initialize → initialized 알림
      2. tools/call → 결과 반환
    """
    # ── stdout을 queue로 비동기 수집 ─────────────────────────────────────────
    resp_queue: queue.Queue[dict | None] = queue.Queue()

    def _reader():
        try:
            for raw in proc.stdout:  # type: ignore[union-attr]
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    resp_queue.put(obj)
                except json.JSONDecodeError:
                    pass  # JSON이 아닌 행 무시 (npx 시작 메시지 등)
        finally:
            resp_queue.put(None)  # 프로세스 종료 신호

    reader_thread = threading.Thread(target=_reader, daemon=True)
    reader_thread.start()

    def send(obj: dict) -> None:
        line = json.dumps(obj, ensure_ascii=False) + "\n"
        proc.stdin.write(line)  # type: ignore[union-attr]
        proc.stdin.flush()       # type: ignore[union-attr]

    def recv_by_id(target_id: int, timeout: float) -> dict | None:
        """queue에서 target_id 응답을 찾을 때까지 소비. 없으면 None."""
        deadline = time.time() + timeout
        pending: list[dict] = []
        while time.time() < deadline:
            remaining = max(0.1, deadline - time.time())
            try:
                obj = resp_queue.get(timeout=min(remaining, 0.5))
            except queue.Empty:
                continue
            if obj is None:
                # 프로세스 종료 — 수집된 pending 돌려놓기
                for p in pending:
                    resp_queue.put(p)
                return None
            if obj.get("id") == target_id:
                for p in pending:
                    resp_queue.put(p)
                return obj
            pending.append(obj)
        # 타임아웃 — pending 반환
        for p in pending:
            resp_queue.put(p)
        return None

    req_id = 0
    _law_key = law_api_key.strip() or os.environ.get("LAW_OC_ID", "")

    # ── 1. initialize ────────────────────────────────────────────────────────
    req_id += 1
    send({
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "infra-guard", "version": "1.0"},
        },
    })
    init_resp = recv_by_id(req_id, timeout=20)
    if init_resp is None:
        # stderr 일부 캡처해서 힌트 제공
        try:
            stderr_hint = proc.stderr.read(500) if proc.stderr else ""  # type: ignore[union-attr]
        except Exception:
            stderr_hint = ""
        return (
            "[ERROR] MCP initialize 응답 타임아웃\n"
            f"  커맨드: {_MCP_CMD}\n"
            f"  stderr: {stderr_hint[:300]}"
        )
    if "error" in init_resp:
        return f"[ERROR] MCP initialize 실패: {init_resp['error']}"

    # initialized 알림 전송
    send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    # ── 2. tools/call ────────────────────────────────────────────────────────
    req_id += 1
    call_input = dict(tool_input)
    if "apiKey" not in call_input:
        call_input["apiKey"] = _law_key

    send({
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": call_input},
    })
    call_resp = recv_by_id(req_id, timeout=_MCP_TIMEOUT)
    if call_resp is None:
        return "[ERROR] MCP tools/call 응답 타임아웃"
    if "error" in call_resp:
        return f"[ERROR] MCP tools/call 실패: {call_resp['error']}"

    # ── 3. 결과 추출 ──────────────────────────────────────────────────────────
    return _extract_mcp_content(call_resp.get("result", {}))


def _extract_mcp_content(result: Any) -> str:
    """MCP tools/call 결과에서 텍스트 추출."""
    if isinstance(result, dict):
        content = result.get("content", [])
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
            if parts:
                return "\n".join(parts)
        if "text" in result:
            return str(result["text"])
    return str(result) if result else "[결과 없음]"
