# AI Meeting Room

**Put Claude, GPT and Gemini in one room with you.** Each AI speaks for itself, you watch the discussion live in your browser and can interject at any time. Nothing is relayed by hand, and nothing leaves your computer except the AIs' own calls to their providers.

[繁體中文說明](README.zh-TW.md)

- **Uses the subscriptions you already have.** Claude runs through Claude Code (your Claude account), GPT through OpenAI Codex (your ChatGPT account), Gemini through Antigravity CLI (your Google account). No API keys.
- **Auto-detects** which of the three are installed and signed in. Nobody joins until you click **Invite**; invite or dismiss any AI at any time.
- **You are the host.** Interjections are answered first, every host message shows who has replied, the AIs never end the meeting on their own, and they pause after 8 messages in a row without you. A ✕ rejection only marks that version — the AIs wait until you have reviewed the rest and say what to change; an explicit change request is acted on immediately.
- **Chat-app feel.** Right-click any message to reply to it, reject (✕) or adopt (✓) it in one click; Enter sends, Shift+Enter adds a line.
- **Mock-ups right in the conversation.** An AI can post a self-contained HTML page with its message; it is shown inline and stays interactive (animations, buttons, dragging) — no URLs to open.
- **Same project, same context.** Pick a folder; every AI reads the same files (CLAUDE.md, AGENTS.md, GEMINI.md, README) before speaking.
- **Lead and assistants.** Optionally make one AI the lead: it does all code changes and git commits **in an isolated git worktree outside your project**; the others review and do read-only tasks it assigns.
- **Per-AI model and reasoning effort**, changeable mid-meeting and remembered for next time. Claude offers each family name (always the newest version, with the current version shown) and fixed versions.
- **Several meetings at once**, one browser tab each; delete old meetings from the list.
- **Self-healing.** An AI that stops unexpectedly is brought back automatically, unless you removed it; one that hits its usage limit leaves the meeting automatically (the message shows when the limit resets) and does not keep retrying — click Invite to bring it back; an AI whose model ends its turn after each reply (instead of waiting for the next message) is quietly started again, so any model can stay in the meeting; after a restart, open meetings get their AIs back.
- **Transcripts saved into your project** (`docs/meetings/<date>_<title>/transcript.md`) when you close the meeting. Saved meetings stay readable in the sidebar under **Saved meetings (read-only)** even after the room itself has been deleted.
- **Only adopted attachments are kept**: mock-ups and images you marked ✓ plus the last one nobody rejected are copied out; everything else (including ✕ rejected versions) is left out and marked in the transcript, so the folder stays small.
- **Clean-up after a conclusion**: the `開會` skill tells Claude, once a meeting has reached a conclusion, to move what the final work actually uses (source images, scripts, approved designs) into the project, check it can be rebuilt, then send the meeting's `rooms/<id>` and `seats/<id>` folders (draft images, trial videos, AI logs) to the recycle bin and drop superseded files from the export folder.
- English and Traditional Chinese UI and meeting language.
- One Python file, standard library only. Runs on `127.0.0.1` only.

## Requirements

- Python 3.9+
- git (only for the lead mode)
- At least one of:

| Seat | Install | Sign in |
|---|---|---|
| Claude | [Claude Code](https://claude.com/claude-code) (`claude` CLI, or the Claude desktop app which bundles it) | your Claude account |
| GPT | [OpenAI Codex](https://openai.com/codex) (desktop app or `npm i -g @openai/codex`) | your ChatGPT account |
| Gemini | Antigravity CLI — Windows: `irm https://antigravity.google/cli/install.ps1 \| iex` ([docs](https://antigravity.google/docs/cli/headless/)) | run `agy` once, sign in with Google |

> Gemini CLI no longer works with personal Google accounts (since June 2026); Antigravity CLI (`agy`) replaced it. This project uses `agy`.

## Quick start

```bash
git clone https://github.com/sonic7527/ai-meeting-room ~/ai-meeting-room
```

Start the room in the background:

```bash
# Windows
powershell -ExecutionPolicy Bypass -File ~/ai-meeting-room/start_bg.ps1
# macOS / Linux
bash ~/ai-meeting-room/start_bg.sh
```

Open <http://127.0.0.1:7720/>, click **New meeting**, pick the project, write the topic, **Start meeting**, then **Invite** the AIs you want.

### Updating

```bash
git -C ~/ai-meeting-room pull
# Windows
powershell -ExecutionPolicy Bypass -File ~/ai-meeting-room/start_bg.ps1 -Restart
# macOS / Linux
bash ~/ai-meeting-room/start_bg.sh --restart
```

Open meetings keep going: their AIs rejoin automatically and re-read the conversation.

### One-time setup for Gemini

Antigravity CLI runs in the background and cannot ask you for permission, so the meeting tools must be allowed in its settings. In the **Invite** (or **New meeting**) dialog, click **Allow meeting tools** under Gemini. It adds exactly two rules to `~/.gemini/antigravity-cli/settings.json` — `mcp(meeting/*)` (the meeting tools) and `read_url(*)` (so it can open links you paste) — nothing else. All three AIs can read web pages: Claude opens pages directly, Gemini opens them with `read_url`, GPT uses Codex web search (search results, which may lag behind the live page). Antigravity model names usually carry the effort already (e.g. `gemini-3.8-flash-high`); for those the room does not pass a separate effort, which would make `agy` refuse to start.

### Optional: the `meeting` command for Claude Code

Link `skills/meeting` (English) or `skills/開會` (Chinese) into `~/.claude/skills/` so that `git pull` also updates the command:

```bash
# Windows (PowerShell, no admin needed)
New-Item -ItemType Junction -Path "$HOME\.claude\skills\meeting" -Target "$HOME\ai-meeting-room\skills\meeting"
# macOS / Linux
ln -s ~/ai-meeting-room/skills/meeting ~/.claude/skills/meeting
```

Then just tell Claude "start a meeting about …": it starts the room, opens an empty meeting on the current project in a new Chrome tab, waits until you close it and reports the result. If you cloned somewhere other than `~/ai-meeting-room`, set `AI_MEETING_ROOM_DIR`.

## How it works

```
 you (browser) ──▶ ┌──────────────────────────────┐ ◀── Claude  (claude -p, MCP over HTTP)
                   │  hub.py  127.0.0.1:7720       │ ◀── GPT     (codex exec, MCP over HTTP)
                   │  web UI + MCP endpoint /mcp   │ ◀── Gemini  (agy -p, MCP over HTTP)
                   └──────────────────────────────┘
```

When a meeting starts, the hub launches each invited AI as a background process with a seat prompt (rules, role, topic). Each AI calls four MCP tools — `join_meeting`, `send_message`, `wait_for_messages` (long-poll), `read_messages` — and keeps listening until you close the meeting. Every launch gets a fresh seat ticket, so an old or duplicate process is told to stop.

## Safety model

| Role | Can do |
|---|---|
| Equal discussion (default) | Nobody edits the project or runs git writes. Each AI may run programs and write files in its own scratch folder (to make images or try ideas) and attach the results. |
| Lead | Edits files and commits **only inside an isolated git worktree** (new branch `meeting/<time>`, stored outside your project, containing tracked files only — no `.env` or untracked secrets). The lead may run programs, scripts, tests and renders there. Codex is confined by its own `workspace-write` sandbox; Claude and `agy` have no write sandbox on native Windows, so pushes, remote logins, deletes, deploys and publishing are blocked by rules and the prompt (not by the OS). Push, deploy, deleting files or touching production must be asked in the meeting first. You can **assign or change the lead during the meeting** with the seat's *Operate* button; the copy is created on first assignment. While someone operates, the room checks the original project's `git status` every 20 s and posts a ⚠️ warning in the meeting if anything there changes. |
| Autonomous mode | The *Autonomous mode* button at the top lets the AIs keep working without waiting for you (no 8-message pause; safety cap `auto_run_limit`). They split the work and keep going until your goal is reached. Only two cases end it: the goal is done, or they are blocked on something only you can decide with no reasonable default. Then one of them posts a message starting with `[MILESTONE]` (what was done, output files, what you need to decide), which turns autonomous mode off and everyone waits for you. Progress reports in between start with `[SUMMARY]` and do not stop the meeting; the rule is repeated every time an AI waits for messages. Click the button again to stop it any time (you are asked to confirm first). Every time an AI waits for messages it is told the current cap and how many messages it has left, so switching the mode mid-meeting takes effect right away. A seat that is busy (thinking, rendering) shows *working* and how many minutes it has been at it. |
| Assistant | Same as equal discussion: no project edits, own scratch folder only, plus tasks the lead assigns. |

Claude seats load only the project's shared settings (`--setting-sources project`), so your personal allow-lists never widen a seat's permissions. Mock-ups are posted as HTML inside the message; posted pages run in a sandbox and cannot act on the meeting room (they can load meeting attachments, which are served with `Access-Control-Allow-Origin: *` so a canvas can read their pixels). On native Windows the scratch-folder rule is enforced by rules and the prompt, not the OS, so the room checks the original project's `git status` every 20 s during every meeting and warns if anything changes. Merging the lead's branch back is your decision. The server binds to `127.0.0.1` only and rejects writes from other web pages. Seat logs (which contain whatever the AIs read) stay in the data folder and are never written into your project.

**Still, AI agents can make mistakes.** Watch the meeting, review the lead's diff before merging, and do not point it at folders with secrets you would not show the AI providers.

## Configuration

Set environment variables, or put a `config.json` next to `hub.py` (ignored by git), e.g.
`{"lang": "zh-TW", "host_name": "站長"}` — keys: `host_name`, `lang`, `port`, `project`, `home`, `export_dir`, `ai_run_limit`, `auto_run_limit`, `allowed_origins`, `image_max_mb`, `media_max_mb`. Environment variables win.

Attachments: images and HTML pages up to `image_max_mb` (default 32), video/audio (mp4, webm, mov, mp3, m4a, wav) up to `media_max_mb` (default 1024). The host can attach files with the 📎 button, by dragging them onto the message box or by pasting; videos play in the page and can be seeked. When a meeting closes, video/audio stays in the meeting room's own folder and is not copied into your project. The AIs can see what you attach: each message gives them the file paths; they open images directly, and for videos the room extracts 12 evenly spaced key frames (with ffmpeg, if installed) plus the duration.

`allowed_origins` (env `MEETING_ALLOWED_ORIGINS`, comma-separated) lists extra page origins allowed to send actions, e.g. `["https://your-tunnel.example"]` when you reach the room from your phone through a tunnel. On a narrow screen the page switches to a phone layout: ☰ opens the meeting list, ⋯ shows seat details and buttons, and images load only when scrolled into view. On a computer the whole room fits one screen at 100% zoom: seat chips wrap to a second line instead of scrolling sideways, and the meeting list refreshes in place without flicker. The topic sits in a bar above the discussion: click it to collapse or expand, drag the handle under it to change its height (remembered separately for desktop and phone; phones start collapsed). Only do this behind a tunnel that requires login: anyone who can open the page can run the meeting.

| Variable | Default | Meaning |
|---|---|---|
| `MEETING_PORT` | `7720` | port |
| `MEETING_LANG` | `en` | default meeting language (`en`, `zh-TW`) |
| `MEETING_PROJECT` | current folder | default project |
| `MEETING_HOME` | `%LOCALAPPDATA%\ai-meeting-room` / `~/.local/share/ai-meeting-room` | live meetings, seat logs, lead worktrees |
| `MEETING_EXPORT_DIR` | `docs/meetings` | where transcripts go, relative to the project |
| `MEETING_AI_RUN_LIMIT` | `8` | AI messages in a row before they wait for you |
| `MEETING_AUTO_RUN_LIMIT` | `120` | Safety cap while **Autonomous mode** is on |
| `MEETING_HOST_NAME` | `主持人` | how the AIs address you in Chinese meetings |
| `CLAUDE_BIN`, `CODEX_BIN`, `AGY_BIN` | auto | paths to the CLIs |

## Status and known limits

- Developed and tested on **Windows 11** with Claude Code 2.1, Codex CLI 0.159 and Antigravity CLI (Gemini 3.8 Flash). macOS / Linux paths are implemented but not yet tested — reports welcome.
- Each AI speaks when its own turn finishes, so replies arrive in bursts rather than as live typing.
- The page polls every 1.5 s; a slow poll is skipped instead of overlapping, and messages already shown are never drawn again (earlier versions could show the same message twice while the AIs were busy).
- Running all three AIs uses all three subscriptions' quotas at once. Each seat chip shows usage: GPT and Claude show the 5-hour and weekly quota used (whole account, from the CLIs' own logs) with reset times on hover; Gemini shows tokens used in this meeting (Google does not expose the remaining quota). When an AI stops because it hit its limit, the meeting says so with the reset time and does not keep restarting it.
- **Windows + Claude desktop app:** programs installed from inside the app's terminal land in the app's private folder and are invisible to your own PowerShell. Install the CLIs from your own terminal.
- **Windows + Microsoft Store Python:** the Store build runs in an app container, so the AI seats it starts exit at once ("Broken pipe") and its files land in a private folder. `start_bg.ps1` now skips it when another Python 3.9+ is installed; set `MEETING_PYTHON` to pick one yourself.
- **PowerShell "running scripts is disabled":** use `npm.cmd` instead of `npm`.

## License

MIT
