"""
Auto-scheduler for faceless video pipeline.
Uses APScheduler to run video creation jobs on a daily/custom schedule.
Schedule config is stored in scheduler_config.json.
"""
import os
import json
import asyncio
import threading
from datetime import datetime, date
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "scheduler_config.json")

_scheduler = None
_job_callback = None  # set by app.py to trigger dashboard jobs


def _default_config():
    return {
        "enabled": True,
        "schedules": [
            {
                "id": "slot_morning",
                "niche": "math_quiz",
                "count": 1,
                "hour": 9,
                "minute": 0,
                "upload": True,
                "active": True,
            },
            {
                "id": "slot_afternoon",
                "niche": "math_quiz",
                "count": 1,
                "hour": 13,
                "minute": 0,
                "upload": True,
                "active": True,
            },
            {
                "id": "slot_evening",
                "niche": "math_quiz",
                "count": 1,
                "hour": 18,
                "minute": 0,
                "upload": True,
                "active": True,
            },
        ]
    }


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                cfg = json.load(f)
            # Seed ramp_start if missing from an old config file
            if "ramp_start" not in cfg:
                cfg["ramp_start"] = date.today().isoformat()
                save_config(cfg)
            return cfg
        except Exception:
            pass
    cfg = _default_config()
    cfg["ramp_start"] = date.today().isoformat()
    save_config(cfg)  # persist defaults so dashboard shows correct state
    return cfg


def _ramp_slots(cfg: dict) -> int:
    """Return how many slots (1/2/3) should be active based on weeks since ramp_start.

    Week 1  (days 0-6):   1 upload/day  — only morning slot
    Week 2  (days 7-13):  2 uploads/day — morning + afternoon
    Week 3+ (days 14+):   3 uploads/day — all slots
    """
    try:
        start_d = date.fromisoformat(cfg.get("ramp_start", date.today().isoformat()))
        elapsed_days = (date.today() - start_d).days
    except Exception:
        elapsed_days = 14  # default to full speed if date is corrupt

    if elapsed_days < 7:
        slots = 1
    elif elapsed_days < 14:
        slots = 2
    else:
        slots = 3

    print(f"[Scheduler] Ramp day {elapsed_days} → {slots} slot(s) active")
    return slots


def save_config(config: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def _run_scheduled_job(niche: str, count: int, upload: bool):
    """Called by APScheduler — creates videos for all niches in the schedule."""
    from main import create_single_short, get_topic
    print(f"[Scheduler] Running job — niche={niche} count={count} upload={upload}")

    async def _run():
        for i in range(count):
            topic = get_topic(niche)
            ts = datetime.now().strftime("%Y%m%d%H%M%S")
            output_dir = f"output/sched_{ts}"
            try:
                result = await create_single_short(
                    topic=topic, niche=niche,
                    output_dir=output_dir, upload=upload
                )
                print(f"[Scheduler] Done: {topic} → {output_dir}")
                # Notify dashboard callback if registered
                if _job_callback:
                    _job_callback(niche=niche, topic=topic, result=result)
            except Exception as e:
                print(f"[Scheduler] Error on '{topic}': {e}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_run())
    loop.close()


def set_job_callback(fn):
    """Register a callback for when a scheduled job completes."""
    global _job_callback
    _job_callback = fn


def start(config: dict = None):
    """Start the background scheduler with the given config."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)

    cfg = config or load_config()
    if not cfg.get("enabled"):
        print("[Scheduler] Disabled — not starting.")
        return

    _scheduler = BackgroundScheduler(timezone="UTC")

    # Determine how many slots to activate based on ramp-up week
    max_slots = _ramp_slots(cfg)
    active_schedules = [s for s in cfg.get("schedules", []) if s.get("active")]
    # Sort by hour so we always pick morning first, then afternoon, then evening
    active_schedules.sort(key=lambda s: int(s.get("hour", 0)))
    slots_to_run = active_schedules[:max_slots]

    for sched in slots_to_run:
        niche = sched.get("niche", "finance")
        count = int(sched.get("count", 1))
        upload = sched.get("upload", False)
        hour = int(sched.get("hour", 9))
        minute = int(sched.get("minute", 0))
        _scheduler.add_job(
            _run_scheduled_job,
            trigger=CronTrigger(hour=hour, minute=minute),
            args=[niche, count, upload],
            id=sched.get("id", f"{niche}_{hour}_{minute}"),
            replace_existing=True,
        )
        print(f"[Scheduler] Scheduled: {niche} x{count} @ {hour:02d}:{minute:02d} UTC")

    if _scheduler.get_jobs():
        _scheduler.start()
        print(f"[Scheduler] Started with {len(_scheduler.get_jobs())} job(s).")
    else:
        print("[Scheduler] No active schedules.")


def stop():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[Scheduler] Stopped.")


def get_status() -> dict:
    if not _scheduler or not _scheduler.running:
        return {"running": False, "jobs": []}
    jobs = []
    for job in _scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            "id": job.id,
            "next_run": next_run.isoformat() if next_run else None,
        })
    return {"running": True, "jobs": jobs}


def reload():
    """Reload config from disk and restart scheduler."""
    start(load_config())
