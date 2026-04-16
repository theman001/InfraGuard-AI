"""
core/rag/scheduler.py — APScheduler 기반 법령 자동 업데이트

스케줄: 매월 1일 02:00
동작:
  1. law_registry에서 is_active=1 법령 목록 조회 (DB 기준 — 사용자 수정 반영)
  2. 각 법령 API 조회 → 시행일자 확인
  3. last_effective_date와 다르면 → sync_law_chunks로 법령 단위 증분 동기화
     (추가된 조문만 insert, 변경된 조문만 update, 삭제된 조문만 delete)
  4. last_effective_date 갱신
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from core.models import get_all_laws, update_effective_date
from core.rag.collector import fetch_law_xml, get_law_name_from_xml
from core.rag.chunker import parse_chunks
# chroma_store는 실제 동기화 시점에 지연 임포트 (sentence-transformers 로딩 방지)

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def sync_laws(force_all: bool = False) -> dict:
    """
    법령 동기화 실행.

    Args:
        force_all: True면 시행일자 무관하게 전체 재수집

    Returns:
        {"updated": [...], "skipped": [...], "failed": [...]}
    """
    laws = get_all_laws(active_only=True)
    result = {"updated": [], "skipped": [], "failed": []}

    logger.info(f"[scheduler] 동기화 시작 — {len(laws)}개 법령 (force_all={force_all})")

    for entry in laws:
        try:
            soup, effective_date = fetch_law_xml(entry.mst_id)

            # 변경 감지: 시행일자가 동일하면 스킵
            if not force_all and entry.last_effective_date == effective_date:
                logger.info(f"  [skip] {entry.law_name} (시행일 동일: {effective_date})")
                result["skipped"].append(entry.law_name)
                continue

            # 변경 감지됨 → 증분 동기화
            law_name = get_law_name_from_xml(soup) or entry.law_name
            logger.info(f"  [update] {law_name} ({entry.last_effective_date} → {effective_date})")

            # 새 청크 파싱
            chunks = parse_chunks(
                soup          = soup,
                mst_id        = entry.mst_id,
                law_name      = law_name,
                law_type      = entry.law_type or "",
                effective_date= effective_date,
                category      = entry.category,
                sector        = entry.sector,
                cert          = entry.cert,
            )

            # 법령 단위 증분 동기화 (추가/수정/삭제 조문만 처리)
            from core.rag.chroma_store import sync_law_chunks  # 지연 임포트
            sync_result = sync_law_chunks(entry.mst_id, chunks)

            # DB 시행일자 갱신
            update_effective_date(entry.mst_id, effective_date)

            logger.info(
                f"    추가 {sync_result['inserted']}개 / "
                f"수정 {sync_result['updated']}개 / "
                f"삭제 {sync_result['deleted']}개 / "
                f"유지 {sync_result['unchanged']}개"
            )
            result["updated"].append(entry.law_name)

        except Exception as e:
            logger.error(f"  [error] {entry.law_name} (MST={entry.mst_id}): {e}")
            result["failed"].append({"law_name": entry.law_name, "error": str(e)})

    logger.info(
        f"[scheduler] 완료 — "
        f"업데이트 {len(result['updated'])}개 / "
        f"스킵 {len(result['skipped'])}개 / "
        f"실패 {len(result['failed'])}개"
    )
    return result


def start_scheduler() -> None:
    """앱 시작 시 호출. 매월 1일 02:00에 sync_laws 실행."""
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    _scheduler.add_job(
        func     = sync_laws,
        trigger  = CronTrigger(day=1, hour=2, minute=0, timezone="Asia/Seoul"),
        id       = "monthly_law_sync",
        name     = "월 1회 법령 자동 업데이트",
        replace_existing = True,
    )
    _scheduler.start()
    logger.info("[scheduler] 스케줄러 시작 — 매월 1일 02:00 실행")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[scheduler] 스케줄러 종료")


def get_next_run_time() -> str | None:
    """다음 실행 예정 시각 문자열 반환"""
    if not _scheduler or not _scheduler.running:
        return None
    job = _scheduler.get_job("monthly_law_sync")
    if job and job.next_run_time:
        return job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
    return None
