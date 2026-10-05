#!/usr/bin/env python3
import base64
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

VERSION = "1.2.0"
HERE = os.path.dirname(os.path.abspath(__file__))
IS_WIN = os.name == "nt"


def _load_local_config():
    try:
        with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return
    for key, var in (("host_name", "MEETING_HOST_NAME"), ("lang", "MEETING_LANG"), ("port", "MEETING_PORT"),
                     ("project", "MEETING_PROJECT"), ("home", "MEETING_HOME"), ("export_dir", "MEETING_EXPORT_DIR"),
                     ("ai_run_limit", "MEETING_AI_RUN_LIMIT"), ("auto_run_limit", "MEETING_AUTO_RUN_LIMIT"), ("image_max_mb", "MEETING_IMAGE_MAX_MB"),
                     ("media_max_mb", "MEETING_MEDIA_MAX_MB")):
        if key in cfg and not os.environ.get(var):
            os.environ[var] = str(cfg[key])
    if cfg.get("allowed_origins") and not os.environ.get("MEETING_ALLOWED_ORIGINS"):
        os.environ["MEETING_ALLOWED_ORIGINS"] = ",".join(cfg["allowed_origins"])


_load_local_config()


def _data_home():
    if os.environ.get("MEETING_HOME"):
        return os.environ["MEETING_HOME"]
    if IS_WIN:
        return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "ai-meeting-room")
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "ai-meeting-room")


DEFAULT_PROJECT = os.path.abspath(os.environ.get("MEETING_PROJECT") or os.getcwd())
LOCAL = _data_home()
DATA = os.path.join(LOCAL, "rooms")
EXPORT_SUBDIR = os.environ.get("MEETING_EXPORT_DIR", os.path.join("docs", "meetings"))
PORT = int(os.environ.get("MEETING_PORT", "7720"))
ALLOWED_ORIGINS = {o.strip().rstrip("/") for o in os.environ.get("MEETING_ALLOWED_ORIGINS", "").split(",") if o.strip()}
DEFAULT_LANG = os.environ.get("MEETING_LANG", "en")
SEATS = ("Claude", "GPT", "Gemini")
AI_RUN_LIMIT = int(os.environ.get("MEETING_AI_RUN_LIMIT", "8"))
AUTO_RUN_LIMIT = int(os.environ.get("MEETING_AUTO_RUN_LIMIT", "120"))
DONE_MARK = ("【階段成果】", "[MILESTONE]")


def run_limit(room):
    """自主會議:AI 可以連續工作到告一段落(只留一個防失控的安全上限);一般會議:連講 AI_RUN_LIMIT 則就等主持人"""
    return AUTO_RUN_LIMIT if room.meta.get("auto") else AI_RUN_LIMIT
WAIT_MAX = 240
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
PAGE_EXT = {".html", ".htm"}
MEDIA_EXT = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
             ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".wav": "audio/wav"}
ATTACH_MAX = int(float(os.environ.get("MEETING_IMAGE_MAX_MB", "32")) * 1024 * 1024)
MEDIA_MAX = int(float(os.environ.get("MEETING_MEDIA_MAX_MB", "1024")) * 1024 * 1024)
ALL_EXT = IMG_EXT | PAGE_EXT | set(MEDIA_EXT)


VIDEO_EXT = {".mp4", ".webm", ".mov"}
FRAMES_N = 12


def frames_dir(room, f):
    return os.path.join(room.dir, ".frames", f)


def make_frames(room, f):
    src = os.path.join(room.dir, f)
    out = frames_dir(room, f)
    ff, fp = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ff or not fp or os.path.isdir(out):
        return
    os.makedirs(out, exist_ok=True)
    try:
        dur = float(subprocess.run([fp, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src],
                                   capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW).stdout.strip())
    except (ValueError, subprocess.SubprocessError):
        return
    for i in range(FRAMES_N):
        t = dur * (i + 0.5) / FRAMES_N
        subprocess.run([ff, "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", src, "-frames:v", "1", "-vf", "scale=960:-2",
                        os.path.join(out, f"{i + 1:02d}_{int(t // 60):02d}m{t % 60:04.1f}s.jpg")],
                       capture_output=True, timeout=120, creationflags=NO_WINDOW)
    with open(os.path.join(out, "info.json"), "w", encoding="utf-8") as fh:
        json.dump({"duration_sec": round(dur, 1)}, fh)


def frames_later(room, f):
    if os.path.splitext(f)[1].lower() in VIDEO_EXT:
        threading.Thread(target=make_frames, args=(room, f), daemon=True).start()


def attach_info(room, f):
    p = os.path.join(room.dir, f)
    d = {"path": p}
    if os.path.splitext(f)[1].lower() in VIDEO_EXT:
        fd = frames_dir(room, f)
        if os.path.isdir(fd):
            d["frames"] = [os.path.join(fd, x) for x in sorted(os.listdir(fd)) if x.endswith(".jpg")]
            try:
                with open(os.path.join(fd, "info.json"), encoding="utf-8") as fh:
                    d.update(json.load(fh))
            except (OSError, ValueError):
                d["frames_note"] = "key frames are still being extracted; read the messages again shortly"
    return d


def size_ok(path_or_size, ext):
    n = path_or_size if isinstance(path_or_size, int) else os.path.getsize(path_or_size)
    return n <= (MEDIA_MAX if ext in MEDIA_EXT else ATTACH_MAX)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
LANGS = ("en", "zh-TW")


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


T = {
    "en": {
        "host": "Host", "system": "System",
        "modes": {"discuss": "Discussion", "review": "Code review"},
        "leads": {"": "Equal discussion (all read-only)", "Claude": "Claude leads, GPT assists",
                  "GPT": "GPT leads, Claude assists"},
        "start": "Meeting started: {title} (project {project} · {mode} · {lead})",
        "worktree": "Lead's isolated copy: {path} (branch {branch}). The main project folder is never touched; "
                    "the host decides whether to merge it back.",
        "closed": "The host closed the meeting. Both AIs are leaving.",
        "exported": "Meeting record saved to: {path}",
        "export_fail": "Saving the meeting record failed: {err}",
        "seat_fail": "{seat} failed to start: {err}",
        "model_changed": "{seat} switched to {label} and rejoined.",
        "auto_back": "{seat} stopped unexpectedly ({why}) and was brought back automatically.",
        "limit_hit": "{seat} hit its usage limit (resets: {when}); not bringing it back automatically. Click Bring back once it resets.",
        "resumed": "The meeting room restarted; {seat} rejoined.",
        "auto_gave_up": "{seat} stopped unexpectedly again ({why}); not restarting. Use Bring back when ready.",
        "invited": "The {host} invited {seat} ({label}).",
        "lead_set": "The {host} assigned {seat} to operate: it may run programs and edit files in the isolated copy "
                    "{path}; everyone else only reads.",
        "lead_off": "The {host} cleared the assignment; everyone only reads again.",
        "proj_changed": "⚠️ The original project {project} changed during the meeting: {files}. If this was not you, "
                        "check it with git and restore it.",
        "dismissed": "The {host} asked {seat} to leave.",
        "auto_on": "The {host} turned on **autonomous mode**: do not wait for the {host}. Split the work among "
                   "yourselves and keep going until the task is done or reaches a natural milestone. Then ONE of you "
                   "posts a message starting with [MILESTONE] that lists what was done, the output files and what "
                   "the {host} needs to decide; after that everyone calls wait_for_messages. (Safety cap: {n} "
                   "messages in a row.)",
        "auto_off": "The {host} turned off autonomous mode; back to at most {n} messages in a row before waiting.",
        "auto_done": "A milestone was posted; autonomous mode is off. Everyone waits for the {host}.",
        "default": "default", "account_default": "Account default",
        "efforts": {"": "default", "low": "low", "medium": "medium", "high": "high", "xhigh": "x-high",
                    "max": "max", "ultra": "ultra"},
        "stale": "Your seat ticket is no longer valid (a newer process took this seat). Stop now and do not call any more tools.",
        "run_limit": "The host has not replied yet and the AIs have sent {n} messages in a row. Call wait_for_messages and wait for the host.",
        "closed_no_speak": "The meeting is closed. You can no longer speak.",
        "empty": "The message is empty.",
        "bad_image": "Attachment not found, too large (images/pages {img_mb} MB, video/audio {media_mb} MB max) or "
                     "unsupported (png/jpg/webp/gif/html/mp4/webm/mov/mp3/m4a/wav): {p}",
        "no_new": "No new messages. Call wait_for_messages again.",
        "run_left": "You may post {left} more message(s) in a row before waiting for the {host} (current limit {n}; the limit changes when autonomous mode is turned on or off).",
        "rules": "Without the host speaking, the two AIs may send at most {n} messages in a row; then wait for the host.",
        "need_git": "A lead needs a git project (the lead edits code in an isolated git worktree). "
                    "This folder is not a git project; use an equal discussion instead.",
        "no_codex": "Codex CLI not found. Install Codex and sign in with your ChatGPT account (or set CODEX_BIN).",
        "no_claude": "Claude CLI not found. Install Claude Code (or set CLAUDE_BIN).",
        "no_gemini": "Antigravity CLI (agy) not found. Install it, run `agy` once and sign in with Google (or set AGY_BIN).",
        "agy_allow": "agy has not allowed the meeting tools yet. Click \"Allow meeting tools\" in the invite panel.",
        "transcript": {"time": "Started", "project": "Project", "type": "Type", "models": "Models",
                       "worktree": "Lead's copy", "merge": "merge is the host's decision", "topic": "Topic",
                       "log": "Transcript", "dropped": "not kept: not adopted",
                       "media": "video/audio stays in the meeting room folder, not copied here"},
        "img_note": "To show a mock-up or animation, put a complete self-contained HTML page (inline CSS/JS, no "
                    "external URLs) in the `html` field of send_message; the room shows it inline and interactive. You "
                    "can also make images with your built-in image tool or with programs in your scratch folder and pass "
                    "the file path as attach_path. A page may load earlier attachments by file name; to read their pixels in "
                    "a canvas set img.crossOrigin=\"anonymous\". Never ask the host to open a URL and never start a web "
                    "server.",
        "no_img": "To show a mock-up or animation, put a complete self-contained HTML page (inline CSS/JS, no external "
                  "URLs) in the `html` field of send_message; the room shows it inline and interactive. You can also make "
                  "image files with programs in your scratch folder and pass the path as attach_path. A page may load "
                  "earlier attachments by file name; to read their pixels in a canvas set img.crossOrigin=\"anonymous\". "
                  "Never ask the host to open a URL.",
    },
    "zh-TW": {
        "host": os.environ.get("MEETING_HOST_NAME", "主持人"), "system": "系統",
        "modes": {"discuss": "討論", "review": "互相檢查程式碼"},
        "leads": {"": "平等討論(大家都只能看)", "Claude": "Claude 主審、GPT 輔助", "GPT": "GPT 主審、Claude 輔助"},
        "start": "會議開始:{title}(專案 {project}・{mode}・{lead})",
        "worktree": "主審的獨立副本:{path}(分支 {branch})。主資料夾不會被改到;要不要合併回來由{host}決定。",
        "closed": "{host}宣布散會,AI 退場。",
        "exported": "會議紀錄已存到:{path}",
        "export_fail": "會議紀錄匯出失敗:{err}",
        "seat_fail": "{seat} 啟動失敗:{err}",
        "model_changed": "{seat} 改用 {label},重新入席。",
        "auto_back": "{seat} 意外離席({why}),已自動請回。",
        "limit_hit": "{seat} 的用量已達上限(恢復時間:{when}),先不自動請回;恢復後按「請回席」。",
        "resumed": "會議室重新啟動,{seat} 重新入席。",
        "auto_gave_up": "{seat} 又意外離席({why}),不再自動請回;需要時按「請回席」。",
        "invited": "{host}邀請 {seat} 入席({label})。",
        "lead_set": "{host}指派 {seat} 操作:可以在獨立副本 {path} 裡跑程式、改檔;其他人只能看。",
        "lead_off": "{host}取消指派,大家回到只能看。",
        "proj_changed": "⚠️ 原專案 {project} 在會議期間有變動:{files}。如果不是你自己改的,請用 git 檢查並還原。",
        "dismissed": "{host}請 {seat} 離席。",
        "auto_on": "{host}開啟**自主會議**:不用等{host}回覆,請自行分工,把工作做完或做到告一段落。"
                   "完成時由一位發一則開頭為「【階段成果】」的訊息,列出做了什麼、產出檔案、要{host}決定的事;"
                   "之後所有人呼叫 wait_for_messages 等{host}。(防失控上限:連續 {n} 則)",
        "auto_off": "{host}關閉自主會議,回到連講 {n} 則就等{host}。",
        "auto_done": "已發出階段成果,自主會議自動關閉,大家等{host}回來看。",
        "default": "預設", "account_default": "帳號預設",
        "efforts": {"": "預設", "low": "低", "medium": "中", "high": "高", "xhigh": "更高", "max": "最高", "ultra": "極限"},
        "stale": "你的入席證已失效(這個席位已由新的程序接手)。請立即結束,不要再呼叫任何工具。",
        "run_limit": "{host}還沒回應,AI 已連講 {n} 則。請呼叫 wait_for_messages 等{host}發言。",
        "closed_no_speak": "已散會,不能再發言。",
        "empty": "發言內容是空的。",
        "bad_image": "附件不存在、太大(圖片/網頁 {img_mb} MB、影音 {media_mb} MB 以內),或格式不支援"
                     "(png/jpg/webp/gif/html/mp4/webm/mov/mp3/m4a/wav):{p}",
        "no_new": "目前沒有新發言,請再呼叫 wait_for_messages。",
        "run_left": "目前還能連續發言 {left} 則才需要等{host}(上限 {n} 則;{host}開關自主會議時上限會跟著變)。",
        "rules": "{host}沒發言時,AI 合計最多連講 {n} 則,之後要等{host}開口。",
        "need_git": "指定主審需要 git 專案(主審在獨立副本裡改程式);這個資料夾不是 git 專案,請改用平等討論",
        "no_codex": "找不到 Codex:請安裝 Codex 並以 ChatGPT 帳號登入(或設定 CODEX_BIN)",
        "no_claude": "找不到 Claude 命令列程式:請安裝 Claude Code(或設定 CLAUDE_BIN)",
        "no_gemini": "找不到 Antigravity 命令列程式(agy):請安裝後執行一次 `agy` 用 Google 帳號登入(或設定 AGY_BIN)",
        "agy_allow": "agy 還沒允許會議室工具:請在邀請區按「允許會議室工具」。",
        "transcript": {"time": "時間", "project": "專案", "type": "類型", "models": "模型",
                       "worktree": "主審副本", "merge": "合併與否由主持人決定", "topic": "議題", "log": "逐字稿",
                       "dropped": "未保留:沒有採用", "media": "影音檔留在會議室資料夾,不複製到專案"},
        "img_note": "要給{host}看樣板或動態時,把完整網頁內容(單一 HTML,樣式、程式都寫在裡面、不連外部網址)放在 send_message 的 "
                    "html 欄位,會議室會直接嵌在你的發言下面、可以操作。也可以用內建圖片生成功能,或在自己的試做資料夾用程式出圖,"
                    "把檔案路徑放進 attach_path。網頁可以用檔名載入之前的附件;要在 canvas 讀它們的像素,記得設 "
                    "img.crossOrigin=\"anonymous\"。不要叫{host}開網址,也不要自己架伺服器。",
        "no_img": "要給{host}看樣板或動態時,把完整網頁內容(單一 HTML,樣式、程式都寫在裡面、不連外部網址)放在 send_message 的 "
                  "html 欄位,會議室會直接嵌在你的發言下面、可以操作。也可以在自己的試做資料夾用程式產生圖檔,把路徑放進 attach_path。"
                  "網頁可以用檔名載入之前的附件;要在 canvas 讀它們的像素,記得設 img.crossOrigin=\"anonymous\"。不要叫{host}開網址。",
    },
}


def tx(room_or_lang, key, **kw):
    lang = room_or_lang if isinstance(room_or_lang, str) else (room_or_lang.meta.get("lang") or DEFAULT_LANG)
    d = T.get(lang, T["en"])
    v = d[key]
    if isinstance(v, str):
        kw.setdefault("host", d["host"])
        return v.format(**kw)
    return v


class Room:
    def __init__(self, rid, meta):
        self.id = rid
        self.meta = meta
        self.msgs = []
        self.cond = threading.Condition()
        self.waiting = {}
        self.busy_since = {}
        self.procs = {}
        self.dir = os.path.join(DATA, rid)

    def save_meta(self):
        with open(os.path.join(self.dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(self.meta, f, ensure_ascii=False, indent=1)

    def add(self, who, text, imgs=None):
        with self.cond:
            m = {"seq": len(self.msgs) + 1, "who": who, "text": text, "imgs": imgs or [], "at": now_iso()}
            self.msgs.append(m)
            with open(os.path.join(self.dir, "log.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
            self.cond.notify_all()
            return m

    def ai_run(self):
        n = 0
        for m in reversed(self.msgs):
            if m["who"] == "user":
                break
            if m["who"] in SEATS:
                n += 1
        return n

    def state(self, seat):
        p = self.procs.get(seat)
        if self.waiting.get(seat):
            return "listening"
        if p is not None and p.poll() is None:
            return "thinking"
        return "away"


ROOMS = {}
ROOMS_LOCK = threading.Lock()


def load_rooms():
    os.makedirs(DATA, exist_ok=True)
    for d in sorted(os.listdir(DATA)):
        mp = os.path.join(DATA, d, "meta.json")
        if not os.path.isfile(mp):
            continue
        with open(mp, encoding="utf-8") as f:
            r = Room(d, json.load(f))
        lp = os.path.join(DATA, d, "log.jsonl")
        if os.path.isfile(lp):
            with open(lp, encoding="utf-8") as f:
                r.msgs = [json.loads(x) for x in f if x.strip()]
        ROOMS[d] = r


def room_seats(room):
    seats = room.meta.get("seats")
    return [x for x in (SEATS if seats is None else seats) if x in SEATS]


def others_of(room, seat, lang=None):
    o = [x for x in room_seats(room) if x != seat]
    lang = lang or room.meta.get("lang") or DEFAULT_LANG
    return ("、" if lang == "zh-TW" else " and ").join(o) or ("（無）" if lang == "zh-TW" else "(nobody)")


def new_room(title, topic, seat_cfg, project, lead, mode, lang, seats):
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    slug = re.sub(r"[^0-9A-Za-z一-鿿]+", "-", title).strip("-")[:24] or "meeting"
    rid = f"{stamp}-{slug}"
    with ROOMS_LOCK:
        base, i = rid, 2
        while rid in ROOMS or os.path.exists(os.path.join(DATA, rid)):
            rid = f"{base}-{i}"
            i += 1
        meta = {"title": title, "topic": topic, "created": now_iso(), "closed": False, "lang": lang, "seats": seats,
                "seat_cfg": seat_cfg, "project": project, "lead": lead, "mode": mode}
        if lead:
            meta["worktree"], meta["branch"], meta["git_common"] = make_worktree(project, rid, lang)
        r = Room(rid, meta)
        os.makedirs(r.dir, exist_ok=True)
        r.save_meta()
        ROOMS[rid] = r
    r.add("system", tx(r, "start", title=title, project=project, mode=tx(r, "modes")[mode], lead=tx(r, "leads")[lead]))
    if lead:
        r.add("system", tx(r, "worktree", path=meta["worktree"], branch=meta["branch"]))
    return r


def clean_cfg(c):
    out = {}
    for seat in SEATS:
        x = (c or {}).get(seat) or {}
        m, e = str(x.get("model") or ""), str(x.get("effort") or "")
        if not re.fullmatch(r"[A-Za-z0-9._-]{0,60}", m) or not re.fullmatch(r"[a-z]{0,10}", e):
            raise ValueError("invalid model or effort / 模型或思考深度格式不對")
        out[seat] = {"model": m, "effort": e}
    return out


def get_room(rid):
    r = ROOMS.get(rid)
    if not r:
        raise KeyError(f"meeting not found / 找不到會議: {rid}")
    return r


ARC_PREFIX = "arc~"


def _arc_id(path):
    return ARC_PREFIX + base64.urlsafe_b64encode(os.path.abspath(path).encode("utf-8")).decode("ascii").rstrip("=")


def _arc_head(d):
    title, topic, sections = os.path.basename(d), "", []
    try:
        with open(os.path.join(d, "transcript.md"), encoding="utf-8") as fh:
            lines = fh.read().split("\n")
    except OSError:
        return title, topic, ""
    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip()
    sections = [i for i, ln in enumerate(lines) if ln.startswith("## ")]
    head = [ln.split(":", 1)[1].strip() for ln in lines[:sections[0] if sections else len(lines)]
            if ln.startswith("- ") and ":" in ln]
    if len(sections) >= 2:
        topic = "\n".join(lines[sections[0] + 1:sections[1]]).strip()
    return title, topic, head[2] if len(head) > 2 else ""


def archives():
    live = {os.path.normcase(os.path.abspath(r.meta["export"])) for r in ROOMS.values() if r.meta.get("export")}
    out = []
    for proj in (p["path"] for p in known_projects()):
        base = os.path.join(proj, EXPORT_SUBDIR)
        if not os.path.isdir(base):
            continue
        for n in os.listdir(base):
            d = os.path.join(base, n)
            log = os.path.join(d, "log.jsonl")
            if os.path.normcase(os.path.abspath(d)) in live or not os.path.isfile(log):
                continue
            out.append({"id": _arc_id(d), "dir": d, "project": proj})
    return out


def get_archive(aid):
    for a in archives():
        if a["id"] == aid:
            return a
    raise KeyError(f"meeting not found / 找不到會議: {aid}")


def archive_messages(a):
    msgs = []
    with open(os.path.join(a["dir"], "log.jsonl"), encoding="utf-8") as fh:
        for ln in fh:
            if ln.strip():
                m = json.loads(ln)
                m["imgs"] = [f for f in m.get("imgs") or [] if os.path.isfile(os.path.join(a["dir"], f))]
                msgs.append(m)
    return msgs


def _ver(p):
    v = os.path.basename(os.path.dirname(p))
    return tuple(int(x) if x.isdigit() else 0 for x in v.split("."))


def find_codex():
    if os.environ.get("CODEX_BIN"):
        return os.environ["CODEX_BIN"]
    if IS_WIN:
        c = glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""), "OpenAI", "Codex", "bin", "*", "codex.exe"))
        if c:
            return max(c, key=os.path.getmtime)
    else:
        c = glob.glob("/Applications/Codex.app/Contents/Resources/codex") + \
            glob.glob("/Applications/Codex.app/Contents/Resources/*/codex")
        if c:
            return c[0]
    return shutil.which("codex")


def find_claude():
    if os.environ.get("CLAUDE_BIN"):
        return os.environ["CLAUDE_BIN"]
    w = shutil.which("claude")
    if w:
        return w
    if IS_WIN:
        c = glob.glob(os.path.join(os.environ.get("APPDATA", ""), "Claude", "claude-code", "*", "claude.exe"))
    else:
        c = glob.glob(os.path.expanduser("~/Library/Application Support/Claude/claude-code/*/claude")) + \
            glob.glob(os.path.expanduser("~/.claude/local/claude"))
    return max(c, key=_ver) if c else None


def find_gemini():
    if os.environ.get("AGY_BIN"):
        return os.environ["AGY_BIN"]
    w = shutil.which("agy")
    if w:
        return w
    c = [os.path.join(os.environ.get("LOCALAPPDATA", ""), "agy", "bin", "agy.exe")] if IS_WIN else \
        [os.path.expanduser("~/.local/bin/agy"), "/usr/local/bin/agy"]
    return next((x for x in c if os.path.isfile(x)), None)


AGY_SETTINGS = os.path.join(os.path.expanduser("~"), ".gemini", "antigravity-cli", "settings.json")
AGY_RULES = ["mcp(meeting/*)", "read_url(*)"]


def agy_allows_meeting():
    try:
        with open(AGY_SETTINGS, encoding="utf-8") as f:
            have = (json.load(f).get("permissions") or {}).get("allow") or []
        return all(r in have for r in AGY_RULES)
    except (OSError, ValueError):
        return False


def allow_meeting_in_agy():
    try:
        with open(AGY_SETTINGS, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    allow = d.setdefault("permissions", {}).setdefault("allow", [])
    missing = [r for r in AGY_RULES if r not in allow]
    if missing:
        allow.extend(missing)
        os.makedirs(os.path.dirname(AGY_SETTINGS), exist_ok=True)
        with open(AGY_SETTINGS, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)


FINDERS = {"Claude": find_claude, "GPT": find_codex, "Gemini": find_gemini}
INSTALL_HINT = {
    "Claude": "Install Claude Code (https://claude.com/claude-code) and sign in with your Claude account.",
    "GPT": "Install OpenAI Codex (desktop app or `npm i -g @openai/codex`) and sign in with your ChatGPT account.",
    "Gemini": "Install Antigravity CLI (Windows: `irm https://antigravity.google/cli/install.ps1 | iex`), run `agy` once and "
              "sign in with Google, then click \"Allow meeting tools\" here (adds only mcp(meeting/*) to agy's settings).",
}


def _signed_in(seat):
    home = os.path.expanduser("~")
    if seat == "GPT":
        return os.path.isfile(os.path.join(home, ".codex", "auth.json")) or bool(os.environ.get("OPENAI_API_KEY"))
    if seat == "Gemini":
        return os.path.isdir(os.path.join(home, ".gemini", "antigravity-cli", "cache"))
    return True


def agents():
    out = {}
    for s in SEATS:
        path = FINDERS[s]()
        out[s] = {"installed": bool(path), "path": path, "signed_in": bool(path) and _signed_in(s),
                  "hint": INSTALL_HINT[s]}
        if s == "Gemini":
            out[s]["needs_allow"] = bool(path) and not agy_allows_meeting()
    return out


CLAUDE_MODELS = [
    {"id": ""},
    {"id": "fable", "label": "Fable", "latest": "5.1"},
    {"id": "opus", "label": "Opus", "latest": "5.5"},
    {"id": "sonnet", "label": "Sonnet", "latest": "5.5"},
    {"id": "haiku", "label": "Haiku", "latest": "4.5"},
    {"id": "claude-fable-5-1", "label": "Fable 5.1", "pinned": True},
    {"id": "claude-opus-5-5", "label": "Opus 5.5", "pinned": True},
    {"id": "claude-sonnet-5-5", "label": "Sonnet 5.5", "pinned": True},
    {"id": "claude-haiku-4-5-20251001", "label": "Haiku 4.5", "pinned": True},
]
CLAUDE_EFFORTS = ["low", "medium", "high", "xhigh", "max"]
_AGY_MODELS = {"t": 0, "v": []}


def agy_models():
    if time.time() - _AGY_MODELS["t"] < 600:
        return _AGY_MODELS["v"]
    exe, out = find_gemini(), []
    if exe:
        try:
            r = subprocess.run([exe, "models"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=30, creationflags=NO_WINDOW)
            for line in r.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) == 2 and re.fullmatch(r"[A-Za-z0-9._-]+", parts[0].strip()):
                    out.append({"id": parts[0].strip(), "label": parts[1].strip()})
        except (OSError, subprocess.SubprocessError):
            pass
    _AGY_MODELS.update(t=time.time(), v=out)
    return out


def codex_defaults():
    m = e = ""
    try:
        with open(os.path.join(os.path.expanduser("~"), ".codex", "config.toml"), encoding="utf-8") as f:
            for line in f:
                if line.startswith("["):
                    break
                mm = re.match(r'\s*model\s*=\s*"([^"]+)"', line)
                ee = re.match(r'\s*model_reasoning_effort\s*=\s*"([^"]+)"', line)
                m = mm.group(1) if mm else m
                e = ee.group(1) if ee else e
    except OSError:
        pass
    return m, e


def model_options():
    dm, de = codex_defaults()
    gpt = []
    try:
        with open(os.path.join(os.path.expanduser("~"), ".codex", "models_cache.json"), encoding="utf-8") as f:
            d = json.load(f)
        for x in (d.get("models", d) if isinstance(d, dict) else d):
            slug = x.get("slug") or x.get("id")
            if not slug or "review" in slug:
                continue
            gpt.append({"id": slug, "label": x.get("display_name") or slug, "note": x.get("description", ""),
                        "efforts": [y.get("effort") for y in x.get("supported_reasoning_levels", []) if y.get("effort")]})
    except (OSError, ValueError):
        pass
    if dm and not any(g["id"] == dm for g in gpt):
        gpt.insert(0, {"id": dm, "label": dm, "note": "", "efforts": ["low", "medium", "high"]})
    return {"Claude": {"models": CLAUDE_MODELS,
                       "efforts": CLAUDE_EFFORTS, "default": {"model": "", "effort": ""}},
            "last": last_models(),
            "GPT": {"models": gpt, "default": {"model": dm, "effort": de}},
            "Gemini": {"models": [{"id": "", "label": ""}] + agy_models(), "efforts": ["low", "medium", "high", "max"],
                       "default": {"model": "", "effort": ""}}}


def last_models():
    try:
        with open(os.path.join(LOCAL, "last_models.json"), encoding="utf-8") as f:
            d = json.load(f)
        return {k: v for k, v in d.items() if k in SEATS and isinstance(v, dict)}
    except (OSError, ValueError):
        return {}


def remember_models(cfg):
    if not cfg:
        return
    d = last_models()
    d.update({k: v for k, v in cfg.items() if k in SEATS})
    os.makedirs(LOCAL, exist_ok=True)
    with open(os.path.join(LOCAL, "last_models.json"), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def seat_label(room, seat):
    c = (room.meta.get("seat_cfg") or {}).get(seat) or {}
    eff = tx(room, "efforts")
    if seat == "GPT":
        dm, de = codex_defaults()
        e = c.get("effort") or de
        return f"{c.get('model') or dm or tx(room, 'default')} · {eff.get(e, e)}"
    m = c.get("model") or ""
    if seat == "Gemini":
        return f"{m or tx(room, 'default')} · {eff.get(c.get('effort', ''), c.get('effort'))}"
    return f"{m.capitalize() if m else tx(room, 'account_default')} · {eff.get(c.get('effort', ''), c.get('effort'))}"


def known_projects():
    found = []

    def push(p):
        p = os.path.normpath(p)
        low = p.lower().replace("\\", "/")
        if not os.path.isdir(p) or "/temp/" in low or "/tmp/" in low or "worktrees" in low or len(p) <= 3:
            return
        if os.path.normcase(p) == os.path.normcase(os.path.expanduser("~")):
            return
        if all(os.path.normcase(p) != os.path.normcase(x) for x in found):
            found.append(p)

    push(DEFAULT_PROJECT)
    cp = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    if os.path.isdir(cp):
        for n in sorted(os.listdir(cp), key=lambda n: -os.path.getmtime(os.path.join(cp, n))):
            m = re.match(r"^([A-Za-z])--(.+)$", n)
            if m and IS_WIN:
                cands = [f"{m.group(1).upper()}:\\{m.group(2)}", f"{m.group(1).upper()}:\\" + m.group(2).replace("-", "\\")]
            elif n.startswith("-") and not IS_WIN:
                cands = [n.replace("-", "/")]
            else:
                continue
            for c in cands:
                if os.path.isdir(c):
                    push(c)
                    break
    try:
        with open(os.path.join(os.path.expanduser("~"), ".codex", "config.toml"), encoding="utf-8") as f:
            for line in f:
                m = re.match(r"""^\[projects\.['"](.+)['"]\]""", line.strip())
                if m:
                    push(m.group(1))
    except OSError:
        pass
    try:
        with open(os.path.join(LOCAL, "projects.json"), encoding="utf-8") as f:
            for p in json.load(f):
                push(p)
    except (OSError, ValueError):
        pass
    return [{"path": p, "name": os.path.basename(p) or p} for p in found]


def remember_project(p):
    os.makedirs(LOCAL, exist_ok=True)
    fp = os.path.join(LOCAL, "projects.json")
    try:
        with open(fp, encoding="utf-8") as f:
            arr = json.load(f)
    except (OSError, ValueError):
        arr = []
    if p not in arr:
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(([p] + arr)[:30], f, ensure_ascii=False, indent=1)


def git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:300])
    return r.stdout.strip()


GUARDS = set()
GUARD_EVERY = 20


def project_state(room):
    top = git(room.meta.get("project") or DEFAULT_PROJECT, "rev-parse", "--show-toplevel")
    out = git(top, "status", "--porcelain", "--untracked-files=all")
    return top, {line for line in out.splitlines() if line.strip()}


def guard_project(room):
    if room.id in GUARDS:
        return
    GUARDS.add(room.id)

    def run():
        try:
            top, seen = project_state(room)
        except RuntimeError:
            GUARDS.discard(room.id)
            return
        while not room.meta.get("closed"):
            time.sleep(GUARD_EVERY)
            try:
                _, now = project_state(room)
            except RuntimeError:
                continue
            new = sorted(now - seen)
            if new:
                files = ", ".join(x.split(None, 1)[-1] for x in new[:10]) + (f" (+{len(new) - 10})" if len(new) > 10 else "")
                room.add("system", tx(room, "proj_changed", project=top, files=files))
            seen = now
        GUARDS.discard(room.id)

    threading.Thread(target=run, daemon=True).start()


def make_worktree(project, rid, lang):
    try:
        top = git(project, "rev-parse", "--show-toplevel")
    except RuntimeError:
        raise RuntimeError(tx(lang, "need_git"))
    branch = "meeting/" + datetime.now().strftime("%Y%m%d-%H%M") + "-" + uuid.uuid4().hex[:4]
    path = os.path.join(LOCAL, "worktrees", rid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    git(top, "worktree", "add", "-b", branch, path, "HEAD")
    common = os.path.normpath(os.path.join(top, git(top, "rev-parse", "--git-common-dir")))
    return path, branch, common


def project_of(room):
    wt = room.meta.get("worktree")
    if wt and os.path.isdir(wt):
        return wt
    p = room.meta.get("project") or DEFAULT_PROJECT
    return p if os.path.isdir(p) else DEFAULT_PROJECT


GIT_WRITE = ["git add", "git commit", "git reset", "git checkout", "git restore", "git rm", "git mv", "git stash",
             "git merge", "git rebase", "git cherry-pick", "git tag", "git branch", "git switch", "git apply", "git clean",
             "git worktree", "git config"]
LEAD_DENY = ["git push", "git remote", "ssh", "scp", "sftp", "rsync", "rm", "rmdir", "del", "deploy.sh", "./deploy.sh",
             "bash deploy.sh", "docker", "kubectl", "gh", "npm publish", "pip upload", "twine"]


def bash_rules(cmds):
    return ",".join(f"Bash({c}:*)" for c in cmds)


ROLE = {
    "en": {
        "equal": "This is an equal discussion with no lead. **Nobody edits the project: do not modify project files "
                 "and do not run any git write command.** You may run programs and scripts and write files only in your "
                 "own scratch folder {out} (to make images or try ideas) and attach results with attach_path. "
                 "Whoever notices the discussion has converged writes the [SUMMARY].",
        "lead": "The host made **you the lead**; {other} assists.\n"
                "- You do **all code changes and git actions** for this meeting (edit files, git add/commit). "
                "{other} cannot edit; anything hands-on is yours.\n"
                "- You work in an **isolated copy**: {wt} (branch {branch}). Inside it you may run programs, scripts, "
                "tests and renders and edit files freely; put scratch output in the copy or in {out}. Never write to the "
                "original project {project}. Pushing, deploying, remote logins, deleting files and publishing are "
                "blocked; a refused command means it is not allowed: ask the host in the meeting instead and never look "
                "for a workaround.\n"
                "- You may assign read-only work to {other} (research, reading code, checking your changes, finding "
                "holes). Write \"@{other} please …\" with a clear scope and what to report back.\n"
                "- Answer every point {other} raises: accept and change it, or explain why not.\n"
                "- Before editing, say what you will change and why; afterwards list the files and the key diff and "
                "ask {other} to check.\n"
                "- 🔴 **git push, deployment, deleting files, touching production or secrets: always ask the host in "
                "the meeting first and act only after a clear yes.**\n"
                "- Follow the project's own rules (CLAUDE.md / AGENTS.md), e.g. commit message format, banned commands.\n"
                "- Finish with a [SUMMARY] for the host: what you did, verification, what is left, what the host must decide.",
        "assist": "The host made **{other} the lead**; you assist.\n"
                  "- You **may not modify project files or run any git write command**; you may read files, use "
                  "read-only commands, and run programs that write only into your own scratch folder {out}.\n"
                  "- Your job: give your own view on {other}'s plan and changes, find holes, verify facts, raise risks "
                  "and alternatives.\n"
                  "- Do the work {other} assigns to you (\"@{seat} please …\") and report the result in the meeting; "
                  "anything beyond read-only goes back to {other}.\n"
                  "- For changes that are needed, give file, line and the suggested edit, and let {other} make it. "
                  "{other} writes the [SUMMARY].",
        "review": "\n\nThis is a **code review**: start with git status, git diff, git log, git show to see the changes. "
                  "Whoever made the change explains the intent; the reviewer lists issues one by one with file and line "
                  "and what would go wrong; the author answers each (real issue / not an issue + why).",
    },
    "zh-TW": {
        "equal": "這場是平等討論,沒有主審。**大家都不能改專案:不要修改專案裡的檔案、不要做 git 寫入動作。**"
                 "可以在自己的試做資料夾 {out} 裡跑程式、腳本、寫檔(例如產圖、試做),成果用 attach_path 附上。"
                 "收斂時誰先發現誰寫【小結】。",
        "lead": "{host}指定**你是主審**、{other} 是輔助。\n"
                "- 你負責這場會議的**所有程式修改與 git 動作**(改檔、git add/commit)。{other} 不能改檔,需要動手的事都由你做。\n"
                "- 你在**獨立副本**裡工作:{wt}(分支 {branch})。在副本裡可以自由跑程式、腳本、測試、算圖、改檔;"
                "試做的輸出放在副本或 {out}。絕對不要寫到原專案資料夾 {project}。推送、部署、連遠端主機、刪檔、發佈都被擋;"
                "被拒絕的指令就是不准做,改成在會議室請{host}處理,不要找別的方法繞過。\n"
                "- 你可以指派 {other} 做唯讀的工作(查資料、讀程式、檢查你的改動、找漏洞),用「@{other} 請…」清楚交代範圍與要回報什麼。\n"
                "- 認真回應 {other} 的每個意見:接受就改,不接受講理由。\n"
                "- 動手前先在會議室說要改什麼、為什麼;改完貼出改了哪些檔、重點差異,請輔助檢查。\n"
                "- 🔴 **git push、部署、刪除檔案、動到正式環境或金鑰的動作,一律先在會議室問{host},{host}明確同意才做。**\n"
                "- 嚴格遵守專案說明檔(CLAUDE.md/AGENTS.md)裡的規則,例如提交訊息格式、禁止的指令。\n"
                "- 最後寫【小結】交給{host}:做了什麼、驗證結果、還沒做的、需要{host}決定的。",
        "assist": "{host}指定 **{other} 是主審**、你是輔助。\n"
                  "- 你**不能修改專案裡的檔案、不能做 git 寫入動作**;可以讀檔、用唯讀指令查證,也可以跑程式,但只能寫到自己的試做資料夾 {out}。\n"
                  "- 你的工作:對 {other} 的方案與改動提出自己的意見,找漏洞、查證事實、提出風險與替代做法。\n"
                  "- {other} 指派給你的工作(「@{seat} 請…」)要照做,做完把結果回報在會議室;超出唯讀範圍的請 {other} 自己做。\n"
                  "- 需要動手改的地方,寫清楚檔名、行號、建議怎麼改,交給 {other} 執行。【小結】由 {other} 寫。",
        "review": "\n\n這場是**互相檢查程式碼**:先用 git status、git diff、git log、git show 看改動範圍。"
                  "說明改動的一方講清楚用意;檢查的一方逐項列問題,每個附檔名與行號、說明會出什麼錯;被檢查的一方逐項回應(是問題/不是問題+理由)。",
    },
}


def role_text(room, seat):
    lang = room.meta.get("lang") or DEFAULT_LANG
    R = ROLE.get(lang, ROLE["en"])
    lead = room.meta.get("lead") or ""
    other = others_of(room, seat) if lead == seat else lead
    kw = dict(other=other, seat=seat, host=tx(room, "host"), wt=room.meta.get("worktree"),
              branch=room.meta.get("branch"), project=room.meta.get("project"),
              out=os.path.join(LOCAL, "seats", room.id, seat.lower()))
    r = R["equal"] if not lead else (R["lead"] if lead == seat else R["assist"])
    r = r.format(**kw)
    if room.meta.get("mode") == "review":
        r += R["review"]
    return r


def seat_prompt(room, seat, ticket):
    lang = room.meta.get("lang") or DEFAULT_LANG
    with open(os.path.join(HERE, "prompts", f"seat.{lang}.md"), encoding="utf-8") as f:
        tpl = f.read()
    rep = {"SEAT": seat, "OTHER": others_of(room, seat), "ROOM": room.id,
           "TITLE": room.meta["title"], "TOPIC": room.meta["topic"], "PROJECT": project_of(room),
           "MODE": tx(room, "modes")[room.meta.get("mode") or "discuss"], "ROLE": role_text(room, seat),
           "IMAGE": tx(room, "img_note") if seat == "GPT" else tx(room, "no_img"),
           "HOST": tx(room, "host"), "TICKET": ticket}
    for k, v in rep.items():
        tpl = tpl.replace("{{" + k + "}}", v)
    return tpl


def start_seat(room, seat, restart=False):
    if not room.meta.get("closed"):
        guard_project(room)
    p = room.procs.get(seat)
    if p is not None and p.poll() is None:
        if not restart:
            return "already seated"
        p.terminate()
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
    cfg = (room.meta.get("seat_cfg") or {}).get(seat) or {}
    ticket = uuid.uuid4().hex[:8]
    url = f"http://127.0.0.1:{PORT}/mcp"
    seat_dir = os.path.join(LOCAL, "seats", room.id)
    os.makedirs(seat_dir, exist_ok=True)
    env = os.environ.copy()
    lead = room.meta.get("lead")
    if seat == "GPT":
        exe = find_codex()
        if not exe:
            raise RuntimeError(tx(room, "no_codex"))
        work = os.path.join(seat_dir, "gpt")
        os.makedirs(work, exist_ok=True)
        if lead == "GPT":
            root = project_of(room)
            extra = ["--add-dir", work] + (["--add-dir", room.meta["git_common"]] if room.meta.get("git_common") else [])
        else:
            root, extra = work, []
        args = [exe, "exec", "--skip-git-repo-check", "-C", root, *extra, "-s", "workspace-write",
                "-c", f'mcp_servers.meeting.url="{url}"',
                "-c", "mcp_servers.meeting.tool_timeout_sec=300", "-c", "tools.web_search=true",
                "-c", 'mcp_servers.meeting.default_tools_approval_mode="approve"']
        if cfg.get("model"):
            args += ["-m", cfg["model"]]
        if cfg.get("effort"):
            args += ["-c", f'model_reasoning_effort="{cfg["effort"]}"']
        args.append("-")
        cwd = root
    elif seat == "Gemini":
        exe = find_gemini()
        if not exe:
            raise RuntimeError(tx(room, "no_gemini"))
        if not agy_allows_meeting():
            raise RuntimeError(tx(room, "agy_allow"))
        work = os.path.join(seat_dir, "gemini")
        os.makedirs(os.path.join(work, ".agents"), exist_ok=True)
        with open(os.path.join(work, ".agents", "mcp_config.json"), "w", encoding="utf-8") as f:
            json.dump({"mcpServers": {"meeting": {"serverUrl": url}}}, f)
        args = [exe, "--mode", "accept-edits", "--dangerously-skip-permissions", "--output-format", "stream-json",
                "--add-dir", project_of(room), "--add-dir", seat_dir, "--add-dir", room.dir]
        if cfg.get("model"):
            args += ["--model", cfg["model"]]
        if cfg.get("effort"):
            args += ["--effort", cfg["effort"]]
        args += ["-p", seat_prompt(room, seat, ticket)]
        cwd = work
    else:
        exe = find_claude()
        if not exe:
            raise RuntimeError(tx(room, "no_claude"))
        mcp_cfg = os.path.join(seat_dir, "claude_mcp.json")
        with open(mcp_cfg, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": {"meeting": {"type": "http", "url": url}}}, f)
        meet = ("mcp__meeting__join_meeting,mcp__meeting__send_message,"
                "mcp__meeting__wait_for_messages,mcp__meeting__read_messages")
        if lead == "Claude":
            args = [exe, "-p", "--output-format", "stream-json", "--verbose", "--setting-sources", "project",
                    "--mcp-config", mcp_cfg, "--strict-mcp-config", "--permission-mode", "acceptEdits",
                    "--add-dir", seat_dir, "--add-dir", room.dir,
                    "--allowedTools", meet + ",Read,Grep,Glob,Edit,Write,Bash,WebFetch,WebSearch",
                    "--disallowedTools", "NotebookEdit,PowerShell," + bash_rules(LEAD_DENY)]
        else:
            args = [exe, "-p", "--output-format", "stream-json", "--verbose", "--setting-sources", "project",
                    "--mcp-config", mcp_cfg, "--strict-mcp-config", "--add-dir", room.dir, "--add-dir", project_of(room),
                    "--allowedTools", meet + ",Read,Grep,Glob,WebFetch,WebSearch,Bash",
                    "--disallowedTools", "Edit,Write,NotebookEdit,PowerShell," + bash_rules(LEAD_DENY + GIT_WRITE)]
        if cfg.get("model"):
            args += ["--model", cfg["model"]]
        if cfg.get("effort"):
            args += ["--effort", cfg["effort"]]
        if lead == "Claude":
            cwd = project_of(room)
        else:
            cwd = os.path.join(seat_dir, "claude")
            os.makedirs(cwd, exist_ok=True)
        env["MCP_TOOL_TIMEOUT"] = "300000"
    room.meta.setdefault("tickets", {})[seat] = ticket
    room.save_meta()
    with open(os.path.join(seat_dir, f"{seat}.log"), "a", encoding="utf-8") as log:
        log.write(f"\n=== {now_iso()} start {seat} ({seat_label(room, seat)}): {exe}\n")
        log.flush()
        p = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                             creationflags=NO_WINDOW)
    if seat != "Gemini":
        p.stdin.write(seat_prompt(room, seat, ticket).encode("utf-8"))
    p.stdin.close()
    room.procs[seat] = p
    return "seated"


RESTARTS = {}
USAGE_CACHE = {}
LIMIT_RE = re.compile(r"(hit your usage limit|usage limit reached|rate_limit_error|RESOURCE_EXHAUSTED|"
                      r"quota exceeded|exhausted your|\"status\":\"rejected\")", re.I)


def _tail(path, n=262144):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - n))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _find_key(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = _find_key(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_key(v, key)
            if r is not None:
                return r
    return None


def _clock(ts):
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%m/%d %H:%M")
    except (TypeError, ValueError, OSError):
        return "?"


def usage_gpt():
    root = os.path.join(os.path.expanduser("~"), ".codex", "sessions")
    files = sorted(glob.glob(os.path.join(root, "*", "*", "*", "rollout-*.jsonl")), key=os.path.getmtime, reverse=True)[:10]
    for f in files:
        for line in reversed(_tail(f).splitlines()):
            if '"rate_limits"' not in line:
                continue
            try:
                rl = _find_key(json.loads(line), "rate_limits")
            except ValueError:
                continue
            if isinstance(rl, dict) and isinstance(rl.get("primary"), dict):
                p, w = rl["primary"], rl.get("secondary") or {}
                return {"5h": p.get("used_percent"), "5h_reset": p.get("resets_at"),
                        "week": w.get("used_percent"), "week_reset": w.get("resets_at"), "at": os.path.getmtime(f)}
    return None


def usage_claude():
    files = sorted(glob.glob(os.path.join(LOCAL, "seats", "*", "Claude.log")), key=os.path.getmtime, reverse=True)[:5]
    for f in files:
        for line in reversed(_tail(f).splitlines()):
            if '"rate_limit_event"' not in line:
                continue
            try:
                info = json.loads(line).get("rate_limit_info") or {}
            except ValueError:
                continue
            uw = info.get("unifiedWindows") or {}
            fh, sd = uw.get("five_hour") or {}, uw.get("seven_day") or {}
            pct = lambda x: None if x is None else round(float(x) * 100)
            return {"5h": pct(fh.get("utilization")), "5h_reset": fh.get("resetsAt"),
                    "week": pct(sd.get("utilization")), "week_reset": sd.get("resetsAt"), "at": os.path.getmtime(f)}
    return None


def usage_gemini(room):
    total = 0
    for line in _tail(os.path.join(LOCAL, "seats", room.id, "Gemini.log"), 8 << 20).splitlines():
        if '"step_type"' in line and '"usage"' in line:
            try:
                total += int((_find_key(json.loads(line), "usage") or {}).get("total_tokens") or 0)
            except (ValueError, AttributeError):
                pass
    return {"tokens": total}


def seat_usage(room):
    key = room.id
    hit = USAGE_CACHE.get(key)
    if hit and time.time() - hit[0] < 30:
        return hit[1]
    zh = (room.meta.get("lang") or DEFAULT_LANG) == "zh-TW"
    out = {}
    for seat, fn in (("GPT", usage_gpt), ("Claude", usage_claude)):
        try:
            u = fn()
        except Exception:
            u = None
        if u and u.get("5h") is not None:
            line = (f"5 小時 {u['5h']:.0f}%・本週 {u['week'] or 0:.0f}%" if zh
                    else f"5h {u['5h']:.0f}% · week {u['week'] or 0:.0f}%")
            tip = (f"5 小時額度 {_clock(u['5h_reset'])} 恢復;本週額度 {_clock(u['week_reset'])} 恢復(帳號整體用量,{_clock(u['at'])} 更新)"
                   if zh else f"5h window resets {_clock(u['5h_reset'])}; weekly resets {_clock(u['week_reset'])} "
                              f"(whole account, updated {_clock(u['at'])})")
            out[seat] = {"line": line, "tip": tip, "high": u["5h"] >= 80}
    try:
        g = usage_gemini(room)["tokens"]
    except Exception:
        g = 0
    out["Gemini"] = {"line": (f"本場 {g / 10000:.1f} 萬 token" if zh else f"{g / 1000:.0f}k tokens this meeting"),
                     "tip": ("Google 沒有提供剩餘額度,只能顯示這場會議用掉的量" if zh
                             else "Google does not expose remaining quota; this is what this meeting used"), "high": False}
    USAGE_CACHE[key] = (time.time(), out)
    return out


def _exit_reason(room, seat):
    try:
        with open(os.path.join(LOCAL, "seats", room.id, f"{seat}.log"), encoding="utf-8", errors="replace") as f:
            tail = f.read()[-6000:]
    except OSError:
        return "?"
    if LIMIT_RE.search(tail):
        when = re.search(r"try again at ([^.\n\"]+)", tail)
        return "limit:" + (when.group(1).strip() if when else "")
    m = re.search(r'required the "([a-z_]+)" permission', tail)
    if m:
        return m.group(1) + " denied"
    return "exited"


def watchdog():
    while True:
        time.sleep(10)
        for room in list(ROOMS.values()):
            if room.meta.get("closed"):
                continue
            for seat in room_seats(room):
                p = room.procs.get(seat)
                if p is None or p.poll() is None or seat not in (room.meta.get("tickets") or {}):
                    continue
                key = (room.id, seat)
                recent = [t for t in RESTARTS.get(key, []) if time.time() - t < 900]
                why = _exit_reason(room, seat)
                room.procs.pop(seat, None)
                if why.startswith("limit:"):
                    room.add("system", tx(room, "limit_hit", seat=seat, when=why[6:] or "?"))
                    USAGE_CACHE.pop(room.id, None)
                    continue
                if len(recent) >= 3:
                    room.add("system", tx(room, "auto_gave_up", seat=seat, why=why))
                    RESTARTS[key] = recent
                    continue
                RESTARTS[key] = recent + [time.time()]
                try:
                    start_seat(room, seat)
                    room.add("system", tx(room, "auto_back", seat=seat, why=why))
                except Exception as e:
                    room.add("system", tx(room, "seat_fail", seat=seat, err=e))


def resume_seats():
    for room in list(ROOMS.values()):
        if room.meta.get("closed"):
            continue
        for seat in room_seats(room):
            if seat not in (room.meta.get("tickets") or {}):
                continue
            try:
                start_seat(room, seat)
                room.add("system", tx(room, "resumed", seat=seat))
            except Exception as e:
                room.add("system", tx(room, "seat_fail", seat=seat, err=e))


def stop_seat(room, seat):
    (room.meta.get("tickets") or {}).pop(seat, None)
    room.save_meta()
    p = room.procs.pop(seat, None)
    if p is not None and p.poll() is None:
        p.terminate()
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
    with room.cond:
        room.cond.notify_all()


def kept_attachments(room):
    with_files = [m["seq"] for m in room.msgs if m["who"] != "user" and m.get("imgs")]
    adopted, vetoed = set(), set()
    for m in room.msgs:
        if m["who"] != "user":
            continue
        hit = re.match(r"↩ #(\d+)", m["text"] or "")
        if not hit:
            continue
        seq, rest = int(hit.group(1)), m["text"][hit.end():]
        if "✕" in rest:
            vetoed.add(seq)
            adopted.discard(seq)
        elif "✓" in rest:
            adopted.add(seq)
            vetoed.discard(seq)
    keep = {q for q in with_files if q in adopted}
    rest = [q for q in with_files if q not in vetoed]
    if rest:
        keep.add(rest[-1])
    return keep


def export_room(room):
    proj = room.meta.get("project") or DEFAULT_PROJECT
    if not os.path.isdir(proj):
        proj = DEFAULT_PROJECT
    day = (room.meta.get("created") or now_iso())[:10]
    slug = re.sub(r'[\\/:*?"<>|\s]+', "_", room.meta["title"]).strip("_")[:40] or room.id
    out = room.meta.get("export") or os.path.join(proj, EXPORT_SUBDIR, f"{day}_{slug}")
    if os.path.exists(out) and room.meta.get("export") != out:
        out += "_" + room.id[-4:]
    os.makedirs(out, exist_ok=True)
    L = tx(room, "transcript")
    name = {"user": tx(room, "host"), "system": tx(room, "system")}
    lines = [f"# {room.meta['title']}", "",
             f"- {L['time']}: {room.meta.get('created', '')[:16].replace('T', ' ')}",
             f"- {L['project']}: {room.meta.get('project')}",
             f"- {L['type']}: {tx(room, 'modes')[room.meta.get('mode') or 'discuss']} · {tx(room, 'leads')[room.meta.get('lead') or '']}",
             f"- {L['models']}: " + " / ".join(f"{s} {seat_label(room, s)}" for s in room_seats(room))]
    if room.meta.get("branch"):
        lines.append(f"- {L['worktree']}: {room.meta.get('worktree')} (`{room.meta['branch']}`, {L['merge']})")
    lines += ["", f"## {L['topic']}", "", room.meta.get("topic", ""), "", f"## {L['log']}", ""]
    keep = kept_attachments(room)
    for m in room.msgs:
        if m["who"] == "system":
            lines += [f"> {m['at'][11:16]} {m['text']}", ""]
            continue
        lines += [f"### {name.get(m['who'], m['who'])} ({m['at'][11:16]})", "", m["text"], ""]
        for f in m.get("imgs") or []:
            src, dst = os.path.join(room.dir, f), os.path.join(out, f)
            if m["seq"] not in keep:
                if os.path.isfile(dst):
                    os.remove(dst)
                lines += [f"`{f}` ({L['dropped']})", ""]
                continue
            if os.path.splitext(f)[1].lower() in MEDIA_EXT:
                lines += [f"`{f}` ({L['media']})", ""]
                continue
            if os.path.isfile(src):
                shutil.copyfile(src, dst)
                lines += [f"[{f}]({f})" if f.lower().endswith(tuple(PAGE_EXT)) else f"![]({f})", ""]
    with open(os.path.join(out, "transcript.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    shutil.copyfile(os.path.join(room.dir, "log.jsonl"), os.path.join(out, "log.jsonl"))
    room.meta["export"] = out
    room.save_meta()
    return out


def close_room(room):
    with room.cond:
        room.meta["closed"] = True
        room.save_meta()
        room.cond.notify_all()
    room.add("system", tx(room, "closed"))

    def reap():
        end = time.time() + 30
        while time.time() < end and any(p.poll() is None for p in room.procs.values()):
            time.sleep(1)
        for p in room.procs.values():
            if p.poll() is None:
                p.terminate()
        try:
            out = export_room(room)
            room.add("system", tx(room, "exported", path=out))
            export_room(room)
        except Exception as e:
            room.add("system", tx(room, "export_fail", err=e))
    threading.Thread(target=reap, daemon=True).start()


_TICKET = {"type": "string", "description": "Your seat ticket from your instructions. Required on every call."}
TOOLS = [
    {"name": "join_meeting",
     "description": "Enter the meeting. Returns the topic, rules and every message so far. Call once at the start.",
     "inputSchema": {"type": "object", "properties": {
         "room": {"type": "string", "description": "meeting id"},
         "name": {"type": "string", "enum": list(SEATS), "description": "your seat"},
         "ticket": _TICKET}, "required": ["room", "name", "ticket"]}},
    {"name": "send_message",
     "description": "Speak in the meeting, in the meeting's language. To show the host a mock-up or animation, put a "
                    "complete self-contained HTML page in `html`; to show an existing image or HTML file, put its full "
                    "path in attach_path. The room shows it right under your message and HTML stays interactive, so "
                    "never ask the host to open a URL or start a server.",
     "inputSchema": {"type": "object", "properties": {
         "room": {"type": "string"}, "name": {"type": "string", "enum": list(SEATS)},
         "text": {"type": "string"},
         "html": {"type": "string", "description": "A complete self-contained HTML page (inline CSS/JS, no external "
                  "URLs) to show under your message, e.g. a mock-up or animation. No file writing needed."},
         "attach_path": {"type": "string"}, "image_path": {"type": "string"},
         "ticket": _TICKET},
         "required": ["room", "name", "ticket", "text"]}},
    {"name": "wait_for_messages",
     "description": "Wait for new messages from the host or the other AI. after_seq = the last message number you "
                    "have seen. Returns at once if there is something new; otherwise returns an empty list after up "
                    "to timeout_sec seconds — then just call it again. closed=true means the host closed the "
                    "meeting: say one closing line and stop.",
     "inputSchema": {"type": "object", "properties": {
         "room": {"type": "string"}, "name": {"type": "string", "enum": list(SEATS)},
         "after_seq": {"type": "integer"}, "timeout_sec": {"type": "integer", "description": f"max {WAIT_MAX}"},
         "ticket": _TICKET}, "required": ["room", "name", "ticket", "after_seq"]}},
    {"name": "read_messages",
     "description": "Read every message after after_seq without waiting.",
     "inputSchema": {"type": "object", "properties": {
         "room": {"type": "string"}, "after_seq": {"type": "integer"}}, "required": ["room", "after_seq"]}},
]


def fmt(room, msgs):
    host = tx(room, "host")
    return [{"seq": m["seq"], "who": host if m["who"] == "user" else m["who"], "text": m["text"],
             "has_image": bool(m.get("imgs")), "files": [attach_info(room, f) for f in m.get("imgs") or []],
             "at": m["at"]} for m in msgs]


def call_tool(name, a):
    room = get_room(a.get("room", ""))
    seat = a.get("name")
    if name != "read_messages" and seat not in SEATS:
        return {"ok": False, "reason": f"`name` is required and must be your seat: one of {', '.join(SEATS)}."}
    if seat:
        if seat not in SEATS:
            raise KeyError(f"no such seat: {seat}")
        if str(a.get("ticket") or "") != (room.meta.get("tickets") or {}).get(seat):
            return {"ok": False, "stop": True, "reason": tx(room, "stale")}
    closed = room.meta.get("closed", False)
    if name == "join_meeting":
        return {"title": room.meta["title"], "topic": room.meta["topic"], "you": seat, "closed": closed,
                "rules": tx(room, "rules", n=run_limit(room)), "messages": fmt(room, room.msgs),
                "last_seq": len(room.msgs)}
    if name == "read_messages":
        after = int(a.get("after_seq", 0))
        return {"messages": fmt(room, room.msgs[after:]), "last_seq": len(room.msgs), "closed": closed}
    if name == "send_message":
        if closed:
            return {"ok": False, "reason": tx(room, "closed_no_speak")}
        if room.ai_run() >= run_limit(room):
            return {"ok": False, "reason": tx(room, "run_limit", n=run_limit(room))}
        text = (a.get("text") or "").strip()
        if not text:
            return {"ok": False, "reason": tx(room, "empty")}
        imgs = []
        page = a.get("html")
        if isinstance(page, str) and page.strip():
            if len(page.encode("utf-8")) > ATTACH_MAX:
                return {"ok": False, "reason": tx(room, "bad_image", p="html", img_mb=ATTACH_MAX >> 20,
                                                  media_mb=MEDIA_MAX >> 20)}
            fn = f"{len(room.msgs) + 1:03d}_{seat}_page.html"
            with open(os.path.join(room.dir, fn), "w", encoding="utf-8") as f:
                f.write(page)
            imgs.append(fn)
        for ip in [x for x in (a.get("attach_path"), a.get("image_path")) if x]:
            ext = os.path.splitext(ip)[1].lower()
            if ext not in ALL_EXT or not os.path.isfile(ip) or not size_ok(ip, ext):
                return {"ok": False, "reason": tx(room, "bad_image", p=ip, img_mb=ATTACH_MAX >> 20,
                                                  media_mb=MEDIA_MAX >> 20)}
            fn = f"{len(room.msgs) + 1:03d}_{seat}_{len(imgs) + 1}{ext}"
            shutil.copyfile(ip, os.path.join(room.dir, fn))
            imgs.append(fn)
            frames_later(room, fn)
        seq = room.add(seat, text, imgs)["seq"]
        if room.meta.get("auto") and text.startswith(DONE_MARK):
            room.meta["auto"] = False
            room.save_meta()
            room.add("system", tx(room, "auto_done"))
        return {"ok": True, "seq": seq}
    if name == "wait_for_messages":
        after = int(a.get("after_seq", 0))
        cap = 50 if seat == "Gemini" else WAIT_MAX
        end = time.time() + max(5, min(int(a.get("timeout_sec") or cap), cap))
        room.waiting[seat] = True
        try:
            with room.cond:
                while not ([m for m in room.msgs[after:] if m["who"] != seat] or room.meta.get("closed")):
                    left = end - time.time()
                    if left <= 0:
                        break
                    room.cond.wait(timeout=min(left, 15))
        finally:
            room.waiting[seat] = False
            room.busy_since[seat] = time.time()
        new = room.msgs[after:]
        return {"messages": fmt(room, new), "last_seq": len(room.msgs), "closed": room.meta.get("closed", False),
                "can_speak": room.ai_run() < run_limit(room), "hint": "" if new else tx(room, "no_new"),
                "run_left": max(0, run_limit(room) - room.ai_run()), "run_limit": run_limit(room),
                "run_note": tx(room, "run_left", left=max(0, run_limit(room) - room.ai_run()), n=run_limit(room))}
    raise KeyError(f"no such tool: {name}")


def mcp_handle(req):
    mid, method = req.get("id"), req.get("method", "")
    if mid is None:
        return None
    try:
        if method == "initialize":
            res = {"protocolVersion": (req.get("params") or {}).get("protocolVersion", "2025-06-18"),
                   "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": {"name": "ai-meeting-room", "version": VERSION},
                   "instructions": "Meeting room. Call join_meeting first, then alternate send_message and "
                                   "wait_for_messages. Speak in the meeting's language."}
        elif method == "ping":
            res = {}
        elif method == "tools/list":
            res = {"tools": TOOLS}
        elif method == "tools/call":
            p = req.get("params") or {}
            try:
                out = call_tool(p.get("name"), p.get("arguments") or {})
                res = {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}], "isError": False}
            except Exception as e:
                res = {"content": [{"type": "text", "text": f"error: {e}"}], "isError": True}
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unsupported: {method}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": res}
    except Exception as e:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body=b"", ctype="application/json; charset=utf-8", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, ctype):
        size = os.path.getsize(path)
        start, end = 0, size - 1
        rng = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range") or "")
        if rng and (rng.group(1) or rng.group(2)):
            if rng.group(1):
                start = int(rng.group(1))
                end = min(int(rng.group(2)), size - 1) if rng.group(2) else size - 1
            else:
                start = max(size - int(rng.group(2)), 0)
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            with open(path, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _upload(self, room, query):
        name = (parse_qs(query).get("name") or [""])[0]
        ext = os.path.splitext(name)[1].lower()
        n = int(self.headers.get("Content-Length") or 0)
        if room.meta.get("closed"):
            return self._send(400, {"error": tx(room, "closed_no_speak")})
        if ext not in ALL_EXT or n <= 0 or not size_ok(n, ext):
            return self._send(400, {"error": tx(room, "bad_image", p=name, img_mb=ATTACH_MAX >> 20,
                                                  media_mb=MEDIA_MAX >> 20)})
        fn = f"up_{uuid.uuid4().hex[:10]}{ext}"
        dst = os.path.join(room.dir, fn)
        left = n
        with open(dst, "wb") as f:
            while left > 0:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        if left > 0:
            os.remove(dst)
            return self._send(400, {"error": "upload interrupted"})
        frames_later(room, fn)
        return self._send(200, {"file": fn})

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        return json.loads(raw.decode("utf-8")) if raw else {}

    def _local_origin(self):
        org = self.headers.get("Origin")
        return org is None or org in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}") or org in ALLOWED_ORIGINS

    def do_GET(self):
        u = urlparse(self.path)
        parts = [unquote(x) for x in u.path.strip("/").split("/") if x]
        if u.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "ui.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if u.path == "/mcp":
            return self._send(405, {"error": "use POST"})
        if u.path == "/api/info":
            return self._send(200, {"version": VERSION, "lang": DEFAULT_LANG, "project": DEFAULT_PROJECT,
                                    "codex": find_codex(), "claude": find_claude(), "data": LOCAL,
                                    "host_name": T["zh-TW"]["host"]})
        if u.path == "/api/agents":
            return self._send(200, agents())
        if u.path == "/api/models":
            return self._send(200, model_options())
        if u.path == "/api/projects":
            return self._send(200, known_projects())
        if parts == ["api", "rooms"]:
            rows = [{"id": r.id, "title": r.meta["title"], "created": r.meta["created"],
                     "closed": r.meta.get("closed", False), "count": len(r.msgs)} for r in ROOMS.values()]
            return self._send(200, sorted(rows, key=lambda x: x["created"], reverse=True))
        if parts == ["api", "archives"]:
            rows = []
            for a in archives():
                title, _, _ = _arc_head(a["dir"])
                with open(os.path.join(a["dir"], "log.jsonl"), encoding="utf-8") as fh:
                    lines = [ln for ln in fh if ln.strip()]
                created = json.loads(lines[0]).get("at", "") if lines else ""
                rows.append({"id": a["id"], "title": title, "created": created, "count": len(lines)})
            return self._send(200, sorted(rows, key=lambda x: x["created"], reverse=True))
        if parts[:2] == ["api", "rooms"] and len(parts) == 4 and parts[3] == "messages" and parts[2].startswith(ARC_PREFIX):
            try:
                a = get_archive(parts[2])
            except KeyError as e:
                return self._send(404, {"error": str(e)})
            after = int(parse_qs(u.query).get("after", ["0"])[0])
            title, topic, kind = _arc_head(a["dir"])
            msgs = archive_messages(a)
            meta = {"title": title, "topic": topic, "project": a["project"], "mode": kind, "archive": True,
                    "closed": True, "export": a["dir"], "created": msgs[0]["at"] if msgs else ""}
            return self._send(200, {"meta": meta, "messages": msgs[after:], "last_seq": len(msgs), "seats": {},
                                    "usage": {}, "labels": {}, "ai_run": 0, "ai_limit": 1})
        if parts[:2] == ["api", "rooms"] and len(parts) == 4 and parts[3] == "messages":
            try:
                r = get_room(parts[2])
            except KeyError as e:
                return self._send(404, {"error": str(e)})
            after = int(parse_qs(u.query).get("after", ["0"])[0])
            meta = {k: v for k, v in r.meta.items() if k != "tickets"}
            return self._send(200, {"meta": meta, "messages": r.msgs[after:], "last_seq": len(r.msgs),
                                    "seats": {s: r.state(s) for s in room_seats(r)},
                                    "usage": seat_usage(r),
                                    "labels": {s: seat_label(r, s) for s in room_seats(r)},
                                    "ai_run": r.ai_run(), "ai_limit": run_limit(r), "ai_limit_off": AI_RUN_LIMIT,
                                    "busy_sec": {s: int(time.time() - r.busy_since[s]) for s in room_seats(r)
                                                 if r.state(s) == "thinking" and s in r.busy_since}})
        if parts[:1] == ["files"] and len(parts) == 3:
            if any(x in ("..", "") or "/" in x or "\\" in x for x in parts[1:]):
                return self._send(404, {"error": "not found"})
            if parts[1].startswith(ARC_PREFIX):
                try:
                    p = os.path.join(get_archive(parts[1])["dir"], parts[2])
                except KeyError:
                    return self._send(404, {"error": "not found"})
            else:
                p = os.path.join(DATA, parts[1], parts[2])
            ext = os.path.splitext(p)[1].lower()
            if ext not in ALL_EXT or not os.path.isfile(p):
                return self._send(404, {"error": "not found"})
            if ext in MEDIA_EXT:
                return self._send_file(p, MEDIA_EXT[ext])
            with open(p, "rb") as f:
                data = f.read()
            if ext in PAGE_EXT:
                return self._send(200, data, "text/html; charset=utf-8",
                                  headers={"Content-Security-Policy": "sandbox allow-scripts allow-forms allow-modals",
                                           "X-Content-Type-Options": "nosniff"})
            return self._send(200, data, "image/jpeg" if ext in (".jpg", ".jpeg") else f"image/{ext[1:]}",
                              headers={"Access-Control-Allow-Origin": "*"})
        return self._send(404, {"error": "not found"})

    def do_DELETE(self):
        return self._send(200, {})

    def do_POST(self):
        u = urlparse(self.path)
        parts = [unquote(x) for x in u.path.strip("/").split("/") if x]
        if u.path == "/mcp":
            try:
                req = self._body()
            except Exception:
                return self._send(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            if isinstance(req, list):
                out = [x for x in (mcp_handle(r) for r in req) if x is not None]
                return self._send(200, out) if out else self._send(202)
            out = mcp_handle(req)
            if out is None:
                return self._send(202)
            hdr = {"Mcp-Session-Id": uuid.uuid4().hex} if req.get("method") == "initialize" else None
            return self._send(200, out, headers=hdr)
        if not self._local_origin():
            return self._send(403, {"error": "local page only"})
        if parts[:2] == ["api", "rooms"] and len(parts) == 4 and parts[3] == "upload":
            try:
                return self._upload(get_room(parts[2]), u.query)
            except KeyError:
                return self._send(404, {"error": "not found"})
        try:
            b = self._body()
            if parts == ["api", "shutdown"]:
                for room in list(ROOMS.values()):
                    for p in list(room.procs.values()):
                        if p.poll() is None:
                            p.terminate()
                self._send(200, {"ok": True})
                threading.Thread(target=SERVER.shutdown, daemon=True).start()
                return
            if parts == ["api", "agy-allow"]:
                allow_meeting_in_agy()
                return self._send(200, {"ok": agy_allows_meeting()})
            if parts == ["api", "rooms"]:
                return self._create(b)
            if parts[:2] == ["api", "rooms"] and len(parts) == 4:
                r, act = get_room(parts[2]), parts[3]
                if act == "messages":
                    text = (b.get("text") or "").strip()
                    files = [f for f in (b.get("files") or []) if isinstance(f, str) and f.startswith("up_")
                             and os.path.basename(f) == f and os.path.isfile(os.path.join(r.dir, f))]
                    if not text and not files:
                        return self._send(400, {"error": tx(r, "empty")})
                    if r.meta.get("closed"):
                        return self._send(400, {"error": tx(r, "closed_no_speak")})
                    return self._send(200, r.add("user", text, files))
                if act == "close":
                    if not r.meta.get("closed"):
                        close_room(r)
                    return self._send(200, {"ok": True})
                if act == "auto":
                    if r.meta.get("closed"):
                        return self._send(400, {"error": tx(r, "closed_no_speak")})
                    on = bool(b.get("on"))
                    r.meta["auto"] = on
                    r.save_meta()
                    r.add("system", tx(r, "auto_on", n=AUTO_RUN_LIMIT) if on else tx(r, "auto_off", n=AI_RUN_LIMIT))
                    return self._send(200, {"ok": True, "auto": on})
                if act == "lead":
                    s = b.get("seat") or ""
                    if (s and s not in SEATS) or r.meta.get("closed"):
                        return self._send(400, {"error": "invalid seat or meeting closed"})
                    if s and not r.meta.get("worktree"):
                        try:
                            r.meta["worktree"], r.meta["branch"], r.meta["git_common"] = make_worktree(
                                r.meta.get("project") or DEFAULT_PROJECT, r.id, r.meta.get("lang") or DEFAULT_LANG)
                        except RuntimeError as e:
                            return self._send(400, {"error": str(e)})
                    r.meta["lead"] = s
                    r.save_meta()
                    if s:
                        guard_project(r)
                    r.add("system", tx(r, "lead_set", seat=s, path=r.meta.get("worktree")) if s else tx(r, "lead_off"))
                    for seat in room_seats(r):
                        p = r.procs.get(seat)
                        if p is not None and p.poll() is None:
                            try:
                                start_seat(r, seat, restart=True)
                            except Exception as e:
                                r.add("system", tx(r, "seat_fail", seat=seat, err=e))
                    return self._send(200, {"ok": True, "lead": s})
                if act == "invite":
                    s = b.get("seat")
                    if s not in SEATS or r.meta.get("closed"):
                        return self._send(400, {"error": "invalid seat or meeting closed"})
                    if "cfg" in b:
                        r.meta.setdefault("seat_cfg", {})[s] = clean_cfg({s: b["cfg"]})[s]
                        remember_models({s: r.meta["seat_cfg"][s]})
                    if s not in room_seats(r):
                        r.meta["seats"] = room_seats(r) + [s]
                    r.save_meta()
                    try:
                        res = start_seat(r, s)
                    except Exception as e:
                        r.add("system", tx(r, "seat_fail", seat=s, err=e))
                        return self._send(400, {"error": str(e)})
                    r.add("system", tx(r, "invited", seat=s, label=seat_label(r, s)))
                    return self._send(200, {"result": res})
                if act == "dismiss":
                    s = b.get("seat")
                    if s not in room_seats(r):
                        return self._send(400, {"error": "not in the meeting"})
                    stop_seat(r, s)
                    r.meta["seats"] = [x for x in room_seats(r) if x != s]
                    r.save_meta()
                    r.add("system", tx(r, "dismissed", seat=s))
                    return self._send(200, {"ok": True})
                if act == "delete":
                    for x in list(r.procs):
                        stop_seat(r, x)
                    with ROOMS_LOCK:
                        ROOMS.pop(r.id, None)
                    shutil.rmtree(r.dir, ignore_errors=True)
                    shutil.rmtree(os.path.join(LOCAL, "seats", r.id), ignore_errors=True)
                    return self._send(200, {"ok": True, "kept": r.meta.get("export") or ""})
                if act == "seat":
                    s = b.get("seat")
                    if s not in SEATS or r.meta.get("closed"):
                        return self._send(400, {"error": "invalid seat or meeting closed"})
                    if "cfg" in b:
                        r.meta.setdefault("seat_cfg", {})[s] = clean_cfg({s: b["cfg"]})[s]
                        remember_models({s: r.meta["seat_cfg"][s]})
                        r.save_meta()
                        res = start_seat(r, s, restart=True)
                        r.add("system", tx(r, "model_changed", seat=s, label=seat_label(r, s)))
                        return self._send(200, {"result": res})
                    return self._send(200, {"result": start_seat(r, s)})
            return self._send(404, {"error": "not found"})
        except KeyError as e:
            return self._send(404, {"error": str(e)})
        except Exception as e:
            return self._send(500, {"error": str(e)})

    def _create(self, b):
        title, topic = (b.get("title") or "").strip(), (b.get("topic") or "").strip()
        lang = b.get("lang") or DEFAULT_LANG
        if not title or not topic:
            return self._send(400, {"error": "title and topic are required / 標題與議題說明都要填"})
        proj = os.path.normpath((b.get("project") or DEFAULT_PROJECT).strip())
        if not os.path.isdir(proj):
            return self._send(400, {"error": f"folder not found / 找不到資料夾: {proj}"})
        lead, mode = b.get("lead") or "", b.get("mode") or "discuss"
        if lead not in ("", *SEATS) or mode not in ("discuss", "review") or lang not in LANGS:
            return self._send(400, {"error": "invalid lead, mode or language"})
        seats = [x for x in (b.get("seats") or []) if x in SEATS]
        given = {k: v for k, v in clean_cfg(b.get("seat_cfg")).items() if k in (b.get("seat_cfg") or {})}
        seat_cfg = {**{k: v for k, v in last_models().items() if k in SEATS}, **given}
        remember_models({k: v for k, v in given.items() if k in seats})
        remember_project(proj)
        try:
            r = new_room(title, topic, clean_cfg(seat_cfg), proj, lead, mode, lang, seats)
        except RuntimeError as e:
            return self._send(400, {"error": str(e)})
        started = {}
        for s in seats:
            try:
                started[s] = start_seat(r, s)
            except Exception as e:
                started[s] = f"failed: {e}"
                r.add("system", tx(r, "seat_fail", seat=s, err=e))
        return self._send(200, {"id": r.id, "seats": started})


SERVER = None


def main():
    global SERVER
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_rooms()
    SERVER = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    SERVER.daemon_threads = True
    threading.Thread(target=resume_seats, daemon=True).start()
    threading.Thread(target=watchdog, daemon=True).start()
    print(f"AI Meeting Room {VERSION}: http://127.0.0.1:{PORT}/", flush=True)
    print(f"data: {LOCAL}\ncodex: {find_codex() or 'NOT FOUND'}\nclaude: {find_claude() or 'NOT FOUND'}", flush=True)
    SERVER.serve_forever()


if __name__ == "__main__":
    main()
