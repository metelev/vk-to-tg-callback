import unittest


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


if __name__ == "__main__":
    unittest.main()
