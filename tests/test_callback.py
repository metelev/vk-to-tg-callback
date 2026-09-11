import tempfile
import unittest


class CallbackTests(unittest.TestCase):
    def test_confirmation_is_returned_without_enqueueing(self):
        from vk_to_tg.state import State
        from vk_to_tg.web import Callback

        with tempfile.TemporaryDirectory() as directory:
            state = State(f"{directory}/state.db")
            self.addCleanup(state.close)
            callback = Callback(state, group_id=42, secret="secret", confirmation="confirm")
            status, body = callback.handle({"type": "confirmation", "group_id": 42})
            self.assertEqual((status, body), (200, "confirm"))
            self.assertEqual(state.list_jobs(), [])

    def test_wrong_secret_is_rejected(self):
        from vk_to_tg.state import State
        from vk_to_tg.web import Callback

        with tempfile.TemporaryDirectory() as directory:
            state = State(f"{directory}/state.db")
            self.addCleanup(state.close)
            callback = Callback(state, group_id=42, secret="secret", confirmation="confirm")
            status, body = callback.handle(
                {"type": "wall_post_new", "group_id": 42, "secret": "wrong", "object": {}}
            )
            self.assertEqual((status, body), (403, "forbidden"))

    def test_duplicate_wall_event_creates_one_job(self):
        from vk_to_tg.state import State
        from vk_to_tg.web import Callback

        event = {
            "type": "wall_post_new",
            "group_id": 42,
            "secret": "secret",
            "object": {"id": 7, "owner_id": -42, "text": "hello", "attachments": []},
        }
        with tempfile.TemporaryDirectory() as directory:
            state = State(f"{directory}/state.db")
            self.addCleanup(state.close)
            callback = Callback(state, group_id=42, secret="secret", confirmation="confirm")
            self.assertEqual(callback.handle(event), (200, "ok"))
            self.assertEqual(callback.handle(event), (200, "ok"))
            self.assertEqual(len(state.list_jobs()), 1)

    def test_interrupted_delivery_is_quarantined_on_restart(self):
        from vk_to_tg.state import State

        with tempfile.TemporaryDirectory() as directory:
            path = f"{directory}/state.db"
            state = State(path)
            state.enqueue("vk:-42:7", {"id": 7})
            state.set_status("vk:-42:7", "sending")
            state.close()
            restarted = State(path)
            self.addCleanup(restarted.close)
            restarted.recover()
            self.assertEqual(restarted.list_jobs()[0]["status"], "uncertain")


if __name__ == "__main__":
    unittest.main()
