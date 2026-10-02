# AI Meeting Room

**Put Claude, GPT and Gemini in one room with you.** Each AI speaks for itself, you watch the discussion live in your browser and can interject at any time. Nothing is relayed by hand, and nothing leaves your computer except the AIs' own calls to their providers.

[繁體中文說明](README.zh-TW.md)

- **Uses the subscriptions you already have.** Claude runs through Claude Code (your Claude account), GPT through OpenAI Codex (your ChatGPT account), Gemini through Antigravity CLI (your Google account). No API keys.
- **Auto-detects** which of the three are installed and signed in; invite any one, two or all three.
- **You are the host.** Interjections are answered first, every host message shows who has replied, the AIs never end the meeting on their own, and they pause after 8 messages in a row without you.
- **Same project, same context.** Pick a folder; every AI reads the same files (CLAUDE.md, AGENTS.md, GEMINI.md, README) before speaking.
- **Lead and assistants.** Optionally make one AI the lead: it does all code changes and git commits **in an isolated git worktree outside your project**; the others review and do read-only tasks it assigns.
- **Per-AI model and reasoning effort**, changeable mid-meeting.
- **Several meetings at once**, one browser tab each.
- **Transcripts saved into your project** (`docs/meetings/<date>_<title>/transcript.md`) when you close the meeting.
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

Open <http://127.0.0.1:7720/>, click **New meeting**, pick the project, tick the AIs to invite, write the topic, **Start meeting**.

### One-time setup for Gemini

Antigravity CLI runs in the background and cannot ask you for permission, so the meeting tools must be allowed in its settings. In the **New meeting** dialog, click **Allow meeting tools** under Gemini. It adds exactly one rule, `mcp(meeting/*)`, to `~/.gemini/antigravity-cli/settings.json` — nothing else.

### Optional: the `meeting` command for Claude Code

Copy `skills/meeting` (English) or `skills/開會` (Chinese) into `~/.claude/skills/`. Then just tell Claude "start a meeting about …": it starts the room, opens the meeting on the current project in a new Chrome tab, waits until you close it and reports the result. If you cloned somewhere other than `~/ai-meeting-room`, set `AI_MEETING_ROOM_DIR`.

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
| Equal discussion (default) | Everyone reads files and runs read-only git commands (`status`, `diff`, `log`, `show`, `blame`). No edits. |
| Lead | Edits files and commits **only inside an isolated git worktree** (new branch `meeting/<time>`, stored outside your project, containing tracked files only — no `.env` or untracked secrets). Claude's lead commands are allow-listed (git without push, syntax checks). Codex runs in its `workspace-write` sandbox. `agy` refuses shell commands in background mode. Push, deploy, deleting files or touching production must be asked in the meeting first. |
| Assistant | Read-only, plus read-only tasks the lead assigns. |

Merging the lead's branch back is your decision. The server binds to `127.0.0.1` only and rejects writes from other web pages. Seat logs (which contain whatever the AIs read) stay in the data folder and are never written into your project.

**Still, AI agents can make mistakes.** Watch the meeting, review the lead's diff before merging, and do not point it at folders with secrets you would not show the AI providers.

## Configuration

Set environment variables, or put a `config.json` next to `hub.py` (ignored by git), e.g.
`{"lang": "zh-TW", "host_name": "站長"}` — keys: `host_name`, `lang`, `port`, `project`, `home`, `export_dir`, `ai_run_limit`. Environment variables win.

| Variable | Default | Meaning |
|---|---|---|
| `MEETING_PORT` | `7720` | port |
| `MEETING_LANG` | `en` | default meeting language (`en`, `zh-TW`) |
| `MEETING_PROJECT` | current folder | default project |
| `MEETING_HOME` | `%LOCALAPPDATA%\ai-meeting-room` / `~/.local/share/ai-meeting-room` | live meetings, seat logs, lead worktrees |
| `MEETING_EXPORT_DIR` | `docs/meetings` | where transcripts go, relative to the project |
| `MEETING_AI_RUN_LIMIT` | `8` | AI messages in a row before they wait for you |
| `MEETING_HOST_NAME` | `主持人` | how the AIs address you in Chinese meetings |
| `CLAUDE_BIN`, `CODEX_BIN`, `AGY_BIN` | auto | paths to the CLIs |

## Status and known limits

- Developed and tested on **Windows 11** with Claude Code 2.1, Codex CLI 0.159 and Antigravity CLI (Gemini 3.8 Flash). macOS / Linux paths are implemented but not yet tested — reports welcome.
- Each AI speaks when its own turn finishes, so replies arrive in bursts rather than as live typing.
- Running all three AIs uses all three subscriptions' quotas at once.
- **Windows + Claude desktop app:** programs installed from inside the app's terminal land in the app's private folder and are invisible to your own PowerShell. Install the CLIs from your own terminal.
- **PowerShell "running scripts is disabled":** use `npm.cmd` instead of `npm`.

## License

MIT
