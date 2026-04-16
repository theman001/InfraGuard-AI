"""
core/advisor/tool_definitions.py — Claude에게 전달할 Tool 스키마

실제 스키마는 prompts/tools/ 에 JSON 파일로 관리:
  - prompts/tools/rag_search.json
  - prompts/tools/search_decisions.json
  - prompts/tools/get_decision_text.json

ALL_TOOL_DEFINITIONS: claude_client에서 API 호출 시 사용.
  - 마지막 tool(get_decision_text)에 cache_control 자동 부착 (Anthropic prompt caching)
"""

from core.advisor.prompt_builder import load_tools

_TOOL_FILES = (
    "rag_search.json",
    "search_decisions.json",
    "get_decision_text.json",
)

# 모듈 임포트 시점에 로드 (캐시됨 — 파일 I/O는 최초 1회)
ALL_TOOL_DEFINITIONS: list[dict] = load_tools(*_TOOL_FILES, with_cache_control=True)
