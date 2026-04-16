"""
core/rag/collector.py — 국가법령 API 조문 수집

- MST ID 직접 조회 방식 (lawService.do)
- 반환: 조문 XML soup + 시행일자 (변경 감지용)
"""

import os
import time

import requests
from bs4 import BeautifulSoup

LAW_SERVICE_URL = "http://www.law.go.kr/DRF/lawService.do"
OC_ID = os.environ.get("LAW_OC_ID", "theman")
REQUEST_INTERVAL = 0.3   # API 요청 간 최소 간격(초)
TIMEOUT = 30
MAX_RETRY = 3


def fetch_law_xml(mst_id: str) -> tuple[BeautifulSoup, str]:
    """
    단일 법령 조문 XML을 가져온다.

    Returns:
        (soup, effective_date)
        effective_date: "YYYYMMDD" 형식 시행일자. 없으면 빈 문자열.

    Raises:
        requests.HTTPError: HTTP 오류 시
        ValueError: XML 파싱 실패 또는 조문 없을 시
    """
    url = f"{LAW_SERVICE_URL}?OC={OC_ID}&target=law&MST={mst_id}&type=XML"

    for attempt in range(1, MAX_RETRY + 1):
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            break
        except requests.RequestException as e:
            if attempt == MAX_RETRY:
                raise
            wait = attempt * 2
            print(f"  [collector] 재시도 {attempt}/{MAX_RETRY} (MST={mst_id}): {e} — {wait}s 대기")
            time.sleep(wait)

    soup = BeautifulSoup(resp.content, "lxml-xml")

    # 조문 존재 여부 확인
    if not soup.find("조문단위"):
        raise ValueError(f"MST={mst_id}: 조문 데이터 없음 (인증키 또는 MST 확인 필요)")

    # 시행일자 추출 — 법령 수준의 시행일자 (첫 번째 조문 기준)
    effective_date = ""
    date_tag = soup.find("시행일자")
    if date_tag:
        effective_date = date_tag.text.strip()

    time.sleep(REQUEST_INTERVAL)
    return soup, effective_date


def get_law_name_from_xml(soup: BeautifulSoup) -> str:
    """XML에서 법령명 추출"""
    tag = soup.find("법령명한글")
    return tag.text.strip() if tag else ""
