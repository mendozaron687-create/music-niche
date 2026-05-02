import asyncio
import json
import os
from datetime import datetime, timedelta
from main import get_topic, create_single_short

BATCH_CONFIG = {
    "videos_per_day": 3,
    "niche": "finance",
    "upload": True,
    "delay_between": 30,
}


async def run_batch(count: int = 3, niche: str = "finance",
                    upload: bool = True, delay: int = 30):
    print(f"\nBATCH YOUTUBE SHORTS CREATOR")
    print(f"Videos: {count} | Niche: {niche}\n")
    results = []
    failed = []
    used_topics = _load_used_topics()
    topics = []
    for _ in range(count * 3):
        topic = get_topic(niche)
        if topic not in used_topics and topic not in topics:
            topics.append(topic)
        if len(topics) >= count:
            break
    print("Topics for today:")
    for i, t in enumerate(topics, 1):
        print(f"  {i}. {t}")
    print()
    for i, topic in enumerate(topics, 1):
        print(f"\nCreating video {i}/{count}...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"output/batch_{timestamp}_{i}"
        try:
            result = await create_single_short(
                topic=topic, niche=niche, output_dir=output_dir, upload=upload
            )
            results.append(result)
            _save_used_topic(topic)
            print(f"Video {i}/{count} complete!")
            if upload and i < count:
                print(f"Waiting {delay}s before next upload...")
                await asyncio.sleep(delay)
        except Exception as e:
            print(f"Video {i} failed: {e}")
            failed.append({"topic": topic, "error": str(e)})
    _print_summary(results, failed)
    _save_batch_log(results, failed)
    return results


def _load_used_topics() -> set:
    path = os.path.join(os.path.dirname(__file__), "used_topics.json")
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        cutoff = (datetime.now() - timedelta(days=30)).isoformat()
        return {item["topic"] for item in data if item.get("date", "") > cutoff}
    return set()


def _save_used_topic(topic: str):
    path = os.path.join(os.path.dirname(__file__), "used_topics.json")
    data = []
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
    data.append({"topic": topic, "date": datetime.now().isoformat()})
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _print_summary(results, failed):
    print(f"\nSummary: {len(results)} successful, {len(failed)} failed")
    for r in results:
        print(f"  {r['topic'][:40]}")
        if r.get("url"):
            print(f"  {r['url']}")


def _save_batch_log(results, failed):
    log = {
        "date": datetime.now().isoformat(),
        "successful": len(results),
        "failed": len(failed),
        "videos": results,
        "errors": failed
    }
    os.makedirs("logs", exist_ok=True)
    log_file = f"logs/batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(log_file, "w") as f:
        json.dump(log, f, indent=2, default=str)
    print(f"Log saved: {log_file}")


if __name__ == "__main__":
    asyncio.run(run_batch(
        count=BATCH_CONFIG["videos_per_day"],
        niche=BATCH_CONFIG["niche"],
        upload=BATCH_CONFIG["upload"],
        delay=BATCH_CONFIG["delay_between"]
    ))
