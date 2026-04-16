"""
core/advisor/claude_client.py — Claude API tool_use 루프 + 응답 JSON 파싱

흐름:
  1. build_user_prompt()로 User Prompt 구성
  2. Claude API 호출 (tool_use 루프, MAX_ITERATIONS=10)
     - stop_reason == "tool_use": execute_tool() 실행 후 결과 추가
     - stop_reason == "end_turn": 루프 종료
  3. 최종 텍스트 블록에서 JSON 파싱
  4. 파싱 실패 시 1회 재시도

공개 API:
  generate_advisory(template, env_context, user_query, history_list, history_mode)
    → dict  {summary, applicable_laws, precedents, conclusion, gray_areas, similar_history}
"""

import json
import logging
import os
import re
import time

import anthropic

from core.advisor.tool_definitions import ALL_TOOL_DEFINITIONS
from core.advisor.tool_executor import execute_tool
from core.advisor.prompt_builder import load_prompt, build_user_prompt
from core.advisor import debug_logger

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192
MAX_ITERATIONS = 10

# Rate limit 대응
_HISTORY_LIMIT = 20        # 히스토리 최대 전달 건수 (토큰 절감)
_HISTORY_SUMMARY_MAX = 80  # 히스토리 요약 최대 글자 수
_RETRY_MAX = 3             # 429 재시도 횟수
_RETRY_BASE_WAIT = 10      # 재시도 대기 기본 초 (exponential backoff)

# 필수 키 — 파싱 결과 검증용
_REQUIRED_KEYS = {"summary", "applicable_laws", "precedents", "conclusion",
                  "gray_areas", "similar_history"}


def generate_advisory(
    template: dict | None,
    env_context: str,
    user_query: str,
    history_list: list[dict],
    history_mode: str = "OFF",
    claude_api_key: str = "",
    law_api_key: str = "",
) -> dict:
    """
    자문 생성 메인 함수.

    Args:
        template:       회사 컨텍스트 템플릿 (없으면 None)
        env_context:    현재 상황 서술
        user_query:     자문 요청 본문
        history_list:   [{id, summary}, ...] 최근 최대 100건
        history_mode:   "ON" | "OFF"
        claude_api_key: 사용자 LLM API 키 (우선). 없으면 .env CLAUDE_API_KEY 폴백.
        law_api_key:    사용자 국가법령 API 키 (MCP 호출용). 없으면 .env LAW_OC_ID 폴백.

    Returns:
        자문 결과 dict
        {summary, applicable_laws, precedents, conclusion, gray_areas, similar_history}

    Raises:
        RuntimeError: Claude API 호출 실패 또는 JSON 파싱 최종 실패
    """
    # API 키 우선순위: 인자 > .env
    api_key = (
        claude_api_key.strip()
        or os.environ.get("CLAUDE_API_KEY", "")
    )
    if not api_key or api_key == "your_claude_api_key_here":
        raise RuntimeError(
            "Claude API 키가 설정되지 않았습니다. "
            "마이페이지에서 LLM API 키를 등록하거나 .env의 CLAUDE_API_KEY를 확인하세요."
        )

    client = anthropic.Anthropic(api_key=api_key)

    # 히스토리 토큰 절감: 최근 N건 + 요약 길이 제한
    trimmed_history = [
        {"id": h["id"], "summary": (h["summary"] or "")[:_HISTORY_SUMMARY_MAX]}
        for h in history_list[-_HISTORY_LIMIT:]
    ]

    user_prompt = build_user_prompt(
        template=template,
        env_context=env_context,
        user_query=user_query,
        history_list=trimmed_history,
        history_mode=history_mode,
    )

    messages: list[dict] = [{"role": "user", "content": user_prompt}]

    # law_api_key 우선순위: 인자 > .env
    _law_key = law_api_key.strip() or os.environ.get("LAW_OC_ID", "")

    # ── 디버그 세션 초기화 ────────────────────────────────────────────────────
    dbg = debug_logger.new_session(
        user_query=user_query,
        history_mode=history_mode,
        template_used=template is not None,
    )

    # ── tool_use 루프 ─────────────────────────────────────────────────────────
    try:
        for iteration in range(MAX_ITERATIONS):
            logger.debug("Claude API 호출 (iteration=%d)", iteration + 1)

            response = _call_with_retry(client, messages)

            logger.debug("stop_reason=%s", response.stop_reason)

            if response.stop_reason == "end_turn":
                debug_logger.record_iteration(dbg, iteration + 1, response, [])
                debug_logger.finalize_session(dbg)
                final_text = _extract_text(response.content)
                return _parse_advisory_json(final_text, client, messages, response)

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                tools_called = []
                for block in response.content:
                    if block.type == "tool_use":
                        logger.debug("tool 실행: %s  input=%s", block.name, block.input)
                        result_text = execute_tool(block.name, block.input, law_api_key=_law_key)
                        # tool 결과도 길이 제한 (판례 원문 등이 너무 길면 토큰 급증)
                        if len(result_text) > 6000:
                            result_text = result_text[:6000] + "\n...(이하 생략)"
                        logger.debug("tool 결과 길이: %d chars", len(result_text))
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_text,
                        })
                        tools_called.append({
                            "name": block.name,
                            "input": block.input,
                            "result_chars": len(result_text),
                            "result_preview": result_text[:200],
                        })

                debug_logger.record_iteration(dbg, iteration + 1, response, tools_called)
                messages.append({"role": "user", "content": tool_results})
                continue

            # 예상치 못한 stop_reason
            logger.warning("예상치 못한 stop_reason: %s", response.stop_reason)
            debug_logger.record_iteration(dbg, iteration + 1, response, [])
            debug_logger.finalize_session(dbg)
            final_text = _extract_text(response.content)
            return _parse_advisory_json(final_text, client, messages, response)

        err_msg = f"tool_use 루프가 MAX_ITERATIONS({MAX_ITERATIONS})를 초과했습니다."
        debug_logger.finalize_session(dbg, status="error", error=err_msg)
        raise RuntimeError(err_msg)

    except RuntimeError:
        raise
    except Exception as e:
        debug_logger.finalize_session(dbg, status="error", error=str(e))
        raise


def _call_with_retry(client: anthropic.Anthropic, messages: list[dict]):
    """
    Claude API 호출 + 429 rate limit 자동 재시도 (exponential backoff).
    시스템 프롬프트는 prompts/system_prompt.md 에서 로드 + Anthropic prompt caching 적용.
    _RETRY_MAX 초과 시 마지막 예외를 그대로 raise.
    """
    # 시스템 프롬프트: 파일에서 로드 + cache_control (tool_use 반복 시 토큰 절감)
    system_with_cache = [
        {
            "type": "text",
            "text": load_prompt("system_prompt.md"),
            "cache_control": {"type": "ephemeral"},
        }
    ]

    for attempt in range(_RETRY_MAX):
        try:
            return client.messages.create(
                model=MODEL,
                system=system_with_cache,  # type: ignore[arg-type]
                messages=messages,
                tools=ALL_TOOL_DEFINITIONS,  # type: ignore[arg-type]
                max_tokens=MAX_TOKENS,
            )
        except anthropic.RateLimitError as e:
            if attempt >= _RETRY_MAX - 1:
                raise RuntimeError(
                    f"API 요청 한도(Rate Limit) 초과로 자문 생성에 실패했습니다. "
                    f"잠시 후 다시 시도해주세요. ({e})"
                ) from e
            wait = _RETRY_BASE_WAIT * (2 ** attempt)  # 10s → 20s → 40s
            logger.warning("Rate limit 429. %d초 후 재시도 (%d/%d)", wait, attempt + 1, _RETRY_MAX)
            time.sleep(wait)


# ─────────────────────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _extract_text(content: list) -> str:
    """응답 content 블록에서 텍스트만 추출."""
    parts = []
    for block in content:
        if hasattr(block, "type") and block.type == "text":
            parts.append(block.text)
    return "\n".join(parts).strip()


def _parse_advisory_json(
    text: str,
    client: anthropic.Anthropic,
    messages: list[dict],
    last_response,
) -> dict:
    """
    JSON 파싱. 실패 시 1회 재시도.
    성공하면 필수 키 검증 후 반환.
    """
    result = _try_parse_json(text)
    if result is not None and _REQUIRED_KEYS.issubset(result.keys()):
        return result

    # ── 재시도: Claude에게 JSON만 다시 요청 ──────────────────────────────────
    logger.warning("JSON 파싱 실패. 재시도합니다. raw text=%s", text[:200])

    retry_messages = list(messages)
    retry_messages.append({"role": "assistant", "content": last_response.content})
    retry_messages.append({
        "role": "user",
        "content": (
            "응답을 JSON 형식으로 다시 출력하세요. "
            "JSON 외 텍스트(설명, 마크다운 코드블록 등)는 포함하지 마세요. "
            "필수 키: summary, applicable_laws, precedents, conclusion, "
            "gray_areas, similar_history"
        ),
    })

    retry_response = client.messages.create(
        model=MODEL,
        system=[{
            "type": "text",
            "text": load_prompt("system_prompt.md"),
            "cache_control": {"type": "ephemeral"},
        }],  # type: ignore[arg-type]
        messages=retry_messages,
        max_tokens=MAX_TOKENS,
    )
    retry_text = _extract_text(retry_response.content)
    result = _try_parse_json(retry_text)

    if result is not None and _REQUIRED_KEYS.issubset(result.keys()):
        return result

    raise RuntimeError(
        f"JSON 파싱 최종 실패.\n--- raw ---\n{retry_text[:500]}"
    )


def _try_parse_json(text: str) -> dict | None:
    """
    텍스트에서 JSON 파싱 시도.
    마크다운 코드블록 제거 후 시도. 실패하면 None 반환.
    """
    if not text:
        return None

    # 마크다운 코드블록 제거
    cleaned = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()

    # JSON 오브젝트 영역만 추출 (앞뒤 불필요 텍스트 제거)
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        cleaned = match.group(0)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None
