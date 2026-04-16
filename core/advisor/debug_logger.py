"""
core/advisor/debug_logger.py — Claude API 호출 디버그 로거 (개발용)

출력 파일: data/claude_debug.jsonl
  - 자문 1건 = 1개 JSON 라인
  - tool_use 루프 전체 추적 포함

비활성화: .env에 CLAUDE_DEBUG=0 설정 (기본 활성화)
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_LOG_PATH = Path(__file__).parent.parent.parent / "data" / "claude_debug.jsonl"
_ENABLED = os.environ.get("CLAUDE_DEBUG", "1") != "0"


def is_enabled() -> bool:
    return _ENABLED


def log_session(session: dict) -> None:
    """
    자문 1회 세션 전체를 JSONL에 기록.

    session 구조:
    {
      "timestamp":        str,
      "user_query":       str,
      "history_mode":     str,
      "template_used":    bool,
      "iterations": [
        {
          "iteration":       int,
          "input_tokens":    int,
          "output_tokens":   int,
          "cache_creation":  int,   # 신규 캐시 저장 토큰
          "cache_read":      int,   # 캐시 히트 토큰 (rate limit 절감분)
          "stop_reason":     str,
          "tools_called": [
            {
              "name":          str,
              "input":         dict,
              "result_chars":  int,
              "result_preview":str   # 앞 200자
            }
          ]
        }
      ],
      "total_input_tokens":   int,
      "total_output_tokens":  int,
      "total_cache_read":     int,
      "total_iterations":     int,
      "status":               str,   # "success" | "error"
      "error":                str    # 에러 시 메시지
    }
    """
    if not _ENABLED:
        return

    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(session, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("디버그 로그 기록 실패: %s", e)


def new_session(user_query: str, history_mode: str, template_used: bool) -> dict:
    """새 세션 딕셔너리 생성."""
    return {
        "timestamp":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user_query":     user_query[:200],
        "history_mode":   history_mode,
        "template_used":  template_used,
        "iterations":     [],
        "total_input_tokens":  0,
        "total_output_tokens": 0,
        "total_cache_read":    0,
        "total_iterations":    0,
        "status":         "in_progress",
        "error":          "",
    }


def record_iteration(session: dict, iteration: int, response, tools_called: list[dict]) -> None:
    """한 iteration 결과를 session에 기록."""
    usage = getattr(response, "usage", None)
    input_tokens  = getattr(usage, "input_tokens",                  0) if usage else 0
    output_tokens = getattr(usage, "output_tokens",                 0) if usage else 0
    cache_create  = getattr(usage, "cache_creation_input_tokens",   0) if usage else 0
    cache_read    = getattr(usage, "cache_read_input_tokens",       0) if usage else 0

    session["iterations"].append({
        "iteration":      iteration,
        "input_tokens":   input_tokens,
        "output_tokens":  output_tokens,
        "cache_creation": cache_create,
        "cache_read":     cache_read,
        "stop_reason":    response.stop_reason,
        "tools_called":   tools_called,
    })

    session["total_input_tokens"]  += input_tokens
    session["total_output_tokens"] += output_tokens
    session["total_cache_read"]    += cache_read
    session["total_iterations"]     = iteration


def finalize_session(session: dict, status: str = "success", error: str = "") -> None:
    """세션 완료 처리 후 로그 기록."""
    session["status"] = status
    session["error"]  = error
    log_session(session)

    if _ENABLED:
        _print_summary(session)


def _print_summary(session: dict) -> None:
    """터미널에 세션 요약 출력."""
    iters = session["iterations"]
    total_in  = session["total_input_tokens"]
    total_out = session["total_output_tokens"]
    cache_hit = session["total_cache_read"]
    saved_pct = round(cache_hit / total_in * 100, 1) if total_in > 0 else 0

    print("\n" + "─" * 60)
    print(f"[Claude 디버그] {session['timestamp']}")
    print(f"  요청: {session['user_query'][:80]}")
    print(f"  iterations: {len(iters)}회")
    print(f"  입력 토큰 합계: {total_in:,}  (캐시 히트: {cache_hit:,} = {saved_pct}% 절감)")
    print(f"  출력 토큰 합계: {total_out:,}")
    print(f"  상태: {session['status']}")

    for it in iters:
        tools = it.get("tools_called", [])
        tool_str = ", ".join(f"{t['name']}({t['result_chars']}chars)" for t in tools) or "없음"
        print(f"  [{it['iteration']}] in={it['input_tokens']} out={it['output_tokens']} "
              f"cache_read={it['cache_read']} stop={it['stop_reason']} tools=[{tool_str}]")

    print("─" * 60)
