# Retarget checkouts from ha1fdan to this fork

This repository is [CyberSheeple/CTFdScraper](https://github.com/CyberSheeple/CTFdScraper), a fork of [ha1fdan/CTFdScraper](https://github.com/ha1fdan/CTFdScraper). Use this note when a checkout, README, or script still treats the ha1fdan repository as origin.

This document stays on the fork. Do not open it, or the README badge change that ships with it, against ha1fdan. It tells people to leave that repository.

## Inventory

Checked 2026-11-12.

The only GitHub fork of `ha1fdan/CTFdScraper` is `CyberSheeple/CTFdScraper`. Public code search finds `ha1fdan/CTFdScraper` in that upstream README (shields and the clone URL) and, before this branch, in this fork's README for the same reason.

These CyberSheeple repositories do not clone or shell out to `ha1fdan/CTFdScraper`:

| Repository | Why it is not a consumer |
| --- | --- |
| `bsidesnyc-solver` | Own CTFd client in `tools/ctfd_client.py`, plus `tools/scrape_ctfd.py` and `tools/scrape_scoreboard.py` |
| `huntress-solver` | CourseStack and Game Master, not this script |
| `pumpcon-solver` | Solver checkout. No ha1fdan remote or scraper clone |
| `rfctf-solver` | Solver checkout. No ha1fdan remote or scraper clone |
| `solver-plugin` | Shared skills. It does not vendor this script |

Do not rewrite `bsidesnyc-solver` as part of retargeting this fork. If a later repository shells out to this scraper, pin `https://github.com/CyberSheeple/CTFdScraper.git` and keep challenge files at `output/<category>/<name>/description.md` with attachments beside that file.

Re-check before assuming the list is still empty:

```bash
gh api repos/ha1fdan/CTFdScraper/forks --jq '.[].full_name'
gh search code 'ha1fdan/CTFdScraper' --limit 50
gh search code 'github.com/ha1fdan/CTFdScraper' --limit 50
```

Private repositories are missing from `gh search code` unless the token can read them. For each CyberSheeple solver repo, also search the tree for `ha1fdan` and `CTFdScraper`.

## Retarget a local checkout

Use this when `git remote get-url origin` prints `https://github.com/ha1fdan/CTFdScraper.git` or `git@github.com:ha1fdan/CTFdScraper.git`.

```bash
git remote set-url origin https://github.com/CyberSheeple/CTFdScraper.git
git fetch origin
git remote -v
git log --oneline HEAD..origin/main
```

Review that log before merging or resetting. Replace README shields and clone URLs in the same pass. A badge URL is a consumer too: `https://img.shields.io/github/stars/ha1fdan/CTFdScraper` should become `https://img.shields.io/github/stars/CyberSheeple/CTFdScraper`.

Leave the feature branches below un-rebased. Each one starts from the same commit as ha1fdan `main`, so any one of them can be opened upstream by itself. Rebasing one onto another would make that upstream pull request contain both features. They all edit `main.py`, so merging more than one on this fork will conflict. Suggested merge order here is flags, access tokens, scoreboard, notifications, then this note. Resolve those conflicts on the fork without rewriting the feature branches.

| Fork pull request | Branch | Open against ha1fdan? |
| --- | --- | --- |
| CLI flags | `cursor/fix-cli-flags-9022` | Yes. Compare `main...CyberSheeple:cursor/fix-cli-flags-9022` |
| Access tokens | `cursor/access-tokens-9022` | Yes. Compare `main...CyberSheeple:cursor/access-tokens-9022` |
| Scoreboard | `cursor/scrape-scoreboard-9022` | Yes. Compare `main...CyberSheeple:cursor/scrape-scoreboard-9022` |
| Notifications | `cursor/scrape-notifications-9022` | Yes. Compare `main...CyberSheeple:cursor/scrape-notifications-9022` |
| This note | `cursor/fork-regression-9022` | No |

Upstream compare URL shape:

```text
https://github.com/ha1fdan/CTFdScraper/compare/main...CyberSheeple:<branch>?expand=1
```

## Checklist

Run the sections for the branches you actually merged. A partial set opened upstream still has a test list. Existing `.env` session and password logins must still scrape challenges on every branch. Token values never land in stdout or under `output/`.

### Flags (`cursor/fix-cli-flags-9022`)

`--nofiles` and `--nooverwrite` now do what the README already describes, including when `.env` is present.

- `--nofiles` writes `description.md` and does not download attachments.
- `--nooverwrite` leaves an existing `description.md` in place and skips that challenge's files.
- A run with neither flag still writes `output/<category>/<name>/description.md` and the attachment beside it.

### Access tokens (`cursor/access-tokens-9022`)

- `ACCESS_TOKEN` or `CTFD_TOKEN` in `.env`, or `--token`, sends `Authorization: Token <value>` and `Content-Type: application/json`.
- A token is used before a session cookie, and a session cookie before a username and password. Command-line credentials replace `.env`.
- Password login continues only after a redirect and a `session` cookie.
- `--list-tokens` prints id, type, and expiration, then exits. It does not scrape challenges and does not print the secret.

### Scoreboard (`cursor/scrape-scoreboard-9022`)

- Without `--scoreboard`, the run does not request `/api/v1/scoreboard` and does not write scoreboard files.
- With `--scoreboard`, the run writes `output/scoreboard.json` (raw `data` plus `fetched_at`) and `output/scoreboard.md` (position, name, score, bracket).
- A hidden scoreboard (HTTP 403) warns and continues when challenges were also requested. It exits non-zero when the scoreboard was the only request.

### Notifications (`cursor/scrape-notifications-9022`)

- Without `--notifications`, the run does not request `/api/v1/notifications` and does not write notification files.
- With `--notifications`, the run writes `output/notifications.json` and `output/notifications.md` with id, title, date, and content.
- `--since-id N` sends `since_id`. This branch does not scrape the scoreboard.
