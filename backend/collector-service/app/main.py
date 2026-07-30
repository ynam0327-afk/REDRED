import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import settings
from .fetchers import fetch_all_datasets

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("collector-service 시작. 폴링 주기=%d초", settings.poll_interval_seconds)

    # 기동 즉시 1회 실행 (스케줄 첫 사이클까지 기다리지 않도록)
    await fetch_all_datasets()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(fetch_all_datasets, "interval", seconds=settings.poll_interval_seconds)
    scheduler.start()

    # 컨테이너가 종료되지 않도록 유지
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
