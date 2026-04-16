"""
test/test_phase3.py — Phase 3 자문 엔진 통합 테스트

테스트 항목:
  1. ChromaDB 연결 + rag_search 실행
  2. MCP search_decisions 실행 (판례 검색)
  3. generate_advisory() 전체 흐름 (rag + MCP + Claude tool_use)
"""

import json
import os
import sys

# 프로젝트 루트를 sys.path에 추가
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

# .env 로드
from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))


def separator(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ─────────────────────────────────────────────────────────────────────────────
# 1. rag_search — ChromaDB 검색
# ─────────────────────────────────────────────────────────────────────────────

def test_rag_search():
    separator("1. rag_search (ChromaDB)")

    from core.advisor.tool_executor import execute_rag_tool

    queries = [
        {"query": "CCTV 설치 개인정보 고지 의무"},
        {"query": "개인정보 처리방침 공개", "sector": "금융/핀테크"},
        {"query": "BYOD 정책 개인 디바이스", "n_results": 3},
    ]

    for q in queries:
        print(f"\n[쿼리] {q}")
        result = execute_rag_tool(q)
        # 결과 앞 500자만 출력
        print(result[:500])
        print("..." if len(result) > 500 else "")

    print("\n✅ rag_search 테스트 완료")


# ─────────────────────────────────────────────────────────────────────────────
# 2. search_decisions — MCP 판례 검색
# ─────────────────────────────────────────────────────────────────────────────

def test_search_decisions():
    separator("2. search_decisions (MCP)")

    from core.advisor.tool_executor import execute_mcp_tool

    print("\n[판례 검색] domain=precedent, query='개인정보 수집 동의'")
    result = execute_mcp_tool("search_decisions", {
        "domain": "precedent",
        "query": "개인정보 수집 동의",
        "display": 5,
    })
    print(result[:800])
    print("..." if len(result) > 800 else "")

    print("\n[개인정보위 결정문] domain=pipc, query='영상정보처리기기'")
    result2 = execute_mcp_tool("search_decisions", {
        "domain": "pipc",
        "query": "영상정보처리기기",
        "display": 5,
    })
    print(result2[:800])
    print("..." if len(result2) > 800 else "")

    print("\n✅ search_decisions 테스트 완료")


# ─────────────────────────────────────────────────────────────────────────────
# 3. generate_advisory() — 전체 자문 흐름
# ─────────────────────────────────────────────────────────────────────────────

def test_generate_advisory():
    separator("3. generate_advisory() — 전체 흐름")

    from core.advisor.claude_client import generate_advisory
    from core.advisor.gray_area import has_gray_area, format_gray_area_text, is_blocked

    template = {
        "size": "중소기업",
        "sector": "IT/소프트웨어",
        "cert": "ISMS-P",
        "privacy": "처리",
        "employees": "80명",
    }
    env_context = "사무실 내 직원 출입 관리를 위해 CCTV 8대를 신규 설치할 예정입니다."
    user_query = "CCTV 설치 시 개인정보 처리방침 고지 의무와 동의 절차가 어떻게 되나요?"
    history_list = [
        {"id": 1, "summary": "개인정보 처리방침 수립 절차 문의"},
        {"id": 2, "summary": "ISMS-P 인증 취득 요건 확인"},
    ]

    print(f"\n자문 요청: {user_query}")
    print("Claude API 호출 중 (tool_use 루프)...\n")

    result = generate_advisory(
        template=template,
        env_context=env_context,
        user_query=user_query,
        history_list=history_list,
        history_mode="ON",
    )

    print(f"[summary]\n{result.get('summary')}\n")

    laws = result.get("applicable_laws", [])
    print(f"[applicable_laws] {len(laws)}개")
    for law in laws[:3]:
        print(f"  - {law.get('law_name')} {law.get('article')}")

    precs = result.get("precedents", [])
    print(f"\n[precedents] {len(precs)}개")
    for p in precs[:3]:
        print(f"  - {p.get('case_no')}: {p.get('summary', '')[:80]}")

    print(f"\n[conclusion]\n{result.get('conclusion', '')[:400]}")

    if has_gray_area(result):
        print(f"\n{format_gray_area_text(result)}")
    else:
        print("\n[gray_areas] 없음")

    if is_blocked(result):
        print("⛔ Case 8: 관련 법령 없음 — conclusion 생성 중단")

    print(f"\n[similar_history] {result.get('similar_history')}")

    print("\n✅ generate_advisory 테스트 완료")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Phase 3 테스트")
    parser.add_argument("--step", choices=["rag", "mcp", "advisory", "all"], default="all")
    args = parser.parse_args()

    if args.step in ("rag", "all"):
        test_rag_search()

    if args.step in ("mcp", "all"):
        test_search_decisions()

    if args.step in ("advisory", "all"):
        test_generate_advisory()

    print("\n\n모든 테스트 완료")
