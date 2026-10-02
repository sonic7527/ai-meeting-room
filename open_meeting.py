#!/usr/bin/env python3

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

USAGE = """Create a meeting and open it in a new browser tab (Chrome if found).

Usage:  python open_meeting.py meeting.json

meeting.json (UTF-8):
  {"title": "...", "topic": "...", "project": "/path/to/project",
   "lang": "en" | "zh-TW",
   "mode": "discuss" | "review",
   "lead": "" | "Claude" | "GPT" | "Gemini",
   "seats": ["Claude", "GPT", "Gemini"],
   "seat_cfg": {"GPT": {"model": "", "effort": ""}}}

"seats" and "seat_cfg" are optional: without them every installed AI is invited with its default model.
Pass non-ASCII text through the file, not the command line (Windows shells may re-encode it).
"""
BASE = f"http://127.0.0.1:{os.environ.get('MEETING_PORT', '7720')}"


def open_tab(url):
    if sys.platform == "darwin" and os.path.isdir("/Applications/Google Chrome.app"):
        subprocess.Popen(["open", "-a", "Google Chrome", url])
        return "Chrome"
    cands = [os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
             os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
             os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")] if os.name == "nt" else []
    exe = next((c for c in cands if os.path.isfile(c)), None) or shutil.which("google-chrome") or shutil.which("chrome")
    if exe:
        subprocess.Popen([exe, "--new-tab", url])
        return "Chrome"
    webbrowser.open_new_tab(url)
    return "default browser"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2:
        print(USAGE)
        sys.exit(2)
    with open(sys.argv[1], encoding="utf-8") as f:
        body = json.load(f)
    body.setdefault("project", os.getcwd())
    req = urllib.request.Request(BASE + "/api/rooms", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        r = json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        print("failed:", json.load(e).get("error"))
        sys.exit(1)
    except urllib.error.URLError:
        print(f"Cannot reach the meeting room at {BASE}. Start it first (start_bg.ps1 / start_bg.sh).")
        sys.exit(1)
    url = BASE + "/#" + urllib.parse.quote(r["id"])
    print(json.dumps({"id": r["id"], "url": url, "seats": r["seats"], "opened_in": open_tab(url)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
