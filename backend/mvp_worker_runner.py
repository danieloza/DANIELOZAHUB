import asyncio
import os
import signal

from backend.mvp_billing import start_mvp_worker, stop_mvp_worker


async def _run() -> None:
    os.environ["MVP_WORKER_ENABLED"] = "true"
    start_mvp_worker()
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    await stop_event.wait()
    await stop_mvp_worker()


if __name__ == "__main__":
    asyncio.run(_run())
