<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/python-3.7%2B-blue?logo=python&logoColor=white">
  <img alt="License" src="https://img.shields.io/github/license/ha1fdan/CTFdScraper?color=blueviolet">
  <img alt="Stars" src="https://img.shields.io/github/stars/ha1fdan/CTFdScraper?style=social">
  <img alt="Last Commit" src="https://img.shields.io/github/last-commit/ha1fdan/CTFdScraper">
  <img alt="Issues" src="https://img.shields.io/github/issues/ha1fdan/CTFdScraper">
<img alt="PRs" src="https://img.shields.io/github/issues-pr/ha1fdan/CTFdScraper">
</p>


# 🕵️‍♂️ CTFd Challenge Scraper

A simple Python 3 tool to automatically download challenges and files from any CTFd instance.

Supports:
- Access token, session cookie, **or** username/password login
- `.env` or CLI-based usage
- Downloads challenge descriptions and files
- Skips existing files if needed

---

## 🚀 Quick Start

```bash
# Clone the repo
git clone https://github.com/ha1fdan/CTFdScraper.git
cd CTFdScraper

# Set up a virtual environment (optional but recommended)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
````

---

## ⚙️ Configuration

You can either use a `.env` file **or** pass arguments via the command line.

### Option 1: Using `.env`

Create a `.env` file in the root folder:

```
CTFD_TOKEN=your_access_token
SESSION=your_session_cookie              # OR use USERNAME + PASSWORD below
USERNAME=your_username
PASSWORD=your_password
URL=https://your-ctfd-url.com
```

Create the token in CTFd under Settings, then Access Tokens, and store it as `CTFD_TOKEN`. Requests send it as `Authorization: Token <value>` and keep `Content-Type: application/json`. CTFd applies that header on JSON requests. The REST API section below links the docs this follows. The token is preferred over a session cookie, and over a username and password. Command-line credentials replace whatever is in `.env`.

Then simply run:

```bash
python3 main.py
```

---

### Option 2: Using command-line args

```bash
python3 main.py \
  --username your_username \
  --password your_password \
  --url https://your-ctfd-url.com
```

Or with a session cookie:

```bash
python3 main.py \
  --session your_session_cookie \
  --url https://your-ctfd-url.com
```

Or with an access token:

```bash
python3 main.py \
  --token your_access_token \
  --url https://your-ctfd-url.com
```

List token metadata (id, type, expiration) without downloading challenges. The secret value is not printed.

```bash
python3 main.py --token your_access_token --url https://your-ctfd-url.com --list-tokens
```

---

## 🧰 Extra Options

* `--nofiles` – Skip downloading files, just save challenge descriptions.
* `--nooverwrite` – Don't overwrite an existing `description.md`, and skip that challenge's files.
* `--scoreboard` – Also save the standings, including `scoreboard.html` for offline viewing. Open that file in a browser with no network: it recreates the standings table, bracket filters, and the top-10 score graph. Works with `.env` or command-line credentials. [Score Visibility](https://docs.ctfd.io/docs/settings/visibility-settings/#score-visibility) controls who can read them: Public, Private, Hidden, or Admins Only. A 403 (Private or Hidden) or 404 (Admins Only) is a warning when challenges were downloaded too, and a failure when the scoreboard was the only request.

These flags apply whether you authenticate with `.env` or with command-line arguments.

---

## 🔌 REST API

Challenge downloads, `--scoreboard`, and `--list-tokens` call CTFd's REST API under `/api/v1`.

The docs site keeps a single current copy of the guide and the endpoint reference:

* [Using CTFd's REST API](https://docs.ctfd.io/tutorials/api/using-ctfd-api/) shows `Authorization: Token <access token>` with `Content-Type: application/json`.
* [API getting started](https://docs.ctfd.io/docs/api/getting-started/) covers access tokens and the required headers.
* [API endpoint reference](https://docs.ctfd.io/docs/api/redoc/) lists the `/api/v1` operations.

This scraper follows that contract as shipped in [CTFd 3.8.9](https://github.com/CTFd/CTFd/releases/tag/3.8.9) (2026-10-21):

* Token header, honored when the request is JSON: [`CTFd/utils/initialization/__init__.py`](https://github.com/CTFd/CTFd/blob/3.8.9/CTFd/utils/initialization/__init__.py#L341-L355)
* `GET /api/v1/tokens`: [`CTFd/api/v1/tokens.py`](https://github.com/CTFd/CTFd/blob/3.8.9/CTFd/api/v1/tokens.py)
* `GET /api/v1/challenges`: [`CTFd/api/v1/challenges.py`](https://github.com/CTFd/CTFd/blob/3.8.9/CTFd/api/v1/challenges.py)
* `GET /api/v1/scoreboard` and `GET /api/v1/scoreboard/top/10`: [`CTFd/api/v1/scoreboard.py`](https://github.com/CTFd/CTFd/blob/3.8.9/CTFd/api/v1/scoreboard.py). The list is the standings table. `top/10` is the score graph, requested again with `bracket_id` for each bracket. Who may call them is [Score Visibility](https://docs.ctfd.io/docs/settings/visibility-settings/#score-visibility), enforced in [`check_score_visibility`](https://github.com/CTFd/CTFd/blob/3.8.9/CTFd/utils/decorators/visibility.py#L16-L53): Public returns the standings, Private returns them for a logged-in account and 403 otherwise, Hidden returns 403 for non-admins, and Admins Only returns 404 for non-admins. The same routes also check account visibility.

A running instance publishes the spec for its own build at `/api/v1/swagger.json`. The public demo spec is [demo.ctfd.io/api/v1/swagger.json](https://demo.ctfd.io/api/v1/swagger.json).

---

## 📁 Output Structure

All content will be saved under the `output/` directory like this:

```
output/
├── scoreboard.json    # with --scoreboard
├── scoreboard.md      # with --scoreboard
├── scoreboard.html    # with --scoreboard; open offline in a browser
└── category/
    └── challenge_name/
        ├── description.md
        └── challenge_file.ext
```

---

## 📦 Requirements

* Python 3.7+
* Libraries in `requirements.txt`:

  * `requests`
  * `beautifulsoup4`
  * `python-dotenv`

---

## 🙏 Credits

Made for automation lovers & CTF enthusiasts.
Feel free to fork and adapt for your own CTF team setup!

---
