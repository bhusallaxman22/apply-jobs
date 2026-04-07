from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LiveRunSession:
    run_id: str
    mode: str
    resume_event: asyncio.Event = field(default_factory=asyncio.Event)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    created_at: str = field(default_factory=utc_now_iso)
    last_signal_at: str | None = None


_LIVE_RUN_SESSIONS: dict[str, LiveRunSession] = {}


def register_live_run(run_id: str, mode: str) -> LiveRunSession:
    session = LiveRunSession(run_id=run_id, mode=mode)
    _LIVE_RUN_SESSIONS[run_id] = session
    return session


def get_live_run(run_id: str) -> LiveRunSession | None:
    return _LIVE_RUN_SESSIONS.get(run_id)


def clear_live_run(run_id: str) -> None:
    _LIVE_RUN_SESSIONS.pop(run_id, None)


def signal_live_run_resume(run_id: str) -> bool:
    session = _LIVE_RUN_SESSIONS.get(run_id)
    if session is None:
        return False
    session.last_signal_at = utc_now_iso()
    session.resume_event.set()
    return True


def reset_live_run_resume(run_id: str) -> None:
    session = _LIVE_RUN_SESSIONS.get(run_id)
    if session is None:
        return
    session.resume_event.clear()


def signal_live_run_cancel(run_id: str) -> bool:
    session = _LIVE_RUN_SESSIONS.get(run_id)
    if session is None:
        return False
    session.last_signal_at = utc_now_iso()
    session.cancel_event.set()
    return True
