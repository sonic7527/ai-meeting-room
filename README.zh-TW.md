# AI 會議室

**讓 Claude、GPT、Gemini 跟你在同一間會議室討論。** 每位 AI 各自發言,你在瀏覽器即時看到整個討論,隨時可以插話。不用你手動傳話;除了各家 AI 自己連回自家伺服器,資料不會離開你的電腦。

[English](README.md)

- **用你已經有的訂閱**:Claude 走 Claude Code(你的 Claude 帳號)、GPT 走 OpenAI Codex(你的 ChatGPT 帳號)、Gemini 走 Antigravity 命令列程式(你的 Google 帳號)。不需要 API 金鑰。
- **自動偵測**電腦裡裝了、登入了哪幾位。你按「邀請」才入席,開會中隨時可以再邀請或請某位離席。
- **你是主持人**:AI 先回應你的插話;你每則發言下方標示誰已回應;AI 不會自己結束會議;你沒發言時 AI 連講 8 則就自動暫停等你;你否決了,它會立刻改版。
- **像聊天軟體一樣好用**:在任何一則訊息上按右鍵可以回覆它、一鍵 ✕ 否決或 ✓ 採用;Enter 送出、Shift+Enter 換行。
- **樣板直接貼在對話裡**:AI 可以把單一網頁檔跟著發言一起貼上,直接嵌在對話裡,動畫、按鈕、拖曳都能操作,不用另外開網址。
- **同一個專案、同一套背景**:選一個資料夾,每位 AI 發言前都先讀同樣的專案說明檔(CLAUDE.md、AGENTS.md、GEMINI.md、README)。
- **主審與輔助**:可以指定一位 AI 當主審,所有改程式和 git 提交都由它做,而且**只在專案外的 git 獨立副本裡做**;其他 AI 負責檢查、做主審指派的唯讀工作。
- **每位 AI 可以各自選模型和思考深度**,會議中也能換,而且會記住你上次的選擇。
- **可以同時開好幾場會議**,每場一個瀏覽器分頁;舊會議可以從清單刪除。
- **自動修復**:AI 意外離席會被自動請回;會議室重啟後,進行中的會議會自動把 AI 請回來。
- **散會時逐字稿自動存進你的專案**(`docs/meetings/<日期>_<標題>/transcript.md`)。
- **只留採用的附件**:按過 ✓ 的樣板與圖片,加上最後一則沒被否決的,才會存進專案;其他(包括按 ✕ 否決的版本)不存、逐字稿標「未保留」,資料夾不會越來越大。
- 介面和會議語言支援英文、繁體中文。
- 只有一個 Python 檔,只用標準函式庫,只在本機 `127.0.0.1` 執行。

## 需要什麼

- Python 3.9 以上
- git(只有主審模式需要)
- 下面三個至少裝一個:

| 席位 | 安裝 | 登入 |
|---|---|---|
| Claude | [Claude Code](https://claude.com/claude-code)(`claude` 命令列程式,或內含它的 Claude 桌面版) | 你的 Claude 帳號 |
| GPT | [OpenAI Codex](https://openai.com/codex)(桌面版或 `npm i -g @openai/codex`) | 你的 ChatGPT 帳號 |
| Gemini | Antigravity 命令列程式。Windows:`irm https://antigravity.google/cli/install.ps1 \| iex`([官方文件](https://antigravity.google/docs/cli/headless/)) | 執行一次 `agy`,用 Google 帳號登入 |

> 個人 Google 帳號從 2026 年 6 月起已不能用 Gemini CLI,官方改用 Antigravity 命令列程式(`agy`)取代,本專案用的是 `agy`。

## 快速開始

```bash
git clone https://github.com/sonic7527/ai-meeting-room ~/ai-meeting-room
```

在背景啟動會議室:

```bash
# Windows
powershell -ExecutionPolicy Bypass -File ~/ai-meeting-room/start_bg.ps1
# macOS / Linux
bash ~/ai-meeting-room/start_bg.sh
```

打開 <http://127.0.0.1:7720/>,按「開新會議」,選專案、寫議題,按「開會」,再按「邀請」請 AI 入席。

### 更新

```bash
git -C ~/ai-meeting-room pull
# Windows
powershell -ExecutionPolicy Bypass -File ~/ai-meeting-room/start_bg.ps1 -Restart
# macOS / Linux
bash ~/ai-meeting-room/start_bg.sh --restart
```

進行中的會議不受影響:AI 會自動重新入席,讀完前面的對話接著討論。

### Gemini 第一次要做的設定

Antigravity 命令列程式在背景執行時沒辦法跳出詢問,要先在它的設定裡允許會議室工具。在「邀請」(或「開新會議」)視窗的 Gemini 欄位按「允許會議室工具」,它只會在 `~/.gemini/antigravity-cli/settings.json` 加一條 `mcp(meeting/*)` 規則,其他都不動。

### 選用:給 Claude Code 的「開會」指令

把 `skills/開會`(中文)或 `skills/meeting`(英文)用捷徑連結放進 `~/.claude/skills/`,之後 `git pull` 指令也會跟著更新:

```bash
# Windows(PowerShell,不需要系統管理員)
New-Item -ItemType Junction -Path "$HOME\.claude\skills\開會" -Target "$HOME\ai-meeting-room\skills\開會"
# macOS / Linux
ln -s ~/ai-meeting-room/skills/開會 ~/.claude/skills/開會
```

之後跟 Claude 說「開會討論……」,它會啟動會議室、用目前的專案開一場空的會議、在 Chrome 開新分頁,等你散會後讀逐字稿向你回報。如果不是裝在 `~/ai-meeting-room`,請設定環境變數 `AI_MEETING_ROOM_DIR`。

## 運作方式

```
 你(瀏覽器) ──▶ ┌──────────────────────────────┐ ◀── Claude (claude -p)
                 │  hub.py  127.0.0.1:7720       │ ◀── GPT    (codex exec)
                 │  網頁介面 + MCP 入口 /mcp     │ ◀── Gemini (agy -p)
                 └──────────────────────────────┘
```

開會時,伺服器在背景啟動受邀的 AI,給它一份入席說明(規則、角色、議題)。每位 AI 透過四個工具開會:`join_meeting`(入席)、`send_message`(發言)、`wait_for_messages`(等新發言)、`read_messages`(讀紀錄),一直待到你散會。每次入席都會發一張新的入席證,舊的或重複的程序會被請離席。

## 安全設計

| 角色 | 能做什麼 |
|---|---|
| 平等討論(預設) | 大家都只能讀檔、用唯讀的 git 指令(status、diff、log、show、blame),不能改檔 |
| 主審 | 改檔和提交**只在 git 獨立副本裡做**(新分支 `meeting/<時間>`,放在專案外,只有受 git 管理的檔案,沒有 `.env` 等未納管的機密檔)。Claude 主審能用的指令有白名單(git 不含 push、語法檢查);Codex 在它自己的沙盒裡執行;`agy` 在背景模式會拒絕終端機指令。推送、部署、刪檔、動到正式環境一律要先在會議室問你 |
| 輔助 | 只能讀,加上做主審指派的唯讀工作 |

Claude 席位只讀專案共用的設定(`--setting-sources project`),你個人平常允許過的指令不會讓席位的權限變大。樣板是放在發言裡的網頁內容,唯讀的席位不必寫檔;嵌進對話的網頁在隔離框裡執行,動不了會議室。主審的分支要不要合併回來,由你決定。伺服器只聽本機 `127.0.0.1`,也會擋掉其他網頁發來的寫入。AI 的執行紀錄(含它們讀過的檔案內容)只留在資料夾,不會寫進你的專案。

**不過 AI 還是可能出錯。** 開會時請看著,合併主審的改動前先看過差異,也不要把含有機密、你不願讓 AI 廠商看到的資料夾交給它們。

## 設定

可以設環境變數,或在 `hub.py` 旁邊放一個 `config.json`(不會進 git),例如
`{"lang": "zh-TW", "host_name": "站長"}`。可用的鍵:`host_name`、`lang`、`port`、`project`、`home`、`export_dir`、`ai_run_limit`。兩者都有時以環境變數為準。

| 環境變數 | 預設 | 意思 |
|---|---|---|
| `MEETING_PORT` | `7720` | 連接埠 |
| `MEETING_LANG` | `en` | 預設會議語言(`en`、`zh-TW`) |
| `MEETING_PROJECT` | 目前資料夾 | 預設專案 |
| `MEETING_HOME` | `%LOCALAPPDATA%\ai-meeting-room`/`~/.local/share/ai-meeting-room` | 進行中的會議、AI 執行紀錄、主審副本 |
| `MEETING_EXPORT_DIR` | `docs/meetings` | 逐字稿存放位置(相對於專案) |
| `MEETING_AI_RUN_LIMIT` | `8` | 你沒發言時 AI 最多連講幾則 |
| `MEETING_HOST_NAME` | `主持人` | 中文會議裡 AI 怎麼稱呼你 |
| `CLAUDE_BIN`、`CODEX_BIN`、`AGY_BIN` | 自動 | 三個命令列程式的路徑 |

## 目前狀態與已知限制

- 在 **Windows 11** 開發與測試(Claude Code 2.1、Codex 命令列 0.159、Antigravity 命令列 Gemini 3.8 Flash)。macOS/Linux 的路徑已寫好但還沒實測,歡迎回報。
- 每位 AI 要等自己這一輪想完才會發言,所以訊息是一則一則跳出來,不是逐字顯示。
- 三位同時開會,三家訂閱的額度會同時消耗。
- **Windows 上用 Claude 桌面版**:在桌面版裡面安裝的程式會被放進它自己的隔離資料夾,你自己開的 PowerShell 看不到。請在你自己的終端機安裝這些命令列程式。
- **PowerShell 顯示「已停用指令碼執行」**:把 `npm` 改打成 `npm.cmd`。

## 授權

MIT
