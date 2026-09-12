import sys
import types
import unittest
from unittest import mock


class MediaTests(unittest.TestCase):
    def test_largest_photo_and_best_mp4_are_selected(self):
        from vk_to_tg.media import extract_media

        post = {
            "attachments": [
                {"type": "photo", "photo": {"sizes": [
                    {"url": "small", "width": 100, "height": 100},
                    {"url": "large", "width": 1000, "height": 800},
                ]}},
                {"type": "video", "video": {"owner_id": -42, "id": 9, "access_key": "k"}},
            ]
        }
        class VK:
            def resolve_video(self, video):
                return {"url": "movie.mp4", "size": 1024, "width": 1280, "height": 720, "duration": 10}

        media, notes = extract_media(post, VK())
        self.assertEqual([item["url"] for item in media], ["large", "movie.mp4"])
        self.assertEqual(notes, [])

    def test_unavailable_video_becomes_source_note(self):
        from vk_to_tg.media import extract_media

        post = {"attachments": [{"type": "video", "video": {"owner_id": -42, "id": 9}}]}
        class VK:
            def resolve_video(self, video):
                return None

        media, notes = extract_media(post, VK())
        self.assertEqual(media, [])
        self.assertIn("video-42_9", notes[0])

    def test_video_falls_back_to_ytdlp_when_vk_has_no_file(self):
        from vk_to_tg.vk import VK

        class FakeYoutubeDL:
            def __init__(self, options):
                self.options = options
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return None
            def extract_info(self, url, download=False):
                self.url = url
                return {"formats": [
                    {"format_id": "18", "url": "https://cdn.test/video.mp4", "ext": "mp4",
                     "height": 720, "vcodec": "avc1", "acodec": "mp4a"},
                ]}

        fake_module = types.SimpleNamespace(YoutubeDL=FakeYoutubeDL)
        with mock.patch.dict(sys.modules, {"yt_dlp": fake_module}):
            result = VK("token").resolve_video({"owner_id": -42, "id": 9})

        self.assertEqual(result["url"], "https://cdn.test/video.mp4")
        self.assertEqual(result["height"], 720)


if __name__ == "__main__":
    unittest.main()
