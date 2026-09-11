import argparse
import fcntl
import logging
import os
from pathlib import Path
import signal
import threading

from .config import Config
from .media import extract_media
from .state import State
from .telegram import Telegram
from .vk import VK
from .web import Callback, serve
from .worker import run_worker


def main() -> None:
    parser = argparse.ArgumentParser(description="VK Callback API to Telegram cross-poster")
    parser.add_argument("command", choices=["run", "check", "status", "retry", "resolve"])
    parser.add_argument("key", nargs="?")
    args = parser.parse_args()
    config = Config.load()
    os.umask(0o077)
    Path(config.database_path).parent.mkdir(parents=True, exist_ok=True)
    lock = open(config.database_path + ".lock", "a", encoding="utf-8")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.error("service is running; stop it before using this command")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    state = State(config.database_path)
    if args.command == "status":
        for job in state.list_jobs():
            print(job["key"], job["status"], job["error"])
        return
    if args.command in {"retry", "resolve"}:
        jobs = {job["key"]: job for job in state.list_jobs()}
        if not args.key or args.key not in jobs:
            parser.error("provide an existing job key from the status command")
        state.set_status(args.key, "pending" if args.command == "retry" else "done")
        return
    telegram = Telegram(
        config.telegram_bot_token, config.telegram_chat_id, config.media_limit_mb
    )
    vk = VK(config.vk_user_token)
    if args.command == "check":
        telegram.check()
        group = vk.call("groups.getById", group_id=config.vk_group_id)
        if not group:
            raise RuntimeError("VK group is unavailable")
        print("VK and Telegram checks passed; no post was sent")
        return
    state.recover()
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    def worker_main():
        worker_state = State(config.database_path)
        try:
            run_worker(worker_state, telegram, lambda post: extract_media(post, vk), stop)
        finally:
            worker_state.close()

    worker = threading.Thread(
        target=worker_main,
        name="delivery-worker",
    )
    worker.start()
    callback = Callback(
        state, config.vk_group_id, config.vk_callback_secret, config.vk_confirmation
    )
    try:
        serve(callback, config.callback_path, config.listen_host, config.listen_port, stop)
    finally:
        stop.set()
        worker.join(timeout=130)
        state.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logging.error("stopped: %s", type(exc).__name__)
        raise SystemExit(1)
