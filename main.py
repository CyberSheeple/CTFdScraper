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
        help="Also save output/scoreboard.json, output/scoreboard.md, and offline output/scoreboard.html",
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


def api_get(http, url, headers, cookies, params=None):
    kwargs = {"headers": headers}
    if cookies:
        kwargs["cookies"] = cookies
    if params:
        kwargs["params"] = params
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
    """Return standings, or None when score visibility should not fail the run."""
    if response.status_code == 200:
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        return data if isinstance(data, list) else []
    message = response_message(response)
    # Private and Hidden return 403. Admins Only returns 404. See score visibility docs.
    if response.status_code in (403, 404) and challenges_requested:
        print(
            f"[-] Scoreboard is not visible to this account ({message}). "
            "Continuing because challenges were also requested."
        )
        return None
    print(f"[-] Failed to retrieve scoreboard: {response.status_code} - {message}")
    raise SystemExit(1)


def payload_data(response):
    if response.status_code != 200:
        return None
    try:
        payload = response.json()
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload.get("data")


def scoreboard_detail(response):
    """Return a place-keyed graph payload, or None when the endpoint did not succeed."""
    data = payload_data(response)
    return data if isinstance(data, dict) else None


def list_data(response):
    data = payload_data(response)
    return data if isinstance(data, list) else None


def fetch_viewer(url, headers, cookies, http, rows):
    """Identify the signed-in user so the rivals window can be centered on them."""
    response = api_get(http, f"{url}/api/v1/users/me", headers, cookies)
    data = payload_data(response)
    if not isinstance(data, dict) or data.get("id") is None:
        return None
    account_type = ""
    for row in rows:
        if row.get("account_type"):
            account_type = str(row["account_type"]).lower()
            break
    account_id = data.get("team_id") if account_type == "team" else data.get("id")
    return {
        "user_id": data.get("id"),
        "name": data.get("name") or "",
        "team_id": data.get("team_id"),
        "account_id": account_id,
        "account_type": account_type or "user",
    }


def remember_series(series, detail):
    if not isinstance(detail, dict):
        return
    for place in detail.values():
        if not isinstance(place, dict) or place.get("id") is None:
            continue
        series[str(place["id"])] = {
            "id": place.get("id"),
            "name": place.get("name") or "",
            "solves": place.get("solves") or [],
        }


def points_from_history(solves, awards):
    points = []
    for solve in solves or []:
        if not isinstance(solve, dict):
            continue
        challenge = solve.get("challenge") if isinstance(solve.get("challenge"), dict) else {}
        value = challenge.get("value", solve.get("value"))
        if solve.get("date") is None or value is None:
            continue
        points.append({"value": value, "date": solve["date"]})
    for award in awards or []:
        if not isinstance(award, dict) or award.get("date") is None or award.get("value") is None:
            continue
        points.append({"value": award["value"], "date": award["date"]})
    points.sort(key=lambda item: str(item["date"]))
    return points


def fetch_account_series(url, headers, cookies, http, row):
    account_id = row.get("account_id")
    kind = "teams" if str(row.get("account_type") or "").lower() == "team" else "users"
    solves = list_data(api_get(http, f"{url}/api/v1/{kind}/{account_id}/solves", headers, cookies))
    awards = list_data(api_get(http, f"{url}/api/v1/{kind}/{account_id}/awards", headers, cookies))
    if solves is None and awards is None:
        return None
    return {
        "id": account_id,
        "name": row.get("name") or "",
        "solves": points_from_history(solves or [], awards or []),
    }


def fetch_scoreboard_graphs(url, headers, cookies, http, rows):
    """Top graphs, plus per-account history for the rivals and full graphs.

    CTFd's ``/scoreboard/top/<count>`` stops at 50. Accounts outside that slice are
    filled from their public solves and awards.
    """
    series = {}
    response = api_get(http, f"{url}/api/v1/scoreboard/top/50", headers, cookies)
    detail = scoreboard_detail(response)
    if detail is None:
        print(
            f"[-] Score graph is unavailable ({response.status_code}). "
            "The offline scoreboard will list standings only."
        )
        detail = {}
    remember_series(series, detail)
    brackets = {}
    seen = []
    for row in rows:
        bracket_id = row.get("bracket_id")
        if bracket_id is None or bracket_id in seen:
            continue
        seen.append(bracket_id)
        bracket_response = api_get(
            http,
            f"{url}/api/v1/scoreboard/top/10",
            headers,
            cookies,
            params={"bracket_id": bracket_id},
        )
        bracket_detail = scoreboard_detail(bracket_response)
        if bracket_detail is None:
            print(
                f"[-] Score graph for bracket {bracket_id} is unavailable "
                f"({bracket_response.status_code})."
            )
            continue
        brackets[str(bracket_id)] = bracket_detail
        remember_series(series, bracket_detail)
    missing = 0
    for row in rows:
        account_id = row.get("account_id")
        if account_id is None or str(account_id) in series:
            continue
        account_series = fetch_account_series(url, headers, cookies, http, row)
        if account_series is None:
            missing += 1
            continue
        series[str(account_id)] = account_series
    if missing:
        print(f"[-] Score history is unavailable for {missing} accounts. Those lines are omitted from the graph.")
    return {"top": {"all": detail, "brackets": brackets}, "series": series}


SCOREBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Scoreboard</title>
<style>
  :root { color-scheme: light dark; }
  body { margin: 0; font-family: system-ui, sans-serif; line-height: 1.4; }
  header, main { max-width: 960px; margin: 0 auto; padding: 1.25rem; }
  header { padding-bottom: 0; }
  h1 { margin: 0 0 .25rem; }
  .meta { margin: 0; opacity: .7; }
  .tabs, .pills, .pager { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; margin: 1rem 0; }
  .tabs button, .pills button, .pager button { border: 1px solid #888; background: transparent; border-radius: 999px; padding: .35rem .8rem; cursor: pointer; }
  .tabs button.active, .pills button.active { background: #1f6feb; color: #fff; border-color: #1f6feb; }
  .note { margin: 0 0 1rem; opacity: .75; }
  svg { width: 100%; height: 320px; display: block; }
  .legend { display: flex; flex-wrap: wrap; gap: .75rem 1rem; max-height: 8rem; overflow: auto; margin: .5rem 0 1rem; font-size: .9rem; }
  .swatch { display: inline-block; width: .75rem; height: .75rem; margin-right: .35rem; vertical-align: middle; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: .55rem .7rem; text-align: center; }
  td.name, th.name { text-align: left; }
  tbody tr:nth-child(even) { background: rgba(127, 127, 127, .12); }
  tbody tr.self { background: rgba(31, 111, 235, .22); }
  .badge { display: inline-block; margin-left: .5rem; padding: .05rem .4rem; border-radius: .4rem; background: rgba(127, 127, 127, .25); font-size: .8rem; }
  .members { display: block; opacity: .7; font-size: .85rem; }
  .empty { text-align: center; opacity: .7; }
</style>
</head>
<body>
<header>
  <h1>Scoreboard</h1>
  <p class="meta" id="fetched"></p>
</header>
<main>
  <div id="tabs" class="tabs"></div>
  <div id="graph"></div>
  <div id="pills" class="pills"></div>
  <p id="note" class="note"></p>
  <div id="board"></div>
  <div id="pager" class="pager"></div>
</main>
<script type="application/json" id="scoreboard-data">/*SCOREBOARD*/</script>
<script>
(function () {
  var data = JSON.parse(document.getElementById("scoreboard-data").textContent);
  var standings = data.data || [];
  var active = null;
  var view = "top";
  var page = 0;
  var PAGE_SIZE = 25;

  function text(parent, value) {
    parent.appendChild(document.createTextNode(value == null ? "" : String(value)));
  }

  function color(name) {
    var hash = 0;
    var i;
    for (i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
    return "hsl(" + (hash % 360) + " 65% 45%)";
  }

  function brackets() {
    var seen = {};
    var list = [];
    standings.forEach(function (row) {
      if (row.bracket_id == null || seen[row.bracket_id]) return;
      seen[row.bracket_id] = true;
      list.push({id: row.bracket_id, name: row.bracket_name || String(row.bracket_id)});
    });
    return list;
  }

  function filtered() {
    return standings.filter(function (row) {
      return active == null || String(row.bracket_id) === String(active);
    });
  }

  function rivalWindow(rows) {
    var viewer = data.viewer;
    if (!viewer || viewer.account_id == null) {
      return {rows: [], reason: "This snapshot has no signed-in team or user, so the rivals window is unavailable."};
    }
    var index = -1;
    var i;
    for (i = 0; i < rows.length; i++) {
      if (String(rows[i].account_id) === String(viewer.account_id)) index = i;
    }
    if (index < 0) return {rows: [], reason: "Your account is not on this scoreboard."};
    return {
      rows: rows.slice(Math.max(0, index - 5), Math.min(rows.length, index + 6)),
      reason: "Five places above and below " + (viewer.name || "you") + "."
    };
  }

  function selection() {
    var rows = filtered();
    if (view === "top") return {rows: rows.slice(0, 10), reason: ""};
    if (view === "rivals") return rivalWindow(rows);
    return {rows: rows, reason: ""};
  }

  function lineFrom(place) {
    if (!place) return null;
    var total = 0;
    var points = (place.solves || []).map(function (solve) {
      total += Number(solve.value) || 0;
      return {t: Date.parse(solve.date), y: total};
    }).filter(function (point) { return !isNaN(point.t); });
    if (!points.length) return null;
    return {name: place.name || "", color: color((place.name || "") + (place.id || "")), points: points};
  }

  function series() {
    var chosen = selection().rows;
    if (view === "top") {
      var top = data.top || {};
      var places = active == null ? (top.all || {}) : ((top.brackets || {})[String(active)] || {});
      var keys = Object.keys(places).sort(function (a, b) { return Number(a) - Number(b); }).slice(0, 10);
      return keys.map(function (key) { return lineFrom(places[key]); }).filter(Boolean);
    }
    return chosen.map(function (row) {
      return lineFrom((data.series || {})[String(row.account_id)]);
    }).filter(Boolean);
  }

  function svgEl(name) {
    return document.createElementNS("http://www.w3.org/2000/svg", name);
  }

  function renderGraph() {
    var host = document.getElementById("graph");
    host.textContent = "";
    var lines = series();
    if (!lines.length) return;
    var width = 800;
    var height = 320;
    var pad = {left: 52, right: 16, top: 16, bottom: 36};
    var minT = Infinity;
    var maxT = -Infinity;
    var maxY = 0;
    lines.forEach(function (line) {
      line.points.forEach(function (point) {
        if (point.t < minT) minT = point.t;
        if (point.t > maxT) maxT = point.t;
        if (point.y > maxY) maxY = point.y;
      });
    });
    if (minT === maxT) maxT = minT + 1;
    if (maxY === 0) maxY = 1;
    function x(t) {
      return pad.left + (t - minT) / (maxT - minT) * (width - pad.left - pad.right);
    }
    function y(value) {
      return pad.top + (1 - value / maxY) * (height - pad.top - pad.bottom);
    }
    var svg = svgEl("svg");
    svg.setAttribute("viewBox", "0 0 " + width + " " + height);
    svg.setAttribute("role", "img");
    var label = svgEl("title");
    text(label, view === "top" ? "Top 10 scores" : view === "rivals" ? "Rivals" : "Full scoreboard");
    svg.appendChild(label);
    var axis = svgEl("path");
    axis.setAttribute("d", "M" + pad.left + " " + pad.top + "V" + (height - pad.bottom) + "H" + (width - pad.right));
    axis.setAttribute("fill", "none");
    axis.setAttribute("stroke", "currentColor");
    svg.appendChild(axis);
    lines.forEach(function (line) {
      var path = svgEl("polyline");
      path.setAttribute("fill", "none");
      path.setAttribute("stroke", line.color);
      path.setAttribute("stroke-width", "2");
      path.setAttribute("points", line.points.map(function (point) {
        return x(point.t) + "," + y(point.y);
      }).join(" "));
      svg.appendChild(path);
    });
    var maxLabel = svgEl("text");
    maxLabel.setAttribute("x", "4");
    maxLabel.setAttribute("y", pad.top + 4);
    maxLabel.setAttribute("font-size", "12");
    maxLabel.setAttribute("fill", "currentColor");
    text(maxLabel, String(maxY));
    svg.appendChild(maxLabel);
    host.appendChild(svg);
    var legend = document.createElement("div");
    legend.className = "legend";
    lines.forEach(function (line) {
      var item = document.createElement("span");
      var swatch = document.createElement("span");
      swatch.className = "swatch";
      swatch.style.background = line.color;
      item.appendChild(swatch);
      text(item, line.name);
      legend.appendChild(item);
    });
    host.appendChild(legend);
  }

  function rankOf(row, rows) {
    var i;
    for (i = 0; i < rows.length; i++) if (rows[i] === row) return i + 1;
    return "";
  }

  function renderTable() {
    var host = document.getElementById("board");
    var rows = filtered();
    var chosen = selection();
    var tableRows = chosen.rows;
    if (view === "full") tableRows = chosen.rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
    host.textContent = "";
    var note = document.getElementById("note");
    note.textContent = "";
    if (chosen.reason) text(note, chosen.reason);
    if (!tableRows.length) {
      var empty = document.createElement("p");
      empty.className = "empty";
      text(empty, chosen.reason ? "" : "Scoreboard is empty");
      if (!chosen.reason) host.appendChild(empty);
      return;
    }
    var table = document.createElement("table");
    var head = document.createElement("tr");
    ["Place", rows[0].account_type || "Account", "Score"].forEach(function (label, index) {
      var cell = document.createElement("th");
      if (index === 1) cell.className = "name";
      text(cell, label);
      head.appendChild(cell);
    });
    var thead = document.createElement("thead");
    thead.appendChild(head);
    table.appendChild(thead);
    var body = document.createElement("tbody");
    tableRows.forEach(function (row) {
      var tr = document.createElement("tr");
      var viewer = data.viewer;
      if (viewer && viewer.account_id != null && String(row.account_id) === String(viewer.account_id)) {
        tr.className = "self";
      }
      var place = document.createElement("th");
      text(place, rankOf(row, rows));
      var name = document.createElement("td");
      name.className = "name";
      text(name, row.name || "");
      if (row.bracket_name) {
        var badge = document.createElement("span");
        badge.className = "badge";
        text(badge, row.bracket_name);
        name.appendChild(badge);
      }
      if (row.members && row.members.length) {
        var members = document.createElement("span");
        members.className = "members";
        text(members, row.members.map(function (member) {
          return (member.name || "") + " (" + (member.score == null ? "" : member.score) + ")";
        }).join(", "));
        name.appendChild(members);
      }
      var score = document.createElement("td");
      text(score, row.score == null ? "" : row.score);
      tr.appendChild(place);
      tr.appendChild(name);
      tr.appendChild(score);
      body.appendChild(tr);
    });
    table.appendChild(body);
    host.appendChild(table);
  }

  function renderPills() {
    var host = document.getElementById("pills");
    var items = brackets();
    host.textContent = "";
    if (!items.length) return;
    function add(label, id) {
      var button = document.createElement("button");
      button.type = "button";
      if (String(active) === String(id) || (active == null && id == null)) button.className = "active";
      text(button, label);
      button.addEventListener("click", function () {
        active = id;
        page = 0;
        render();
      });
      host.appendChild(button);
    }
    add("All", null);
    items.forEach(function (item) { add(item.name, item.id); });
  }

  function renderTabs() {
    var host = document.getElementById("tabs");
    host.textContent = "";
    [["top", "Top 10"], ["rivals", "Rivals \u00b15"], ["full", "Full"]].forEach(function (item) {
      var button = document.createElement("button");
      button.type = "button";
      if (view === item[0]) button.className = "active";
      text(button, item[1]);
      button.addEventListener("click", function () {
        view = item[0];
        page = 0;
        render();
      });
      host.appendChild(button);
    });
  }

  function renderPager() {
    var host = document.getElementById("pager");
    host.textContent = "";
    if (view !== "full") return;
    var total = selection().rows.length;
    var pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    if (page > pages - 1) page = pages - 1;
    if (pages < 2) return;
    function add(label, next, disabled) {
      var button = document.createElement("button");
      button.type = "button";
      button.disabled = disabled;
      text(button, label);
      button.addEventListener("click", function () {
        page = next;
        render();
      });
      host.appendChild(button);
    }
    add("Previous", page - 1, page === 0);
    var status = document.createElement("span");
    text(status, "Page " + (page + 1) + " of " + pages);
    host.appendChild(status);
    add("Next", page + 1, page >= pages - 1);
  }

  function render() {
    renderTabs();
    renderGraph();
    renderPills();
    renderTable();
    renderPager();
  }

  text(document.getElementById("fetched"), "Snapshot " + (data.fetched_at || ""));
  render();
})();
</script>
</body>
</html>
"""


def scoreboard_html(document):
    payload = json.dumps(document, ensure_ascii=True).replace("<", "\\u003c")
    return SCOREBOARD_HTML.replace("/*SCOREBOARD*/", payload)


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
    graphs = fetch_scoreboard_graphs(url, headers, cookies, http, rows)
    document = {
        "fetched_at": now.isoformat(),
        "data": rows,
        "viewer": fetch_viewer(url, headers, cookies, http, rows),
        "top": graphs["top"],
        "series": graphs["series"],
    }
    json_path = os.path.join(output_dir, "scoreboard.json")
    md_path = os.path.join(output_dir, "scoreboard.md")
    html_path = os.path.join(output_dir, "scoreboard.html")
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)
        handle.write("\n")
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write(scoreboard_markdown(rows))
    with open(html_path, "w", encoding="utf-8") as handle:
        handle.write(scoreboard_html(document))
    print(f"[+] Wrote scoreboard to {json_path}, {md_path}, and {html_path}")


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
