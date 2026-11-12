import io
import json
import os
from datetime import datetime, timezone
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

import main


class Response:
    def __init__(self, status_code, payload=None, content=b"", text=""):
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.text = text

    def json(self):
        return self._payload


class FakeHTTP:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self.requests = []

    def get(self, url, headers=None, cookies=None, params=None):
        self.calls.append(url)
        self.requests.append({"url": url, "headers": headers or {}, "cookies": cookies, "params": params})
        if url not in self.routes:
            raise AssertionError(f"unexpected GET {url}")
        return self.routes[url]


def challenge_routes(file_url="/files/abc/note.txt?token=1", body=b"note"):
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
                    "files": [file_url],
                }
            },
        ),
        f"https://ctf.example{file_url}": Response(200, content=body),
    }


class FlagTests(unittest.TestCase):
    def test_nofiles_writes_description_and_skips_downloads(self):
        http = FakeHTTP(challenge_routes())
        with tempfile.TemporaryDirectory() as tmp:
            main.main(
                ["--session", "cookie", "--url", "https://ctf.example", "--nofiles"],
                env_path=os.path.join(tmp, "missing.env"),
                output_dir=tmp,
                http=http,
            )
            description = os.path.join(tmp, "web", "Hello", "description.md")
            with open(description, encoding="utf-8") as handle:
                text = handle.read()
            self.assertIn("# Hello", text)
            self.assertIn("Do the thing", text)
            self.assertIn("web", text)
            self.assertIn("100", text)
            self.assertFalse(os.path.exists(os.path.join(tmp, "web", "Hello", "note.txt")))
            self.assertNotIn("https://ctf.example/files/abc/note.txt?token=1", http.calls)

    def test_nooverwrite_keeps_existing_description_and_skips_files(self):
        http = FakeHTTP(challenge_routes())
        with tempfile.TemporaryDirectory() as tmp:
            description = os.path.join(tmp, "web", "Hello", "description.md")
            os.makedirs(os.path.dirname(description))
            with open(description, "w", encoding="utf-8") as handle:
                handle.write("keep me\n")
            main.main(
                ["--session", "cookie", "--url", "https://ctf.example", "--nooverwrite"],
                env_path=os.path.join(tmp, "missing.env"),
                output_dir=tmp,
                http=http,
            )
            with open(description, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "keep me\n")
            self.assertFalse(os.path.exists(os.path.join(tmp, "web", "Hello", "note.txt")))

    def test_env_file_still_honors_cli_flags(self):
        http = FakeHTTP(challenge_routes())
        with tempfile.TemporaryDirectory() as tmp:
            env_path = os.path.join(tmp, ".env")
            with open(env_path, "w", encoding="utf-8") as handle:
                handle.write("SESSION=from-env\nURL=https://ctf.example\n")
            output = os.path.join(tmp, "out")
            main.main(["--nofiles"], env_path=env_path, output_dir=output, http=http)
            self.assertTrue(os.path.exists(os.path.join(output, "web", "Hello", "description.md")))
            self.assertFalse(os.path.exists(os.path.join(output, "web", "Hello", "note.txt")))

    def test_downloads_attachment_beside_description(self):
        http = FakeHTTP(challenge_routes())
        with tempfile.TemporaryDirectory() as tmp:
            main.main(
                ["--session", "cookie", "--url", "https://ctf.example"],
                env_path=os.path.join(tmp, "missing.env"),
                output_dir=tmp,
                http=http,
            )
            file_path = os.path.join(tmp, "web", "Hello", "note.txt")
            with open(file_path, "rb") as handle:
                self.assertEqual(handle.read(), b"note")

    def test_login_uses_nonce(self):
        page = Response(200, text='<input name="nonce" value="abc123">')
        post = Response(302)

        class CookieJar(dict):
            def get_dict(self):
                return dict(self)

        session = mock.Mock()
        session.get.return_value = page
        session.post.return_value = post
        session.cookies = CookieJar(session="logged-in")
        http = FakeHTTP(challenge_routes())
        http.Session = mock.Mock(return_value=session)
        with tempfile.TemporaryDirectory() as tmp:
            main.main(
                ["--username", "ada", "--password", "secret", "--url", "https://ctf.example", "--nofiles"],
                env_path=os.path.join(tmp, "missing.env"),
                output_dir=tmp,
                http=http,
            )
        session.post.assert_called_once()
        self.assertEqual(session.post.call_args.kwargs["data"]["nonce"], "abc123")
        self.assertEqual(session.post.call_args.kwargs["data"]["name"], "ada")

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
SECRET = "ctfd_super_secret_value"


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
            note_call = http.requests[-1]
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
            self.assertEqual(http.requests[-1]["params"], {"since_id": 3})
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
            self.assertNotIn("https://ctf.example/api/v1/notifications", [call["url"] for call in http.requests])

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

    def test_notifications_use_access_token_header(self):
        http = FakeHTTP(routes())
        with tempfile.TemporaryDirectory() as tmp:
            main.main(
                ["--token", SECRET, "--url", "https://ctf.example", "--notifications"],
                env_path=os.path.join(tmp, "missing.env"),
                output_dir=tmp,
                http=http,
                now=NOW,
            )
        note_call = http.requests[-1]
        self.assertEqual(note_call["url"], "https://ctf.example/api/v1/notifications")
        self.assertEqual(note_call["headers"]["Authorization"], f"Token {SECRET}")
        self.assertEqual(note_call["headers"]["Content-Type"], "application/json")
        self.assertIsNone(note_call["cookies"])


class TokenTests(unittest.TestCase):
    def test_token_sends_authorization_and_json_content_type(self):
        http = FakeHTTP(challenge_routes(file_url="/files/abc/note.txt", body=b"note"))
        with tempfile.TemporaryDirectory() as tmp:
            main.main(
                ["--token", SECRET, "--url", "https://ctf.example"],
                env_path=os.path.join(tmp, "missing.env"),
                output_dir=tmp,
                http=http,
            )
            challenge_call = http.requests[0]
            self.assertEqual(challenge_call["headers"]["Authorization"], f"Token {SECRET}")
            self.assertEqual(challenge_call["headers"]["Content-Type"], "application/json")
            self.assertIsNone(challenge_call["cookies"])
            description = os.path.join(tmp, "web", "Hello", "description.md")
            with open(description, encoding="utf-8") as handle:
                self.assertIn("Do the thing", handle.read())

    def test_cli_token_overrides_env_session(self):
        http = FakeHTTP(challenge_routes(file_url="/files/abc/note.txt"))
        with tempfile.TemporaryDirectory() as tmp:
            env_path = os.path.join(tmp, ".env")
            with open(env_path, "w", encoding="utf-8") as handle:
                handle.write("SESSION=from-env\nURL=https://ctf.example\n")
            main.main(["--token", SECRET], env_path=env_path, output_dir=tmp, http=http)
        self.assertEqual(http.requests[0]["headers"]["Authorization"], f"Token {SECRET}")
        self.assertIsNone(http.requests[0]["cookies"])

    def test_env_ctfd_token_used_when_cli_is_empty(self):
        http = FakeHTTP(challenge_routes(file_url="/files/abc/note.txt"))
        with tempfile.TemporaryDirectory() as tmp:
            env_path = os.path.join(tmp, ".env")
            with open(env_path, "w", encoding="utf-8") as handle:
                handle.write(f"CTFD_TOKEN={SECRET}\nURL=https://ctf.example\n")
            main.main([], env_path=env_path, output_dir=tmp, http=http)
        self.assertEqual(http.requests[0]["headers"]["Authorization"], f"Token {SECRET}")

    def test_ctfd_token_wins_over_session_in_env(self):
        http = FakeHTTP(challenge_routes(file_url="/files/abc/note.txt"))
        with tempfile.TemporaryDirectory() as tmp:
            env_path = os.path.join(tmp, ".env")
            with open(env_path, "w", encoding="utf-8") as handle:
                handle.write(f"CTFD_TOKEN={SECRET}\nSESSION=from-env\nURL=https://ctf.example\n")
            main.main([], env_path=env_path, output_dir=tmp, http=http)
        self.assertEqual(http.requests[0]["headers"]["Authorization"], f"Token {SECRET}")
        self.assertIsNone(http.requests[0]["cookies"])

    def test_access_token_env_name_is_ignored(self):
        http = FakeHTTP(challenge_routes(file_url="/files/abc/note.txt"))
        with tempfile.TemporaryDirectory() as tmp:
            env_path = os.path.join(tmp, ".env")
            with open(env_path, "w", encoding="utf-8") as handle:
                handle.write(f"ACCESS_TOKEN={SECRET}\nURL=https://ctf.example\n")
            with self.assertRaises(SystemExit) as caught:
                main.main([], env_path=env_path, output_dir=tmp, http=http)
        self.assertEqual(caught.exception.code, 1)
        self.assertEqual(http.calls, [])

    def test_list_tokens_prints_metadata_only_and_does_not_scrape(self):
        http = FakeHTTP(
            {
                "https://ctf.example/api/v1/tokens": Response(
                    200,
                    {
                        "success": True,
                        "data": [
                            {
                                "id": 4,
                                "type": "user",
                                "expiration": "2026-12-31",
                                "value": SECRET,
                                "description": "cli",
                            }
                        ],
                    },
                )
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                main.main(
                    ["--token", SECRET, "--url", "https://ctf.example", "--list-tokens"],
                    env_path=os.path.join(tmp, "missing.env"),
                    output_dir=tmp,
                    http=http,
                )
        output = buffer.getvalue()
        self.assertIn("id\ttype\texpiration", output)
        self.assertIn("4\tuser\t2026-12-31", output)
        self.assertNotIn(SECRET, output)
        self.assertEqual(http.calls, ["https://ctf.example/api/v1/tokens"])
        self.assertEqual(http.requests[0]["headers"]["Content-Type"], "application/json")

    def test_login_requires_redirect_and_session_cookie(self):
        session = mock.Mock()
        session.get.return_value = Response(200, text='<input name="nonce" value="abc">')
        session.post.return_value = Response(200, text="nope")
        session.cookies = {}
        http = FakeHTTP({})
        http.Session = mock.Mock(return_value=session)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as caught:
                main.main(
                    ["--username", "ada", "--password", "secret", "--url", "https://ctf.example"],
                    env_path=os.path.join(tmp, "missing.env"),
                    output_dir=tmp,
                    http=http,
                )
        self.assertEqual(caught.exception.code, 1)

    def test_login_success_scrapes_with_session_cookie(self):
        session = mock.Mock()
        session.get.return_value = Response(200, text='<input name="nonce" value="abc">')
        session.post.return_value = Response(302)

        class CookieJar(dict):
            def get_dict(self):
                return dict(self)

        session.cookies = CookieJar(session="logged-in")
        http = FakeHTTP(challenge_routes(file_url="/files/abc/note.txt"))
        http.Session = mock.Mock(return_value=session)
        with tempfile.TemporaryDirectory() as tmp:
            main.main(
                ["--username", "ada", "--password", "secret", "--url", "https://ctf.example"],
                env_path=os.path.join(tmp, "missing.env"),
                output_dir=tmp,
                http=http,
            )
        self.assertEqual(http.requests[0]["cookies"], {"session": "logged-in"})
        self.assertNotIn("Authorization", http.requests[0]["headers"])


if __name__ == "__main__":
    unittest.main()
