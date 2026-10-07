"""Portable ARQ entry point, including Windows shutdown support."""

import asyncio
import signal
import sys

from arq.worker import Worker

from app.workers.settings import WorkerSettings


class OrchestratorWorker(Worker):
    async def close(self) -> None:
        if sys.platform == "win32" and not self._handle_signals:
            # ARQ 0.26 uses SIGUSR1 for programmatic shutdown, unavailable on Windows.
            self.handle_sig(signal.SIGTERM)
            self._handle_signals = True
        await super().close()


async def main() -> None:
    worker = OrchestratorWorker(
        functions=WorkerSettings.functions,
        redis_settings=WorkerSettings.redis_settings,
        cron_jobs=WorkerSettings.cron_jobs,
        job_timeout=WorkerSettings.job_timeout,
        keep_result=WorkerSettings.keep_result,
        handle_signals=sys.platform != "win32",
    )
    try:
        await worker.async_run()
    finally:
        await worker.close()


if __name__ == "__main__":
    asyncio.run(main())
