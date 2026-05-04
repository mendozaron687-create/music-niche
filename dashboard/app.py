import os
import sys
import json
import asyncio
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

import scheduler as _scheduler_mod

app = Flask(__name__)
jobs = {}
job_logs = {}


def load_history():
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    history = []
    if os.path.exists(logs_dir):
        for f in sorted(os.listdir(logs_dir), reverse=True)[:50]:
            if f.endswith(".json"):
                with open(os.path.join(logs_dir, f)) as fp:
                    try:
                        history.append(json.load(fp))
                    except Exception:
                        pass
    return history


def load_settings():
    return {
        "SUNO_API_KEY":     os.getenv("SUNO_API_KEY", ""),
        "PEXELS_API_KEY":   os.getenv("PEXELS_API_KEY", ""),
        "OPENROUTER_API_KEY": os.getenv("OPENROUTER_API_KEY", ""),
        "DEFAULT_GENRE":    os.getenv("DEFAULT_GENRE", "lofi_hiphop"),
        "DEFAULT_MODEL":    os.getenv("DEFAULT_MODEL", "V4_5ALL"),
        "VIDEOS_PER_DAY":   os.getenv("VIDEOS_PER_DAY", "3"),
        "AUTO_UPLOAD":      os.getenv("AUTO_UPLOAD", "true"),
    }


def save_settings(data):
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    with open(path, "w") as f:
        for key, value in data.items():
            f.write(f"{key}={value}\n")
    load_dotenv(path, override=True)


def get_stats():
    history = load_history()
    week_videos = 0
    for h in history:
        try:
            if (datetime.now() - datetime.fromisoformat(h.get("date", ""))).days <= 7:
                week_videos += h.get("successful", 0)
        except Exception:
            pass
    return {
        "total_videos":  sum(h.get("successful", 0) for h in history),
        "total_failed":  sum(h.get("failed", 0) for h in history),
        "total_batches": len(history),
        "week_videos":   week_videos,
        "active_jobs":   len([j for j in jobs.values() if j["status"] == "running"]),
    }


def run_job_in_background(job_id, job_type, **kwargs):
    def log(msg):
        job_logs.setdefault(job_id, []).append(
            {"time": datetime.now().strftime("%H:%M:%S"), "msg": msg}
        )

    async def run():
        import sys
        class LogWriter:
            def write(self, msg):
                msg = msg.strip()
                if msg:
                    log(msg)
            def flush(self):
                pass
        old_stdout = sys.stdout
        sys.stdout = LogWriter()
        try:
            jobs[job_id]["status"] = "running"
            log("Job started...")
            if job_type == "single":
                from main import create_music_video
                result = await create_music_video(
                    genre_key=kwargs.get("genre", kwargs.get("niche")),
                    output_dir=f"output/dash_{job_id}",
                    upload=kwargs.get("upload", True),
                    model=kwargs.get("model", "V4_5ALL"),
                    instrumental=kwargs.get("instrumental", False),
                )
                jobs[job_id]["result"] = result
                log(f"Done! {result.get('url', 'Saved locally')}")
            elif job_type == "batch":
                from main import create_music_video
                count = kwargs.get("count", 1)
                log(f"Starting batch of {count} music video(s)...")
                results = []
                for i in range(count):
                    r = await create_music_video(
                        genre_key=kwargs.get("genre", kwargs.get("niche")),
                        output_dir=f"output/dash_{job_id}_{i}",
                        upload=kwargs.get("upload", True),
                        model=kwargs.get("model", "V4_5ALL"),
                        instrumental=kwargs.get("instrumental", False),
                    )
                    results.append(r)
                jobs[job_id]["result"] = results
                log(f"Batch complete! {len(results)} videos created")
            jobs[job_id]["status"] = "complete"
        except Exception as e:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(e)
            log(f"Error: {e}")
        finally:
            sys.stdout = old_stdout

    def thread_target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run())
        loop.close()

    threading.Thread(target=thread_target, daemon=True).start()


@app.route("/")
def index():
    from music_topics import GENRES
    return render_template("index.html",
        stats=get_stats(),
        history=load_history()[:5],
        active_jobs={k: v for k, v in jobs.items() if v["status"] == "running"},
        genres=list(GENRES.keys()),
    )

@app.route("/create")
def create():
    from music_topics import GENRES
    return render_template("create.html", genres=GENRES, settings=load_settings())

@app.route("/batch")
def batch():
    from music_topics import GENRES
    return render_template("batch.html", genres=GENRES, settings=load_settings())

@app.route("/history")
def history():
    return render_template("history.html", history=load_history())

@app.route("/settings")
def settings():
    return render_template("settings.html", settings=load_settings())

@app.route("/api/create", methods=["POST"])
def api_create():
    data = request.json
    job_id = datetime.now().strftime("%Y%m%d%H%M%S")
    jobs[job_id] = {"id": job_id, "type": "single", "status": "queued",
                    "created": datetime.now().isoformat(),
                    "genre": data.get("genre", "lofi_hiphop"), "result": None}
    run_job_in_background(job_id, "single", **data)
    return jsonify({"job_id": job_id, "status": "queued"})

@app.route("/api/batch", methods=["POST"])
def api_batch():
    data = request.json
    job_id = f"batch_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    jobs[job_id] = {"id": job_id, "type": "batch", "status": "queued",
                    "created": datetime.now().isoformat(),
                    "count": data.get("count", 1), "result": None}
    run_job_in_background(job_id, "batch", **data)
    return jsonify({"job_id": job_id, "status": "queued"})

@app.route("/api/job/<job_id>")
def api_job_status(job_id):
    return jsonify({"job": jobs.get(job_id, {}), "logs": job_logs.get(job_id, [])})

@app.route("/api/jobs")
def api_jobs():
    return jsonify(list(jobs.values()))

@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())

@app.route("/api/trending", methods=["GET"])
def api_trending():
    niche = request.args.get("niche", os.getenv("DEFAULT_NICHE", "finance"))
    count = int(request.args.get("count", 8))
    try:
        from trending import get_trending_suggestions
        suggestions = get_trending_suggestions(niche, count)
        return jsonify({"niche": niche, "suggestions": suggestions})
    except Exception as e:
        return jsonify({"error": str(e), "suggestions": []}), 500

@app.route("/api/topics", methods=["GET"])
def api_get_topics():
    return jsonify(load_topics())

@app.route("/api/topics", methods=["POST"])
def api_save_topics():
    save_topics(request.json)
    return jsonify({"status": "saved"})

@app.route("/api/settings", methods=["POST"])
def api_save_settings():
    save_settings(request.json)
    return jsonify({"status": "saved"})

@app.route("/api/download/<job_id>")
def api_download(job_id):
    job = jobs.get(job_id)
    if not job or not job.get("result"):
        return jsonify({"error": "Not found"}), 404
    result = job["result"]
    if isinstance(result, list):
        result = result[0]
    video_path = result.get("paths", {}).get("final")
    if video_path and os.path.exists(video_path):
        return send_file(video_path, as_attachment=True)
    return jsonify({"error": "File not found"}), 404


# ── Scheduler routes ──────────────────────────────────────────────────────────

@app.route("/schedule")
def schedule_page():
    cfg = _scheduler_mod.load_config()
    status = _scheduler_mod.get_status()
    return render_template("schedule.html",
                           config=cfg, status=status,
                           topics=load_topics(), settings=load_settings())


@app.route("/api/schedule", methods=["GET"])
def api_schedule_get():
    return jsonify({
        "config": _scheduler_mod.load_config(),
        "status": _scheduler_mod.get_status(),
    })


@app.route("/api/schedule", methods=["POST"])
def api_schedule_save():
    cfg = request.json
    _scheduler_mod.save_config(cfg)
    _scheduler_mod.reload()
    return jsonify({"status": "saved", "scheduler": _scheduler_mod.get_status()})


@app.route("/api/schedule/run-now", methods=["POST"])
def api_schedule_run_now():
    """Immediately trigger a scheduled genre without waiting for cron time."""
    data = request.json or {}
    genre = data.get("genre", data.get("niche", "lofi_hiphop"))
    count = int(data.get("count", 1))
    upload = data.get("upload", False)
    job_id = f"sched_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    jobs[job_id] = {"id": job_id, "type": "scheduled", "status": "queued",
                    "created": datetime.now().isoformat(),
                    "genre": genre, "result": None}
    run_job_in_background(job_id, "batch",
                          genre=genre, count=count, upload=upload)
    return jsonify({"job_id": job_id, "status": "queued"})


if __name__ == "__main__":
    _scheduler_mod.start()
    print("Dashboard running at http://localhost:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
