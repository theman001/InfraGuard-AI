"""
test/test_integration.py — Phase 4 통합 테스트

테스트 순서:
  1. DB 초기화 + 테스트 유저 생성
  2. API 키 암호화 저장/복호화 조회
  3. 템플릿 CRUD (생성 → 수정 → 삭제)
  4. 자문 생성 전체 흐름 (generate_advisory + debug_logger)
  5. 보고서 저장 → 목록 조회 → 상세 조회
  6. similar_history 링크 유효성 확인
  7. 보고서 삭제 확인

실행:
  python test/test_integration.py
  python test/test_integration.py --step db
  python test/test_integration.py --step keys
  python test/test_integration.py --step template
  python test/test_integration.py --step advisory
  python test/test_integration.py --step report
  python test/test_integration.py --step all
"""

import io
import json
import os
import sys
import traceback

# Windows 콘솔 UTF-8 강제
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))


# ─────────────────────────────────────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────────────────────────────────────

_PASS = "✅"
_FAIL = "❌"
_results: list[tuple[str, bool, str]] = []


def section(title: str):
    print(f"\n{'=' * 65}")
    print(f"  {title}")
    print(f"{'=' * 65}")


def ok(label: str, detail: str = ""):
    msg = f"  {_PASS} {label}"
    if detail:
        msg += f"  → {detail}"
    print(msg)
    _results.append((label, True, detail))


def fail(label: str, detail: str = ""):
    msg = f"  {_FAIL} {label}"
    if detail:
        msg += f"  → {detail}"
    print(msg)
    _results.append((label, False, detail))


def assert_true(cond: bool, label: str, detail: str = ""):
    if cond:
        ok(label, detail)
    else:
        fail(label, detail)
    return cond


def summary():
    section("테스트 결과 요약")
    passed = sum(1 for _, r, _ in _results if r)
    total  = len(_results)
    for label, result, detail in _results:
        icon = _PASS if result else _FAIL
        d = f"  ({detail})" if detail else ""
        print(f"  {icon} {label}{d}")
    print(f"\n  합계: {passed}/{total} 통과")
    return passed == total


# ─────────────────────────────────────────────────────────────────────────────
# 1. DB 초기화 + 테스트 유저
# ─────────────────────────────────────────────────────────────────────────────

_TEST_USERNAME = "_test_integration_user"
_TEST_USER_ID  = None   # 생성 후 채워짐


def test_db():
    global _TEST_USER_ID
    section("1. DB 초기화 + 테스트 유저")

    try:
        from core.db import init_db, get_conn
        init_db()
        ok("init_db() 정상 실행")
    except Exception as e:
        fail("init_db() 실패", str(e))
        return False

    # 테스트 유저 생성 (이미 있으면 재사용)
    try:
        from core.db import get_conn
        with get_conn() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE username = ?", (_TEST_USERNAME,)
            ).fetchone()
            if row:
                _TEST_USER_ID = row[0]
                ok("테스트 유저 재사용", f"id={_TEST_USER_ID}")
            else:
                conn.execute(
                    "INSERT INTO users (username, role, status, totp_secret, totp_enabled) "
                    "VALUES (?, 'user', 'active', 'TESTSECRET', 1)",
                    (_TEST_USERNAME,)
                )
                conn.commit()
                _TEST_USER_ID = conn.execute(
                    "SELECT id FROM users WHERE username = ?", (_TEST_USERNAME,)
                ).fetchone()[0]
                ok("테스트 유저 생성", f"id={_TEST_USER_ID}")
    except Exception as e:
        fail("테스트 유저 생성 실패", str(e))
        traceback.print_exc()
        return False

    return True


# ─────────────────────────────────────────────────────────────────────────────
# 2. API 키 암호화 저장/복호화
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_test_user():
    """_TEST_USER_ID가 None이면 DB에서 찾거나 생성."""
    global _TEST_USER_ID
    if _TEST_USER_ID is not None:
        return True
    try:
        from core.db import get_conn, init_db
        init_db()
        with get_conn() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE username = ?", (_TEST_USERNAME,)
            ).fetchone()
            if row:
                _TEST_USER_ID = row[0]
            else:
                conn.execute(
                    "INSERT INTO users (username, role, status, totp_secret, totp_enabled) "
                    "VALUES (?, 'user', 'active', 'TESTSECRET', 1)",
                    (_TEST_USERNAME,)
                )
                conn.commit()
                _TEST_USER_ID = conn.execute(
                    "SELECT id FROM users WHERE username = ?", (_TEST_USERNAME,)
                ).fetchone()[0]
        return True
    except Exception as e:
        fail("테스트 유저 초기화 실패", str(e))
        return False


def test_api_keys():
    section("2. API 키 암호화 저장/복호화")

    try:
        from core.crypto import encrypt_key, decrypt_key, is_encrypted
        plain = "sk-ant-api03-test-key-1234"
        enc = encrypt_key(plain)
        assert_true(is_encrypted(enc), "encrypt_key → Fernet 형식", enc[:20] + "...")
        dec = decrypt_key(enc)
        assert_true(dec == plain, "decrypt_key → 원문 복원", dec)
        assert_true(decrypt_key("") == "", "decrypt_key('') → 빈 문자열")
    except Exception as e:
        fail("crypto 모듈 오류", str(e))
        return False

    if not _ensure_test_user():
        return False

    try:
        from core.models import update_user_api_keys, get_user_api_keys
        update_user_api_keys(_TEST_USER_ID,
                             law_api_key="theman",
                             llm_api_key=os.environ.get("CLAUDE_API_KEY", ""))
        keys = get_user_api_keys(_TEST_USER_ID)
        assert_true(keys["law_api_key"] == "theman", "law_api_key 저장/복호화")
        has_llm = bool(keys["llm_api_key"])
        assert_true(has_llm, "llm_api_key 저장/복호화", "●●●●" if has_llm else "비어있음")
    except Exception as e:
        fail("update/get_user_api_keys 오류", str(e))
        traceback.print_exc()
        return False

    return True


# ─────────────────────────────────────────────────────────────────────────────
# 3. 템플릿 CRUD
# ─────────────────────────────────────────────────────────────────────────────

_TEST_TEMPLATE_ID = None


def test_template():
    global _TEST_TEMPLATE_ID
    section("3. 템플릿 CRUD")

    if not _ensure_test_user():
        return False

    try:
        from core.models import (
            create_template, get_templates_by_user,
            get_template_by_id, update_template, delete_template,
        )

        items = json.dumps({
            "size":    {"value": "중소기업",      "enabled": True},
            "sector":  {"value": "IT/소프트웨어", "enabled": True},
            "cert":    {"value": "ISMS-P",        "enabled": True},
            "privacy": {"value": "처리",           "enabled": True},
            "employees":{"value": "51~300명",     "enabled": True},
        }, ensure_ascii=False)

        # 생성
        create_template(_TEST_USER_ID, "_통합테스트_템플릿", items)
        templates = get_templates_by_user(_TEST_USER_ID)
        tpl = next((t for t in templates if t["template_name"] == "_통합테스트_템플릿"), None)
        assert_true(tpl is not None, "create_template 생성 확인")
        if not tpl:
            return False
        _TEST_TEMPLATE_ID = tpl["id"]

        # 단건 조회
        fetched = get_template_by_id(_TEST_TEMPLATE_ID)
        assert_true(fetched is not None, "get_template_by_id", f"id={_TEST_TEMPLATE_ID}")

        # 수정
        updated_items = json.loads(items)
        updated_items["employees"]["value"] = "300명 초과"
        update_template(_TEST_TEMPLATE_ID,
                        template_name="_통합테스트_템플릿_수정",
                        items=json.dumps(updated_items, ensure_ascii=False))
        after = get_template_by_id(_TEST_TEMPLATE_ID)
        after_items = json.loads(after["items"])
        assert_true(
            after["template_name"] == "_통합테스트_템플릿_수정",
            "update_template 이름 수정"
        )
        assert_true(
            after_items["employees"]["value"] == "300명 초과",
            "update_template 항목 수정"
        )

        ok("템플릿 CRUD 완료", f"id={_TEST_TEMPLATE_ID}")
    except Exception as e:
        fail("템플릿 CRUD 오류", str(e))
        traceback.print_exc()
        return False

    return True


# ─────────────────────────────────────────────────────────────────────────────
# 4. generate_advisory() 전체 흐름
# ─────────────────────────────────────────────────────────────────────────────

_ADVISORY_RESULT = None


def test_advisory():
    global _ADVISORY_RESULT
    section("4. generate_advisory() + debug_logger")

    if not _ensure_test_user():
        return False

    # prompts/ 파일 존재 확인
    try:
        from core.advisor.prompt_builder import load_prompt, load_tools
        sys_prompt = load_prompt("system_prompt.md")
        assert_true(len(sys_prompt) > 100, "system_prompt.md 로드", f"{len(sys_prompt)} chars")

        tools = load_tools("rag_search.json", "search_decisions.json", "get_decision_text.json")
        assert_true(len(tools) == 3, "툴 정의 3개 로드")
        last_tool = tools[-1]
        assert_true(
            "cache_control" in last_tool,
            "마지막 tool에 cache_control 부착",
            last_tool.get("name")
        )
    except Exception as e:
        fail("prompts/ 파일 로드 오류", str(e))
        return False

    # API 키 가져오기
    try:
        from core.models import get_user_api_keys
        keys = get_user_api_keys(_TEST_USER_ID)
        claude_key = keys["llm_api_key"]
        law_key    = keys["law_api_key"]
        if not claude_key:
            fail("LLM API 키 미등록 — 자문 테스트 건너뜀")
            return False
    except Exception as e:
        fail("API 키 조회 오류", str(e))
        return False

    # 자문 실행
    try:
        from core.advisor.claude_client import generate_advisory

        template = {
            "size":      "중소기업",
            "sector":    "IT/소프트웨어",
            "cert":      "ISMS-P",
            "privacy":   "처리",
            "employees": "80명",
        }
        env_context = "사무실 내 직원 출입 관리를 위해 CCTV 8대를 신규 설치할 예정입니다."
        user_query  = "CCTV 설치 시 개인정보 처리방침 고지 의무와 직원 동의 절차가 어떻게 되나요?"

        print(f"\n  [요청] {user_query}")
        print("  Claude API 호출 중... (30초~2분 소요)\n")

        result = generate_advisory(
            template=template,
            env_context=env_context,
            user_query=user_query,
            history_list=[],
            history_mode="OFF",
            claude_api_key=claude_key,
            law_api_key=law_key,
        )
        _ADVISORY_RESULT = result

        required = {"summary", "applicable_laws", "precedents", "conclusion",
                    "gray_areas", "similar_history"}
        has_keys = required.issubset(result.keys())
        assert_true(has_keys, "응답 필수 키 6개 포함")
        assert_true(bool(result.get("summary")), "summary 비어있지 않음", result.get("summary", "")[:60])
        assert_true(isinstance(result.get("applicable_laws"), list), "applicable_laws 리스트")
        assert_true(isinstance(result.get("precedents"), list), "precedents 리스트")
        assert_true(bool(result.get("conclusion")), "conclusion 비어있지 않음")
        assert_true(isinstance(result.get("gray_areas"), list), "gray_areas 리스트")
        assert_true(isinstance(result.get("similar_history"), list), "similar_history 리스트")

        # debug log 파일 생성 확인
        import time; time.sleep(0.3)
        log_path = os.path.join(ROOT, "data", "claude_debug.jsonl")
        assert_true(os.path.exists(log_path), "debug_logger JSONL 파일 생성됨", log_path)
        if os.path.exists(log_path):
            with open(log_path, encoding="utf-8") as f:
                lines = f.readlines()
            last = json.loads(lines[-1])
            assert_true(last.get("status") == "success", "debug 세션 status=success")
            assert_true(last.get("total_iterations", 0) >= 1, "iterations 기록",
                        f"{last.get('total_iterations')}회")
            assert_true(last.get("total_input_tokens", 0) > 0, "input_tokens 기록",
                        f"{last.get('total_input_tokens'):,}")
            cache_read = last.get("total_cache_read", 0)
            print(f"  ℹ️  cache_read={cache_read:,} tokens "
                  f"({'캐시 히트' if cache_read > 0 else '캐시 미스 (첫 요청 정상)'})")

        print(f"\n  [summary] {result.get('summary', '')[:80]}")
        laws = result.get("applicable_laws", [])
        print(f"  [applicable_laws] {len(laws)}개")
        for law in laws[:2]:
            print(f"    - {law.get('law_name')} {law.get('article')}")
        precs = result.get("precedents", [])
        print(f"  [precedents] {len(precs)}개")
        for p in precs[:2]:
            print(f"    - {p.get('case_no')}")

    except Exception as e:
        fail("generate_advisory 실패", str(e))
        traceback.print_exc()
        return False

    return True


# ─────────────────────────────────────────────────────────────────────────────
# 5. 보고서 저장 → 목록 → 상세 → similar_history 유효성
# ─────────────────────────────────────────────────────────────────────────────

_SAVED_REPORT_ID = None


def test_report():
    global _SAVED_REPORT_ID
    section("5. 보고서 저장 → 조회 → similar_history")

    if not _ensure_test_user():
        return False

    if _ADVISORY_RESULT is None:
        fail("자문 결과 없음 — advisory 테스트를 먼저 실행하세요")
        return False

    try:
        from core.models import (
            create_report, get_reports_by_user,
            get_report_by_id, delete_report,
        )

        result = _ADVISORY_RESULT
        prompt_text = "[현재 상황]\nCCTV 8대 신규 설치\n\n[자문 요청]\n고지 의무 및 동의 절차"

        # 저장
        create_report(
            user_id=_TEST_USER_ID,
            template_id=_TEST_TEMPLATE_ID,
            template_snapshot=json.dumps({
                "sector": {"value": "IT/소프트웨어", "enabled": True}
            }, ensure_ascii=False),
            summary=result.get("summary", ""),
            prompt=prompt_text,
            result=json.dumps(result, ensure_ascii=False),
        )

        # 목록 조회
        reports = get_reports_by_user(_TEST_USER_ID)
        assert_true(len(reports) >= 1, "보고서 목록 1건 이상")
        latest = reports[-1]
        _SAVED_REPORT_ID = latest["id"]
        assert_true(bool(latest["summary"]), "summary 저장됨", latest["summary"][:50])

        # 상세 조회
        detail = get_report_by_id(_SAVED_REPORT_ID)
        assert_true(detail is not None, "get_report_by_id 조회")
        parsed = json.loads(detail["result"])
        assert_true("summary" in parsed, "result JSON 파싱 가능")

        # similar_history 유효성: 참조 ID가 실제 보고서 목록에 있는지 확인
        similar_ids = parsed.get("similar_history", [])
        report_ids = {r["id"] for r in reports}
        dangling = [i for i in similar_ids if i not in report_ids]
        if dangling:
            print(f"  ℹ️  similar_history에 존재하지 않는 ID: {dangling} (이력 없을 때 정상)")
        else:
            ok("similar_history 참조 ID 모두 유효")

        # 보고서 삭제
        delete_report(_SAVED_REPORT_ID)
        after_del = get_report_by_id(_SAVED_REPORT_ID)
        assert_true(after_del is None, "delete_report 삭제 확인")

    except Exception as e:
        fail("보고서 CRUD 오류", str(e))
        traceback.print_exc()
        return False

    return True


# ─────────────────────────────────────────────────────────────────────────────
# 6. 템플릿 삭제 (보고서 유지 확인)
# ─────────────────────────────────────────────────────────────────────────────

def test_template_delete():
    section("6. 템플릿 삭제 (보고서 유지 확인)")

    if not _ensure_test_user():
        return False

    if _TEST_TEMPLATE_ID is None:
        fail("템플릿 ID 없음 — template 테스트를 먼저 실행하세요")
        return False

    try:
        from core.models import (
            create_report, get_reports_by_user,
            delete_template, get_template_by_id,
        )

        # 보고서 1건 생성 후 템플릿만 삭제 → 보고서 유지 확인
        create_report(
            user_id=_TEST_USER_ID,
            template_id=_TEST_TEMPLATE_ID,
            template_snapshot="{}",
            summary="삭제 테스트용 보고서",
            prompt="테스트",
            result='{"summary":"테스트","applicable_laws":[],"precedents":[],"conclusion":"","gray_areas":[],"similar_history":[]}',
        )
        before = get_reports_by_user(_TEST_USER_ID)
        before_count = len(before)

        # 템플릿만 삭제 (delete_reports=False)
        delete_template(_TEST_TEMPLATE_ID, delete_reports=False)
        assert_true(get_template_by_id(_TEST_TEMPLATE_ID) is None, "템플릿 삭제됨")

        after = get_reports_by_user(_TEST_USER_ID)
        assert_true(len(after) == before_count, "보고서는 유지됨 (템플릿만 삭제)", f"{len(after)}건")

        # 테스트 보고서 정리
        for r in after:
            if r["summary"] == "삭제 테스트용 보고서":
                from core.models import delete_report
                delete_report(r["id"])
        ok("테스트 데이터 정리 완료")

    except Exception as e:
        fail("템플릿 삭제 테스트 오류", str(e))
        traceback.print_exc()
        return False

    return True


# ─────────────────────────────────────────────────────────────────────────────
# 7. 테스트 유저 정리
# ─────────────────────────────────────────────────────────────────────────────

def cleanup():
    section("7. 테스트 데이터 정리")
    try:
        from core.db import get_conn
        with get_conn() as conn:
            # 테스트 유저의 보고서 정리
            conn.execute(
                "DELETE FROM reports WHERE user_id = ?", (_TEST_USER_ID,)
            )
            # 테스트 유저의 템플릿 정리
            conn.execute(
                "DELETE FROM templates WHERE user_id = ?", (_TEST_USER_ID,)
            )
            # 테스트 유저 삭제
            conn.execute(
                "DELETE FROM users WHERE username = ?", (_TEST_USERNAME,)
            )
            conn.commit()
        ok("테스트 유저 + 관련 데이터 삭제")
    except Exception as e:
        fail("정리 실패", str(e))


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Phase 4 통합 테스트")
    parser.add_argument(
        "--step",
        choices=["db", "keys", "template", "advisory", "report", "all"],
        default="all",
    )
    args = parser.parse_args()

    step = args.step

    if step in ("db", "all"):
        if not test_db():
            print("\n[중단] DB 초기화 실패 — 이후 테스트 불가")
            sys.exit(1)

    if step in ("keys", "all"):
        test_api_keys()

    if step in ("template", "all"):
        test_template()

    if step in ("advisory", "all"):
        test_advisory()

    if step in ("report", "all"):
        test_report()

    if step == "all":
        test_template_delete()
        cleanup()

    all_passed = summary()
    sys.exit(0 if all_passed else 1)
