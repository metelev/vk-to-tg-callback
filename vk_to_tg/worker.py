import logging
import time
from .telegram import AmbiguousSend, RetryableSend, TelegramError


log = logging.getLogger("vk_to_tg.worker")


def _post_text(post: dict, notes: list[str]) -> str:
    text = post.get("text", "").strip()
    source = f"https://vk.com/wall{post['owner_id']}_{post['id']}"
    parts = [part for part in [text, *notes, "Источник: " + source] if part]
    return "\n\n".join(parts)


def deliver_one(state, job: dict, telegram, extractor) -> str:
    key = job["key"]
    state.set_status(key, "sending")
    try:
        media, notes = extractor(job["payload"])
        result = telegram.publish(_post_text(job["payload"], notes), media)
        state.complete(key, result)
        log.info("delivered %s", key)
        return "done"
    except RetryableSend as exc:
        state.set_status(key, "pending", str(exc))
        return "retry"
    except AmbiguousSend as exc:
        state.set_status(key, "uncertain", str(exc))
        log.error("delivery result uncertain for %s; inspect Telegram", key)
        return "uncertain"
    except (TelegramError, ValueError, KeyError) as exc:
        state.set_status(key, "failed", str(exc))
        log.error("delivery failed for %s: %s", key, type(exc).__name__)
        return "failed"


def run_worker(state, telegram, extractor, stop) -> None:
    while not stop.is_set():
        jobs = state.pending()
        if not jobs:
            stop.wait(2)
            continue
        for job in jobs:
            if stop.is_set():
                break
            outcome = deliver_one(state, job, telegram, extractor)
            if outcome == "retry":
                stop.wait(30)
            else:
                stop.wait(1)
