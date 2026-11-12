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

    def get(self, url, headers=None, cookies=None):
        self.calls.append(url)
        if url not in self.routes:
            raise AssertionError(f"unexpected GET {url}")
        return self.routes[url]


ROWS = [
    {"pos": 1, "name": "Alpha|Team", "score": 200, "bracket_name": "Open"},
    {"pos": 2, "name": "Beta", "score": 50, "bracket_name": None},
]


def routes(scoreboard_status=200, scoreboard_payload=None):
    if scoreboard_payload is None:
        scoreboard_payload = {"success": True, "data": ROWS}
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
        "https://ctf.example/api/v1/scoreboard": Response(scoreboard_status, scoreboard_payload),
    }


NOW = datetime(2026, 11, 12, 1, 2, 3, tzinfo=timezone.utc)


class ScoreboardTests(unittest.TestCase):
    def test_scoreboard_flag_writes_json_and_markdown(self):
        http = FakeHTTP(routes())
        with tempfile.TemporaryDirectory() as tmp:
            main.main(
                ["--session", "cookie", "--url", "https://ctf.example", "--scoreboard"],
                env_path=os.path.join(tmp, "missing.env"),
                output_dir=tmp,
                http=http,
                now=NOW,
            )
            with open(os.path.join(tmp, "scoreboard.json"), encoding="utf-8") as handle:
                document = json.load(handle)
            self.assertEqual(document["fetched_at"], NOW.isoformat())
            self.assertEqual(document["data"], ROWS)
            with open(os.path.join(tmp, "scoreboard.md"), encoding="utf-8") as handle:
                markdown = handle.read()
            self.assertIn("| 1 | Alpha\\|Team | 200 | Open |", markdown)
            self.assertIn("| 2 | Beta | 50 |  |", markdown)
            self.assertTrue(os.path.exists(os.path.join(tmp, "web", "Hello", "description.md")))
            self.assertIn("https://ctf.example/api/v1/scoreboard", http.calls)

    def test_scoreboard_stays_off_without_the_flag(self):
        http = FakeHTTP(routes())
        with tempfile.TemporaryDirectory() as tmp:
            main.main(
                ["--session", "cookie", "--url", "https://ctf.example"],
                env_path=os.path.join(tmp, "missing.env"),
                output_dir=tmp,
                http=http,
            )
            self.assertFalse(os.path.exists(os.path.join(tmp, "scoreboard.json")))
            self.assertNotIn("https://ctf.example/api/v1/scoreboard", http.calls)
            self.assertTrue(os.path.exists(os.path.join(tmp, "web", "Hello", "note.txt")))

    def test_hidden_scoreboard_warns_when_challenges_were_requested(self):
        http = FakeHTTP(routes(403, {"message": "Scores are currently hidden"}))
        with tempfile.TemporaryDirectory() as tmp:
            main.main(
                ["--session", "cookie", "--url", "https://ctf.example", "--scoreboard"],
                env_path=os.path.join(tmp, "missing.env"),
                output_dir=tmp,
                http=http,
            )
            self.assertFalse(os.path.exists(os.path.join(tmp, "scoreboard.json")))
            self.assertTrue(os.path.exists(os.path.join(tmp, "web", "Hello", "description.md")))

    def test_hidden_scoreboard_exits_when_it_is_the_only_request(self):
        http = FakeHTTP({"https://ctf.example/api/v1/scoreboard": Response(403, {"message": "hidden"})})
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as caught:
                main.main(
                    ["--session", "cookie", "--url", "https://ctf.example", "--scoreboard"],
                    env_path=os.path.join(tmp, "missing.env"),
                    output_dir=tmp,
                    http=http,
                    challenges_requested=False,
                )
        self.assertEqual(caught.exception.code, 1)
        self.assertEqual(http.calls, ["https://ctf.example/api/v1/scoreboard"])

    def test_env_file_still_honors_scoreboard_flag(self):
        http = FakeHTTP(routes())
        with tempfile.TemporaryDirectory() as tmp:
            env_path = os.path.join(tmp, ".env")
            with open(env_path, "w", encoding="utf-8") as handle:
                handle.write("SESSION=from-env\nURL=https://ctf.example\n")
            output = os.path.join(tmp, "out")
            main.main(["--scoreboard"], env_path=env_path, output_dir=output, http=http, now=NOW)
            self.assertTrue(os.path.exists(os.path.join(output, "scoreboard.md")))


if __name__ == "__main__":
    unittest.main()
