"""
test_laws.py — 계획된 법령 목록 vs 실제 국가법령 API 검증

각 법령에 대해:
1. lawSearch.do로 검색 → MST ID, 법령명, 시행일자 확인
2. 결과 없거나 이름 불일치 시 플래그 표시
"""

import requests
import urllib.parse
import time
from bs4 import BeautifulSoup

OC_ID = "theman"
LAW_SEARCH_URL = "http://www.law.go.kr/DRF/lawSearch.do"
LAW_SERVICE_URL = "http://www.law.go.kr/DRF/lawService.do"


PLANNED_LAWS = [
    # ── 기본 공통 ──────────────────────────────────────────────────────
    {"name": "개인정보 보호법",                                  "category": "공통",     "sector": None},
    {"name": "정보통신망 이용촉진 및 정보보호 등에 관한 법률",   "category": "공통",     "sector": None},
    {"name": "산업기술의 유출방지 및 보호에 관한 법률",          "category": "공통",     "sector": None},
    {"name": "근로기준법",                                        "category": "공통",     "sector": None},
    {"name": "상법",                                              "category": "공통",     "sector": None},
    {"name": "전자문서 및 전자거래 기본법",                       "category": "공통",     "sector": None},
    {"name": "사이버보안 기본법",                                 "category": "공통",     "sector": None},
    {"name": "정보통신기반 보호법",                               "category": "공통",     "sector": None},
    {"name": "클라우드컴퓨팅 발전 및 이용자 보호에 관한 법률",   "category": "공통",     "sector": None},
    {"name": "전기통신사업법",                                    "category": "공통",     "sector": None},
    {"name": "경비업법",                                          "category": "공통",     "sector": None},
    {"name": "소방시설 설치 및 관리에 관한 법률",                "category": "공통",     "sector": None},
    {"name": "화재의 예방 및 안전관리에 관한 법률",              "category": "공통",     "sector": None},
    {"name": "재난 및 안전관리 기본법",                          "category": "공통",     "sector": None},
    # ── 업종별 ────────────────────────────────────────────────────────
    {"name": "전자금융거래법",                                    "category": "업종별",   "sector": "금융/핀테크"},
    {"name": "신용정보의 이용 및 보호에 관한 법률",              "category": "업종별",   "sector": "금융/핀테크"},
    {"name": "금융실명거래 및 비밀보장에 관한 법률",             "category": "업종별",   "sector": "금융/핀테크"},
    {"name": "의료법",                                            "category": "업종별",   "sector": "의료/헬스케어"},
    {"name": "의료기기법",                                        "category": "업종별",   "sector": "의료/헬스케어"},
    {"name": "생명윤리 및 안전에 관한 법률",                     "category": "업종별",   "sector": "의료/헬스케어"},
    {"name": "산업안전보건법",                                    "category": "업종별",   "sector": "제조"},
    {"name": "중대재해 처벌 등에 관한 법률",                     "category": "업종별",   "sector": "제조"},
    {"name": "국가정보보안 기본지침",                             "category": "업종별",   "sector": "공공/공급망"},
    {"name": "소프트웨어 진흥법",                                 "category": "업종별",   "sector": "공공/공급망"},
    {"name": "전자상거래 등에서의 소비자보호에 관한 법률",       "category": "업종별",   "sector": "유통/이커머스"},
    {"name": "표시·광고의 공정화에 관한 법률",                   "category": "업종별",   "sector": "유통/이커머스"},
    # ── 인증별 ────────────────────────────────────────────────────────
    {"name": "개인정보 보호법 시행령",                            "category": "인증별",   "sector": "ISMS-P"},
    {"name": "개인정보 보호법 시행규칙",                          "category": "인증별",   "sector": "ISMS-P"},
    {"name": "정보통신망 이용촉진 및 정보보호 등에 관한 법률 시행령", "category": "인증별", "sector": "ISMS-P"},
]


def search_law(name: str) -> list[dict]:
    """법령명으로 검색 → 결과 목록 반환"""
    encoded = urllib.parse.quote(name)
    url = f"{LAW_SEARCH_URL}?OC={OC_ID}&target=law&query={encoded}&type=XML&display=5"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.content, "lxml-xml")
    results = []
    for law in soup.find_all("law"):
        mst_tag    = law.find("법령일련번호")
        name_tag   = law.find("법령명한글")
        date_tag   = law.find("시행일자")
        type_tag   = law.find("법령구분명")
        results.append({
            "mst_id":         mst_tag.text.strip()  if mst_tag   else "",
            "law_name":       name_tag.text.strip()  if name_tag  else "",
            "effective_date": date_tag.text.strip()  if date_tag  else "",
            "law_type":       type_tag.text.strip()  if type_tag  else "",
        })
    return results


def get_article_count(mst_id: str) -> int:
    """MST ID로 조문 수 조회"""
    url = f"{LAW_SERVICE_URL}?OC={OC_ID}&target=law&MST={mst_id}&type=XML"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "lxml-xml")
    return len(soup.find_all("조문단위"))


def run():
    print("=" * 70)
    print("국가법령 API 검증 테스트")
    print("=" * 70)

    found     = []
    not_found = []
    warnings  = []

    for entry in PLANNED_LAWS:
        planned_name = entry["name"]
        category     = entry["category"]
        sector       = entry["sector"] or "-"

        print(f"\n[검색] {planned_name} ({category} / {sector})")
        time.sleep(0.3)  # API 부하 방지

        try:
            results = search_law(planned_name)
        except Exception as e:
            print(f"  ❌ API 오류: {e}")
            not_found.append({**entry, "reason": f"API 오류: {e}", "mst_id": ""})
            continue

        if not results:
            print(f"  ❌ 검색 결과 없음")
            not_found.append({**entry, "reason": "검색 결과 0건", "mst_id": ""})
            continue

        top = results[0]
        actual_name = top["law_name"]
        mst_id      = top["mst_id"]
        eff_date    = top["effective_date"]
        law_type    = top["law_type"]

        # 이름 일치 여부 (공백 제거 후 비교)
        name_match = planned_name.replace(" ", "") in actual_name.replace(" ", "") or \
                     actual_name.replace(" ", "") in planned_name.replace(" ", "")

        if name_match:
            print(f"  ✅ 매칭: {actual_name}")
            print(f"     MST={mst_id} | 시행일={eff_date} | 구분={law_type}")
            found.append({
                **entry,
                "actual_name":    actual_name,
                "mst_id":         mst_id,
                "effective_date": eff_date,
                "law_type":       law_type,
            })
        else:
            print(f"  ⚠️  이름 불일치")
            print(f"     계획: {planned_name}")
            print(f"     실제: {actual_name}  (MST={mst_id})")
            warnings.append({
                **entry,
                "actual_name":    actual_name,
                "mst_id":         mst_id,
                "effective_date": eff_date,
                "law_type":       law_type,
                "reason":         f"이름 불일치: '{planned_name}' → '{actual_name}'",
            })

    # ── 최종 요약 ──────────────────────────────────────────────────────
    total = len(PLANNED_LAWS)
    print("\n" + "=" * 70)
    print(f"검증 완료: 총 {total}개 법령")
    print(f"  ✅ 정상 매칭 : {len(found)}개")
    print(f"  ⚠️  이름 불일치 : {len(warnings)}개")
    print(f"  ❌ 검색 실패  : {len(not_found)}개")

    if warnings:
        print("\n[이름 불일치 목록]")
        for w in warnings:
            print(f"  - 계획: {w['name']}")
            print(f"    실제: {w['actual_name']} (MST={w['mst_id']})")

    if not_found:
        print("\n[검색 실패 목록]")
        for n in not_found:
            print(f"  - {n['name']} ({n['reason']})")

    print("\n[정상 매칭 법령 MST 목록]")
    for f in found:
        sector_str = f"({f['sector']})" if f['sector'] else ""
        print(f"  {f['actual_name']:45s}  MST={f['mst_id']}  {f['effective_date']}  {sector_str}")

    return found, warnings, not_found


if __name__ == "__main__":
    run()
