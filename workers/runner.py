from __future__ import annotations

import asyncio
import signal

from backend.app.config import settings
from backend.app.database import dispose_db, init_db
from workers.generation_worker import GenerationWorker


async def main() -> None:
    if settings.auto_create_schema:
        await init_db()
    worker = GenerationWorker()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, worker.stop)
        except NotImplementedError:  # pragma: no cover - Windows event loop
            pass
    try:
        await worker.run_forever()
    finally:
        await dispose_db()


if __name__ == "__main__":
    asyncio.run(main())
