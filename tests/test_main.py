import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

import main


class Response:
    def __init__(self, status_code, payload=None, content=b"", text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.content = content
        self.text = text or json.dumps(self._payload)

    def json(self):
        return self._payload


class FakeHTTP:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, headers=None, cookies=None, params=None):
        self.calls.append({"url": url, "params": params})
        if url not in self.routes:
            raise AssertionError(f"unexpected GET {url}")
        return self.routes[url]


NOTES = [
    {
        "id": 3,
        "title": "Hello",
        "content": "Round started",
        "date": "2026-11-12T01:00:00Z",
        "html": "<p>Round started</p>",
        "user_id": None,
    }
]


def routes(notes=None, status=200):
    payload = {"success": True, "data": NOTES if notes is None else notes}
    return {
        "https://ctf.example/api/v1/challenges": Response(
            200, {"data": [{"id": 7, "name": "Hello", "category": "web"}]}
        ),
        "https://ctf.example/api/v1/challenges/7": Response(
            200,
            {
                "data": {
                    "id": 7,
                    "name": "Hello",
                    "category": "web",
                    "description": "Do the thing",
                    "value": 100,
                    "files": ["/files/abc/note.txt"],
                }
            },
        ),
        "https://ctf.example/files/abc/note.txt": Response(200, content=b"note"),
        "https://ctf.example/api/v1/notifications": Response(status, payload, text="nope" if status != 200 else ""),
    }


NOW = datetime(2026, 11, 12, 1, 2, 3, tzinfo=timezone.utc)


class NotificationTests(unittest.TestCase):
    def test_notifications_keep_id_title_date_and_content(self):
        http = FakeHTTP(routes())
        with tempfile.TemporaryDirectory() as tmp:
            main.main(
                ["--session", "cookie", "--url", "https://ctf.example", "--notifications"],
                env_path=os.path.join(tmp, "missing.env"),
                output_dir=tmp,
                http=http,
                now=NOW,
            )
            with open(os.path.join(tmp, "notifications.json"), encoding="utf-8") as handle:
                document = json.load(handle)
            self.assertEqual(document["fetched_at"], NOW.isoformat())
            self.assertEqual(
                document["data"],
                [{"id": 3, "title": "Hello", "date": "2026-11-12T01:00:00Z", "content": "Round started"}],
            )
            with open(os.path.join(tmp, "notifications.md"), encoding="utf-8") as handle:
                markdown = handle.read()
            self.assertIn("## Hello", markdown)
            self.assertIn("- id: 3", markdown)
            self.assertIn("Round started", markdown)
            self.assertNotIn("<p>", markdown)
            self.assertTrue(os.path.exists(os.path.join(tmp, "web", "Hello", "description.md")))
            note_call = http.calls[-1]
            self.assertEqual(note_call["url"], "https://ctf.example/api/v1/notifications")
            self.assertIsNone(note_call["params"])

    def test_since_id_is_sent(self):
        http = FakeHTTP(routes(notes=[]))
        with tempfile.TemporaryDirectory() as tmp:
            main.main(
                ["--session", "cookie", "--url", "https://ctf.example", "--notifications", "--since-id", "3"],
                env_path=os.path.join(tmp, "missing.env"),
                output_dir=tmp,
                http=http,
                now=NOW,
            )
            self.assertEqual(http.calls[-1]["params"], {"since_id": 3})
            with open(os.path.join(tmp, "notifications.md"), encoding="utf-8") as handle:
                self.assertIn("No notifications.", handle.read())

    def test_notifications_stay_off_without_the_flag(self):
        http = FakeHTTP(routes())
        with tempfile.TemporaryDirectory() as tmp:
            main.main(
                ["--session", "cookie", "--url", "https://ctf.example"],
                env_path=os.path.join(tmp, "missing.env"),
                output_dir=tmp,
                http=http,
            )
            self.assertFalse(os.path.exists(os.path.join(tmp, "notifications.json")))
            self.assertNotIn("https://ctf.example/api/v1/notifications", [call["url"] for call in http.calls])

    def test_notification_failure_exits(self):
        http = FakeHTTP(routes(status=403))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as caught:
                main.main(
                    ["--session", "cookie", "--url", "https://ctf.example", "--notifications"],
                    env_path=os.path.join(tmp, "missing.env"),
                    output_dir=tmp,
                    http=http,
                )
        self.assertEqual(caught.exception.code, 1)

    def test_env_file_still_honors_notifications_flag(self):
        http = FakeHTTP(routes())
        with tempfile.TemporaryDirectory() as tmp:
            env_path = os.path.join(tmp, ".env")
            with open(env_path, "w", encoding="utf-8") as handle:
                handle.write("SESSION=from-env\nURL=https://ctf.example\n")
            output = os.path.join(tmp, "out")
            main.main(["--notifications"], env_path=env_path, output_dir=output, http=http, now=NOW)
            self.assertTrue(os.path.exists(os.path.join(output, "notifications.json")))


if __name__ == "__main__":
    unittest.main()
