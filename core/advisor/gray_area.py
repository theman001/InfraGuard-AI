"""
core/advisor/gray_area.py — 회색지대 판단 결과 파싱 헬퍼

System Prompt의 Case 4~8 처리 결과를 UI에서 사용하기 편하게 가공.
"""


def has_gray_area(result: dict) -> bool:
    """gray_areas 리스트가 비어있지 않으면 True."""
    return bool(result.get("gray_areas"))


def format_gray_area_text(result: dict) -> str:
    """
    gray_areas 항목을 화면 표시용 문자열로 변환.

    예:
        "⚠️ 회색지대 주의사항:\n• 두 법령의 우선순위 원칙이 충돌합니다.\n• 관련 판례가 없는 신규 영역입니다."
    """
    areas: list[str] = result.get("gray_areas", [])
    if not areas:
        return ""

    lines = ["⚠️ 회색지대 주의사항:"]
    for area in areas:
        lines.append(f"• {area}")
    return "\n".join(lines)


def is_blocked(result: dict) -> bool:
    """
    Case 8 (관련 법령 없음) 에 해당하면 True.
    conclusion 생성이 중단된 케이스 감지용.
    """
    areas: list[str] = result.get("gray_areas", [])
    for area in areas:
        if "법령을 찾지 못" in area or "Case 8" in area or "관련 법령 없음" in area:
            return True
    return False
