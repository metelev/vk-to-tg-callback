import tempfile
import unittest
import json
from pathlib import Path
from unittest import mock


class DeliveryTests(unittest.TestCase):
    def test_config_loads_optional_telegram_proxy(self):
        from vk_to_tg.config import Config

        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(
                "VK_GROUP_ID=42\n"
                "VK_CALLBACK_SECRET=secret\n"
                "VK_CONFIRMATION=confirmation\n"
                "VK_USER_TOKEN=vk-token\n"
                "TELEGRAM_BOT_TOKEN=tg-token\n"
                "TELEGRAM_CHAT_ID=-1001\n"
                "TELEGRAM_PROXY_URL=socks5h://127.0.0.1:12334\n",
                encoding="utf-8",
            )
            with mock.patch.dict("os.environ", {}, clear=True):
                config = Config.load(str(env_path))

        self.assertEqual(
            config.telegram_proxy_url,
            "socks5h://127.0.0.1:12334",
        )

    def test_telegram_uses_configured_proxy(self):
        from vk_to_tg.telegram import Telegram

        telegram = Telegram(
            "token",
            "-1001",
            proxy_url="socks5h://127.0.0.1:12334",
        )

        self.assertEqual(
            telegram.session.proxies,
            {
                "http": "socks5h://127.0.0.1:12334",
                "https": "socks5h://127.0.0.1:12334",
            },
        )

    def test_utf16_caption_split_preserves_emoji(self):
        from vk_to_tg.telegram import split_utf16

        text = "😀" * 600
        head, tail = split_utf16(text, 1024)
        self.assertEqual(head + tail, text)
        self.assertLessEqual(len(head.encode("utf-16-le")) // 2, 1024)
        self.assertEqual(len(head), 512)

    def test_captioned_photo_is_one_telegram_call(self):
        from vk_to_tg.state import State
        from vk_to_tg.worker import deliver_one

        class Telegram:
            def __init__(self): self.calls = []
            def publish(self, text, media):
                self.calls.append((text, media)); return {"message_id": 5}

        with tempfile.TemporaryDirectory() as directory:
            state = State(f"{directory}/state.db")
            self.addCleanup(state.close)
            state.enqueue("vk:-42:7", {"id": 7, "owner_id": -42, "text": "hello", "attachments": []})
            tg = Telegram()
            deliver_one(state, state.pending()[0], tg, lambda post: ([{"type": "photo", "url": "x"}], []))
            self.assertEqual(len(tg.calls), 1)
            self.assertTrue(tg.calls[0][0].startswith("hello"))
            self.assertIn("https://vk.com/wall-42_7", tg.calls[0][0])
            self.assertEqual(state.list_jobs()[0]["status"], "done")

    def test_lost_remote_result_is_not_retried_automatically(self):
        from vk_to_tg.state import State
        from vk_to_tg.telegram import AmbiguousSend
        from vk_to_tg.worker import deliver_one

        class Telegram:
            def publish(self, text, media): raise AmbiguousSend("timeout")

        with tempfile.TemporaryDirectory() as directory:
            state = State(f"{directory}/state.db")
            self.addCleanup(state.close)
            state.enqueue("vk:-42:7", {"id": 7, "owner_id": -42, "text": "hello", "attachments": []})
            deliver_one(state, state.pending()[0], Telegram(), lambda post: ([], []))
            self.assertEqual(state.list_jobs()[0]["status"], "uncertain")

    def test_two_photos_are_sent_as_one_media_group(self):
        from vk_to_tg.telegram import Telegram

        class Response:
            ok = True
            status_code = 200
            headers = {"Content-Length": "3"}
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def raise_for_status(self): return None
            def iter_content(self, size): yield b"jpg"
            def json(self): return {"ok": True, "result": [{"message_id": 1}, {"message_id": 2}]}

        class Session:
            def __init__(self): self.posts = []
            def get(self, *args, **kwargs): return Response()
            def post(self, url, data, files=None, timeout=None):
                self.posts.append((url, data, files)); return Response()

        session = Session()
        telegram = Telegram("token", "-1001", session=session)
        result = telegram.publish("caption", [
            {"type": "photo", "url": "https://example.test/1.jpg"},
            {"type": "photo", "url": "https://example.test/2.jpg"},
        ])
        self.assertEqual(len(result), 2)
        self.assertTrue(session.posts[0][0].endswith("/sendMediaGroup"))
        description = json.loads(session.posts[0][1]["media"])
        self.assertEqual(description[0]["caption"], "caption")
        self.assertEqual(len(description), 2)

    def test_single_video_is_uploaded_as_streaming_video(self):
        from vk_to_tg.telegram import Telegram

        class Response:
            ok = True
            status_code = 200
            headers = {"Content-Length": "3"}
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def raise_for_status(self): return None
            def iter_content(self, size): yield b"mp4"
            def json(self): return {"ok": True, "result": {"message_id": 3}}

        class Session:
            def __init__(self): self.posts = []
            def get(self, *args, **kwargs): return Response()
            def post(self, url, data, files=None, timeout=None):
                self.posts.append((url, data, files)); return Response()

        session = Session()
        telegram = Telegram("token", "-1001", session=session)
        telegram.publish("caption", [{"type": "video", "url": "https://example.test/video.mp4"}])
        self.assertTrue(session.posts[0][0].endswith("/sendVideo"))
        self.assertEqual(session.posts[0][1]["supports_streaming"], "true")
        self.assertIn("video", session.posts[0][2])

    def test_more_than_ten_media_fail_before_download(self):
        from vk_to_tg.telegram import Telegram, TelegramError

        class Session:
            def get(self, *args, **kwargs):
                raise AssertionError("download must not start")

        telegram = Telegram("token", "-1001", session=Session())
        with self.assertRaises(TelegramError):
            telegram.publish("caption", [{"type": "photo", "url": "x"}] * 11)


if __name__ == "__main__":
    unittest.main()
