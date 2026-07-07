"""
Entry point for the Docker scheduler container.
Runs the weekly report scheduler continuously.
"""

import asyncio
import os
import signal
import sys

from app.services.scheduler import WeeklyReportScheduler


async def main():
    """Start the scheduler and keep it running."""
    scheduler = WeeklyReportScheduler()

    day = os.environ.get("SCHEDULE_DAY", "mon")
    hour = int(os.environ.get("SCHEDULE_HOUR", "8"))
    minute = int(os.environ.get("SCHEDULE_MINUTE", "0"))

    print(f"Starting Neuronal SEO scheduler: every {day} at {hour:02d}:{minute:02d} UTC")
    scheduler.start(day_of_week=day, hour=hour, minute=minute)

    # Keep the event loop running
    stop_event = asyncio.Event()

    def handle_signal(sig, frame):
        print("Shutting down scheduler...")
        scheduler.stop()
        stop_event.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    await stop_event.wait()


if __name__ == "__main__":
    asyncio.run(main())
