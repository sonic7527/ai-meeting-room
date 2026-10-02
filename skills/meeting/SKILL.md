---
name: meeting
description: Start an AI meeting with the user plus Claude, GPT and/or Gemini (whichever are installed) in the local AI Meeting Room — starts the room in the background, opens a meeting on the current project and opens it in a new Chrome tab. Several meetings can run at once (one tab each). Use when the user says "meeting", "start a meeting", "let's ask GPT and Gemini", "roundtable", "have the AIs discuss / review this".
---

# Meeting (AI Meeting Room)

One command, three results: the room is running, the meeting exists, a new Chrome tab shows it. Do not ask the user to confirm details; take them from what they said and use defaults for the rest.

## 1. Find the install folder

Use the first folder containing `hub.py`: `$AI_MEETING_ROOM_DIR`, then `~/ai-meeting-room`.

## 2. Make sure the room is running

- Windows: `powershell -ExecutionPolicy Bypass -File "<folder>/start_bg.ps1"`
- macOS / Linux: `bash "<folder>/start_bg.sh"`

"already running" or "started" is fine. It keeps running after this conversation ends.

## 3. Write the meeting file (UTF-8, with the Write tool, in a temp/scratch folder)

```json
{"title": "short title",
 "topic": "background, the constraints the user already decided (in their words), what to decide",
 "project": "<git root of the current working folder, or the folder itself>",
 "lang": "en",
 "mode": "discuss",
 "lead": ""}
```

- `project`: **the project you are working in now** (`git rev-parse --show-toplevel`), unless the user names another.
- `lang`: `en` or `zh-TW`, matching the user's language.
- `mode`: `discuss` (default) or `review` when the user wants code checked.
- `lead`: `""` (equal discussion, everyone read-only, default) or the AI the user names as lead. The lead edits code in an isolated git worktree outside the project; push / deploy need the user's yes.
- `seats` (optional): which AIs to invite; omit to invite every AI installed on this computer.
- `seat_cfg` (optional): **only if the user asked for specific models.** Otherwise omit; each CLI uses its default.

## 4. Create the meeting and open the tab

`python "<folder>/open_meeting.py" "<meeting.json>"` (use `py` / `python3` as available; set `PYTHONIOENCODING=utf-8`).
It prints one JSON line: meeting id, URL, which AIs took their seats.

## 5. Tell the user (short)

Title, project, roles, URL. One line: "Type in the page to interject — the AIs answer you first. Click Close meeting to end it." If an AI failed to take its seat, say why.

## 6. Wait for the meeting to end in the background

Run with `run_in_background: true`:
```
until curl -s "http://127.0.0.1:7720/api/rooms/<url-encoded id>/messages?after=99999" | grep -q '"export"'; do sleep 15; done; echo closed
```
When notified, read `<project>/docs/meetings/<date>_<title>/transcript.md` and **report the results to the user first** (each AI's main points, agreements, disagreements, what the user must decide). Give your own view on other AIs' points. The user makes the decisions.
