"""
core/advisor/prompt_builder.py — System/User Prompt 구성

SYSTEM_PROMPT: prompts/system_prompt.md 파일에서 로드
build_user_prompt(): 템플릿 + 현재 상황 + 자문 요청 + 히스토리 조합
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 프롬프트 파일 로더
# ─────────────────────────────────────────────────────────────────────────────

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
_prompt_cache: dict[str, str] = {}
_tools_cache: dict[str, dict] = {}


def load_prompt(filename: str) -> str:
    """
    prompts/ 디렉토리에서 프롬프트 파일을 읽어 반환.
    한 번 읽은 파일은 메모리에 캐시 (프로세스 재시작 전까지 유지).

    Args:
        filename: 파일명 (예: "system_prompt.md")

    Returns:
        파일 내용 문자열

    Raises:
        FileNotFoundError: prompts/{filename} 이 존재하지 않을 때
    """
    if filename in _prompt_cache:
        return _prompt_cache[filename]

    path = _PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(
            f"프롬프트 파일을 찾을 수 없습니다: {path}\n"
            f"prompts/ 디렉토리에 {filename} 파일을 생성하세요."
        )

    content = path.read_text(encoding="utf-8").strip()
    _prompt_cache[filename] = content
    logger.debug("프롬프트 로드: %s (%d chars)", filename, len(content))
    return content


def reload_prompt(filename: str) -> str:
    """캐시를 무효화하고 파일을 다시 읽음 (런타임 수정 반영용)."""
    _prompt_cache.pop(filename, None)
    return load_prompt(filename)


def load_tools(*filenames: str, with_cache_control: bool = True) -> list[dict]:
    """
    prompts/tools/ 디렉토리에서 tool 정의 JSON 파일을 읽어 반환.
    한 번 읽은 파일은 메모리에 캐시.

    Args:
        *filenames: 파일명 목록 (예: "rag_search.json", "search_decisions.json")
        with_cache_control: True이면 마지막 tool에 cache_control 추가
                            (Anthropic prompt caching — 시스템 프롬프트 + 툴 전체 캐시)

    Returns:
        tool 정의 dict 리스트

    Raises:
        FileNotFoundError: prompts/tools/{filename} 이 존재하지 않을 때
    """
    tools: list[dict] = []
    for filename in filenames:
        if filename not in _tools_cache:
            path = _PROMPTS_DIR / "tools" / filename
            if not path.exists():
                raise FileNotFoundError(
                    f"툴 정의 파일을 찾을 수 없습니다: {path}\n"
                    f"prompts/tools/ 디렉토리에 {filename} 파일을 생성하세요."
                )
            _tools_cache[filename] = json.loads(path.read_text(encoding="utf-8"))
            logger.debug("툴 정의 로드: %s", filename)
        tools.append(dict(_tools_cache[filename]))  # shallow copy (cache_control 추가 대비)

    if with_cache_control and tools:
        tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}

    return tools


def reload_tools(*filenames: str) -> list[dict]:
    """툴 캐시를 무효화하고 파일을 다시 읽음."""
    for filename in filenames:
        _tools_cache.pop(filename, None)
    return load_tools(*filenames)


# ─────────────────────────────────────────────────────────────────────────────
# User Prompt 빌더
# ─────────────────────────────────────────────────────────────────────────────

def build_user_prompt(
    template: dict | None,
    env_context: str,
    user_query: str,
    history_list: list[dict],
    history_mode: str,
) -> str:
    """
    User Prompt 조합.

    Args:
        template:     템플릿 항목값 dict (없으면 None).
                      예: {"size": "중소기업", "sector": "IT/소프트웨어",
                            "cert": "ISMS-P", "privacy": "처리", "employees": "50명"}
                      항목값이 None이거나 "사용 안함"이면 해당 줄 제외.
        env_context:  현재 상황 서술 (자유 텍스트)
        user_query:   자문 요청 본문
        history_list: [{id, summary}, ...] 최근 최대 100건
        history_mode: "ON" | "OFF"

    Returns:
        완성된 User Prompt 문자열
    """
    parts: list[str] = []

    # ── 회사 컨텍스트 (템플릿) ────────────────────────────────────────────────
    if template:
        ctx_lines: list[str] = []
        _field_labels = {
            "size":      "회사 규모",
            "sector":    "업종",
            "cert":      "보유 인증",
            "privacy":   "개인정보 처리",
            "employees": "임직원 수",
        }
        for key, label in _field_labels.items():
            val = template.get(key)
            if val and str(val).strip() and str(val).strip() != "사용 안함":
                ctx_lines.append(f"{label}: {val}")
        # 추가 커스텀 항목
        for key, val in template.items():
            if key not in _field_labels and val and str(val).strip() != "사용 안함":
                ctx_lines.append(f"{key}: {val}")

        if ctx_lines:
            parts.append("[회사 컨텍스트]\n" + "\n".join(ctx_lines))

    # ── 현재 상황 ────────────────────────────────────────────────────────────
    if env_context and env_context.strip():
        parts.append(f"[현재 상황]\n{env_context.strip()}")

    # ── 자문 요청 ────────────────────────────────────────────────────────────
    parts.append(f"[자문 요청]\n{user_query.strip()}")

    # ── 과거 자문 히스토리 ───────────────────────────────────────────────────
    recent = history_list[-100:]  # 최근 100건
    if recent:
        history_lines = [f"history_mode: {history_mode}"]
        for item in recent:
            history_lines.append(f"  - id={item['id']}: {item['summary']}")
        parts.append("[과거 자문 이력]\n" + "\n".join(history_lines))
    else:
        parts.append(f"[과거 자문 이력]\nhistory_mode: {history_mode}\n(이력 없음)")

    return "\n\n".join(parts)
