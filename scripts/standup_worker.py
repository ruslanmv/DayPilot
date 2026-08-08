#!/usr/bin/env python3
"""Run the Daily Standup on a schedule.

This is what turns the standup from a button into a habit. Without a process
running this loop the review job is enqueued at 18:00 and never claimed — the
draft only appears when somebody opens the page, and the next-morning reply
never happens at all.

    python scripts/standup_worker.py              # loop until interrupted
    python scripts/standup_worker.py --once       # single pass, for cron
    python scripts/standup_worker.py --interval 30

Safe to run more than once: claiming a job marks it running, and every handler
is idempotent, so a second worker picks up different work rather than repeating
it. Failures are recorded on the job with backoff, never raised into the loop —
one bad workflow must not stop everybody else's standup.
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import time

from daypilot_knowledge.db import create_engine_from_settings, session_scope
from daypilot_orchestrator.jobs import worker
from daypilot_orchestrator.standup.handlers import DELIVER, REVIEW_DUE, bootstrap_schedules, build_handlers

LOG = logging.getLogger("daypilot.standup.worker")
KINDS = [REVIEW_DUE, DELIVER]

_stop = False


def _request_stop(_signum, _frame) -> None:
    global _stop
    _stop = True
    LOG.info("stop requested — finishing the current pass")


def run_pass(engine, *, max_jobs: int = 50) -> int:
    """Claim and run every due standup job. Returns how many ran.

    One session for the pass: a crash rolls the whole pass back rather than
    leaving, say, a draft approved with no delivery job behind it.
    """
    processed = 0
    with session_scope(engine) as session:
        handlers = build_handlers(session)
        while processed < max_jobs:
            job = worker.process_once(session, handlers, kinds=KINDS)
            if job is None:
                break
            processed += 1
            LOG.info("ran %s → %s%s", job.kind, job.state,
                     f" ({job.last_error})" if job.last_error else "")
    return processed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--once", action="store_true", help="run a single pass and exit")
    parser.add_argument("--interval", type=int, default=60,
                        help="seconds between passes (default: 60)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    engine = create_engine_from_settings()

    # A deployment that was down over a review window would otherwise never
    # schedule again — the chain is self-perpetuating, so a missed link is
    # permanent until something re-arms it.
    with session_scope(engine) as session:
        rearmed = bootstrap_schedules(session)
    if rearmed:
        LOG.info("re-armed %d standup schedule(s) that had lapsed", rearmed)

    if args.once:
        LOG.info("ran %d job(s)", run_pass(engine))
        return 0

    LOG.info("standup worker started (every %ss; Ctrl+C to stop)", args.interval)
    while not _stop:
        try:
            ran = run_pass(engine)
            if ran:
                LOG.info("pass complete — %d job(s)", ran)
        except Exception:  # noqa: BLE001 - the loop outlives any single failure
            LOG.exception("pass failed; continuing")
        for _ in range(args.interval):
            if _stop:
                break
            time.sleep(1)
    LOG.info("standup worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
