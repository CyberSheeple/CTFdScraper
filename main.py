import argparse
import json
import os
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from dotenv import dotenv_values

DEFAULT_URL = "https://icoblue2025.ctfd.io"
ENV_KEYS = ("CTFD_TOKEN", "SESSION", "USERNAME", "PASSWORD", "URL")
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/6.9 (X11; TempleOS x86_32; rv:139.0) Gecko/20100101 Firefox/139.0",
}


def build_parser():
    parser = argparse.ArgumentParser(description="CTFd Scraper - Download challenges and files")
    parser.add_argument("--username", help="CTFd username")
    parser.add_argument("--password", help="CTFd password")
    parser.add_argument("--session", help="Session cookie for CTFd")
    parser.add_argument("--token", help="CTFd access token (Authorization: Token)")
    parser.add_argument("--url", default=None, help="Base URL of the CTFd instance")
    parser.add_argument(
        "--nofiles",
        action="store_true",
        help="Skip downloading files, only download challenge descriptions",
    )
    parser.add_argument(
        "--nooverwrite",
        action="store_true",
        help="Skip overwriting existing description.md files",
    )
    parser.add_argument(
        "--scoreboard",
        action="store_true",
        help="Also save output/scoreboard.json and output/scoreboard.md",
    )
    parser.add_argument(
        "--list-tokens",
        action="store_true",
        help="Print access token id, type, and expiration, then exit",
    )
    return parser


def read_env(env_path):
    """Return .env values without overriding variables already in the process."""
    if not env_path or not os.path.exists(env_path):
        return {}
    file_values = {key: value for key, value in dotenv_values(env_path).items() if value is not None}
    values = {}
    for key in ENV_KEYS:
        if key in os.environ:
            values[key] = os.environ[key]
        elif key in file_values:
            values[key] = file_values[key]
    return values


def login(url, username, password, http):
    session = http.Session()
    login_url = f"{url}/login"
    login_page = session.get(login_url)
    soup = BeautifulSoup(login_page.text, "html.parser")
    nonce_tag = soup.find("input", {"name": "nonce"})
    if nonce_tag is None or not nonce_tag.get("value"):
        print("[-] CTFd login page did not include a nonce.")
        raise SystemExit(1)
    response = session.post(
        login_url,
        data={"name": username, "password": password, "nonce": nonce_tag["value"]},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        allow_redirects=False,
    )
    if response.status_code not in (302, 303) or "session" not in session.cookies:
        print(f"[-] CTFd login failed ({response.status_code}).")
        raise SystemExit(1)
    return session.cookies.get_dict()


def resolve_url(args, env):
    if args.url:
        return args.url.rstrip("/")
    if env.get("URL"):
        return env["URL"].rstrip("/")
    if args.token or args.session or args.username or args.password:
        return DEFAULT_URL
    print("[-] CTFD_TOKEN, SESSION, or both USERNAME and PASSWORD must be set in the .env file. URL is also required.")
    raise SystemExit(1)


def credentials_from(args, env):
    """CLI credentials replace .env. Token, then session, then username and password."""
    if args.token or args.session or args.username or args.password:
        return args.token, args.session, args.username, args.password, "cli"
    token = env.get("CTFD_TOKEN")
    return token, env.get("SESSION"), env.get("USERNAME"), env.get("PASSWORD"), "env"


def resolve_auth(args, env, http):
    url = resolve_url(args, env)
    token, session_cookie, username, password, source = credentials_from(args, env)
    suffix = " from .env file" if source == "env" else ""
    if token:
        print(f"[+] Using access token{suffix}")
        return url, {"Authorization": f"Token {token}"}, None
    if session_cookie:
        print(f"[+] Using session cookie{suffix}")
        return url, {}, {"session": session_cookie}
    if username or password:
        if not username or not password:
            print("[-] Either --session or both --username and --password are required.")
            raise SystemExit(1)
        print(f"[+] Using username and password{suffix}")
        return url, {}, login(url, username, password, http)
    if source == "env":
        print("[-] CTFD_TOKEN, SESSION, or both USERNAME and PASSWORD must be set in the .env file. URL is also required.")
    else:
        print("[-] Either --token, --session, or both --username and --password are required.")
    raise SystemExit(1)


def api_get(http, url, headers, cookies):
    kwargs = {"headers": headers}
    if cookies:
        kwargs["cookies"] = cookies
    return http.get(url, **kwargs)


def list_tokens(url, headers, cookies, http):
    response = api_get(http, f"{url}/api/v1/tokens", headers, cookies)
    if response.status_code != 200:
        print(f"[-] Failed to retrieve tokens: {response.status_code} - {response.text}")
        raise SystemExit(1)
    print("id\ttype\texpiration")
    for row in response.json().get("data") or []:
        print(f"{row.get('id', '')}\t{row.get('type', '')}\t{row.get('expiration', '')}")


def description_text(challenge):
    return (
        f"# {challenge['name']}\n\n"
        f"## Description\n{challenge['description']}\n\n"
        f"## Category\n{challenge['category']}\n\n"
        f"## Points\n{challenge['value']}\n\n"
    )


def scrape_challenges(url, headers, cookies, nofiles, nooverwrite, output_dir, http):
    response = api_get(http, f"{url}/api/v1/challenges", headers, cookies)
    if response.status_code == 403:
        print(f"[-] Access forbidden. ERROR: {response.json()['message']}")
        raise SystemExit(1)
    if response.status_code != 200:
        print(f"[-] Failed to retrieve challenges: {response.status_code} - {response.text}")
        raise SystemExit(1)

    challenges = response.json()["data"]
    print("[+] Challenges retrieved successfully.")
    for challenge in challenges:
        detail = api_get(http, f"{url}/api/v1/challenges/{challenge['id']}", headers, cookies)
        if detail.status_code != 200:
            print(
                f"[-] Failed to retrieve challenge data for {challenge['id']}: "
                f"{detail.status_code} - {detail.text}"
            )
            continue

        chall_data = detail.json()["data"]
        path = os.path.join(output_dir, chall_data["category"], chall_data["name"])
        os.makedirs(path, exist_ok=True)
        description_path = os.path.join(path, "description.md")
        if os.path.exists(description_path) and nooverwrite:
            print(
                f"[-] Description file already exists for challenge {challenge['name']}. "
                "Skipping because --nooverwrite is set."
            )
            continue

        with open(description_path, "w", encoding="utf-8") as desc_file:
            desc_file.write(description_text(chall_data))
        print(f"[+] Created description file for challenge {challenge['name']} at {description_path}")

        if nofiles:
            print(f"[-] Skipping file downloads for challenge {challenge['name']} as --nofiles is set.")
            continue

        for file_url in chall_data["files"]:
            file_data = api_get(http, f"{url}{file_url}", headers, cookies)
            if file_data.status_code != 200:
                print(
                    f"[-] Failed to download {file_url} for challenge {challenge['name']}: "
                    f"{file_data.status_code} - {file_data.text}"
                )
                continue
            file_name = os.path.basename(file_url.split("?")[0])
            file_path = os.path.join(path, file_name)
            with open(file_path, "wb") as handle:
                handle.write(file_data.content)
            print(f"[+] Downloaded {file_name} for challenge {challenge['name']}.")


def response_message(response):
    try:
        payload = response.json()
    except Exception:
        return response.text
    if isinstance(payload, dict) and payload.get("message"):
        return payload["message"]
    return response.text


def scoreboard_rows(response, challenges_requested):
    """Return standings, or None when a hidden board should not fail the run."""
    if response.status_code == 200:
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        return data if isinstance(data, list) else []
    message = response_message(response)
    if response.status_code == 403 and challenges_requested:
        print(f"[-] Scoreboard is hidden ({message}). Continuing because challenges were also requested.")
        return None
    print(f"[-] Failed to retrieve scoreboard: {response.status_code} - {message}")
    raise SystemExit(1)


def scoreboard_markdown(rows):
    lines = [
        "# Scoreboard",
        "",
        "| Pos | Name | Score | Bracket |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        name = str(row.get("name") or "").replace("|", "\\|")
        bracket = str(row.get("bracket_name") or "").replace("|", "\\|")
        lines.append(f"| {row.get('pos', '')} | {name} | {row.get('score', '')} | {bracket} |")
    return "\n".join(lines) + "\n"


def write_scoreboard(url, headers, cookies, output_dir, http, challenges_requested, now):
    response = api_get(http, f"{url}/api/v1/scoreboard", headers, cookies)
    rows = scoreboard_rows(response, challenges_requested)
    if rows is None:
        return
    os.makedirs(output_dir, exist_ok=True)
    document = {"fetched_at": now.isoformat(), "data": rows}
    json_path = os.path.join(output_dir, "scoreboard.json")
    md_path = os.path.join(output_dir, "scoreboard.md")
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)
        handle.write("\n")
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write(scoreboard_markdown(rows))
    print(f"[+] Wrote scoreboard to {json_path} and {md_path}")


def main(argv=None, env_path=".env", output_dir="output", http=requests, now=None, challenges_requested=True):
    args = build_parser().parse_args(argv)
    env = read_env(env_path)
    url, extra_headers, cookies = resolve_auth(args, env, http)
    headers = dict(HEADERS)
    headers.update(extra_headers)
    if args.list_tokens:
        list_tokens(url, headers, cookies, http)
        return
    if challenges_requested:
        scrape_challenges(url, headers, cookies, args.nofiles, args.nooverwrite, output_dir, http)
    if args.scoreboard:
        write_scoreboard(
            url,
            headers,
            cookies,
            output_dir,
            http,
            challenges_requested,
            now or datetime.now(timezone.utc),
        )


if __name__ == "__main__":
    main()
