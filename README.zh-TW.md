# AI 會議室

**讓 Claude、GPT、Gemini 跟你在同一間會議室討論。** 每位 AI 各自發言,你在瀏覽器即時看到整個討論,隨時可以插話。不用你手動傳話;除了各家 AI 自己連回自家伺服器,資料不會離開你的電腦。

[English](README.md)

- **用你已經有的訂閱**:Claude 走 Claude Code(你的 Claude 帳號)、GPT 走 OpenAI Codex(你的 ChatGPT 帳號)、Gemini 走 Antigravity 命令列程式(你的 Google 帳號)。不需要 API 金鑰。
- **自動偵測**電腦裡裝了、登入了哪幾位。你按「邀請」才入席,開會中隨時可以再邀請或請某位離席。
- **你是主持人**:AI 先回應你的插話;你每則發言下方標示誰已回應;AI 不會自己結束會議;你沒發言時 AI 連講 8 則就自動暫停等你;按 ✕ 否決只標記那一版不要,AI 會等你看完其他版本、說要怎麼改才動手;你明確要求修改時才立刻改版。
- **像聊天軟體一樣好用**:在任何一則訊息上按右鍵可以回覆它、一鍵 ✕ 否決或 ✓ 採用;Enter 送出、Shift+Enter 換行。
- **樣板直接貼在對話裡**:AI 可以把單一網頁檔跟著發言一起貼上,直接嵌在對話裡,動畫、按鈕、拖曳都能操作,不用另外開網址。
- **同一個專案、同一套背景**:選一個資料夾,每位 AI 發言前都先讀同樣的專案說明檔(CLAUDE.md、AGENTS.md、GEMINI.md、README)。
- **主審與輔助**:可以指定一位 AI 當主審,所有改程式和 git 提交都由它做,而且**只在專案外的 git 獨立副本裡做**;其他 AI 負責檢查、做主審指派的唯讀工作。
- **每位 AI 可以各自選模型和思考深度**,會議中也能換,而且會記住你上次的選擇。
- **可以同時開好幾場會議**,每場一個瀏覽器分頁;舊會議可以從清單刪除。
- **自動修復**:AI 意外離席會被自動請回;除非是你請它離席;用量用完的會自動退席(訊息會寫恢復時間),不會一直重試,額度恢復後要它回來請按「邀請」;有些模型每答完一則就結束自己的回合、不會留下來等下一則,這種正常結束會安靜地再請回來、不算意外離席,所以換成任何模型都能留在會議裡;會議室重啟後,進行中的會議會自動把 AI 請回來。
- **散會時逐字稿自動存進你的專案**(`docs/meetings/<日期>_<標題>/transcript.md`)。
- **只留採用的附件**:按過 ✓ 的樣板與圖片,加上最後一則沒被否決的,才會存進專案;其他(包括按 ✕ 否決的版本)不存、逐字稿標「未保留」,資料夾不會越來越大。
- **有結論就清理**:「開會」技能會讓 Claude 在會議有結論散會後,先把成品真正用到的東西(原圖、程式、定稿設定圖)搬進專案並確認能重做,再把這場會議的 `rooms/<id>`、`seats/<id>`(試做圖、試做影片、AI 日誌)移到資源回收筒,匯出資料夾裡被取代的檔案也刪掉。
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

Antigravity 命令列程式在背景執行時沒辦法跳出詢問,要先在它的設定裡允許會議室工具。在「邀請」(或「開新會議」)視窗的 Gemini 欄位按「允許會議室工具」,它只會在 `~/.gemini/antigravity-cli/settings.json` 加兩條規則:`mcp(meeting/*)`(會議室工具)和 `read_url(*)`(讓它能打開你貼的網址),其他都不動。Antigravity 的模型名稱多半已帶強度(例如 `gemini-3.8-flash-high`),選這類模型時會議室不再另外傳強度設定,以免兩者衝突、Gemini 啟動就失敗。三位 AI 都能讀網頁:Claude 直接打開網頁;Gemini 用 `read_url` 打開;GPT 用 Codex 的網頁搜尋,讀到的是搜尋引擎存的版本,可能比網頁現況舊。

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
| 平等討論(預設) | 大家都不能改專案、不能做 git 寫入;每位 AI 可以在自己的試做資料夾跑程式、寫檔(產圖、試做),成果附在發言上 |
| 主審 | 改檔和提交**只在 git 獨立副本裡做**(新分支 `meeting/<時間>`,放在專案外,只有受 git 管理的檔案,沒有 `.env` 等未納管的機密檔)。主審可以在副本裡跑程式、腳本、測試、算圖。Codex 由它自己的沙盒限制寫入範圍;Claude 和 `agy` 在原生 Windows 上沒有寫入隔離,推送、連遠端主機、刪檔、部署、發佈是靠規則和提示擋(不是作業系統強制)。推送、部署、刪檔、動到正式環境一律要先在會議室問你。**會議中可以隨時用席位上的「指派操作」按鈕指定或換人**,第一次指派時才建立副本。有人在操作時,會議室每 20 秒比對一次原專案的 git 狀態,只要原專案有檔案被新增或修改,就在會議裡跳 ⚠️ 警告 |
| 自主會議 | 按上方「自主會議」,AI 不用等你回覆、不受連講則數限制(只留防失控上限 `auto_run_limit`),自己分工、一直做到你給的目標完成。只有兩種情況會停:目標全部完成,或卡在只有你能決定、又沒有合理預設可以先做的事;這時由一位發開頭為「【階段成果】」的訊息(做了什麼、產出檔案、要你決定的事),自主會議自動關閉、大家等你回來看。中途進度用「【小結】」報告、不會停;AI 每次等訊息都會再被提醒這條規則。隨時再按一次可停止(會先跳確認)。AI 每次等訊息都會被告知目前上限和還能講幾則,會議中途開關自主會議會立刻生效。席位在思考、出圖時顯示「工作中」和已經忙了幾分鐘 |
| 輔助 | 跟平等討論一樣:不能改專案、只能寫自己的試做資料夾,加上做主審指派的工作 |

Claude 席位只讀專案共用的設定(`--setting-sources project`),你個人平常允許過的指令不會讓席位的權限變大。樣板是放在發言裡的網頁內容;嵌進對話的網頁在隔離框裡執行,動不了會議室(可以載入會議裡的附件,附件帶有 `Access-Control-Allow-Origin: *`,canvas 能讀像素)。原生 Windows 上「只寫自己的試做資料夾」是靠規則和提示約束、不是作業系統強制,所以每場會議期間,會議室都會每 20 秒比對一次原專案的 git 狀態,有變動就跳警告。主審的分支要不要合併回來,由你決定。伺服器只聽本機 `127.0.0.1`,也會擋掉其他網頁發來的寫入。AI 的執行紀錄(含它們讀過的檔案內容)只留在資料夾,不會寫進你的專案。

**不過 AI 還是可能出錯。** 開會時請看著,合併主審的改動前先看過差異,也不要把含有機密、你不願讓 AI 廠商看到的資料夾交給它們。

## 設定

可以設環境變數,或在 `hub.py` 旁邊放一個 `config.json`(不會進 git),例如
`{"lang": "zh-TW", "host_name": "站長"}`。可用的鍵:`host_name`、`lang`、`port`、`project`、`home`、`export_dir`、`ai_run_limit`、`auto_run_limit`、`allowed_origins`、`image_max_mb`、`media_max_mb`。兩者都有時以環境變數為準。

附件:圖片和網頁檔上限 `image_max_mb`(預設 32 MB),影片和音樂(mp4、webm、mov、mp3、m4a、wav)上限 `media_max_mb`(預設 1024 MB)。主持人可以按 📎、把檔案拖進發言欄,或直接貼上;影片在網頁裡直接播放、可以拖進度條。散會時影音檔留在會議室自己的資料夾,不會複製進你的專案。AI 看得到你貼的附件:每則訊息會附上檔案路徑,圖片它們直接打開看;影片則由會議室平均抽 12 張關鍵畫面(要裝 ffmpeg)加上影片長度給它們看。

`allowed_origins`(環境變數 `MEETING_ALLOWED_ORIGINS`,逗號分隔)列出可以送出操作的額外網頁來源,例如透過通道用手機進會議室時填 `["https://你的通道網址"]`。螢幕窄時網頁會換成手機版:☰ 打開會議列表、⋯ 顯示席位細節、按鈕與主題,圖片捲到附近才載入。電腦上以 100% 大小就能一頁看完整個會議室:席位放不下會自動換行、不用左右滑動;左側會議列表更新時不會閃。只能用在需要登入的通道後面:打得開這個網頁的人就能操作會議。

| 環境變數 | 預設 | 意思 |
|---|---|---|
| `MEETING_PORT` | `7720` | 連接埠 |
| `MEETING_LANG` | `en` | 預設會議語言(`en`、`zh-TW`) |
| `MEETING_PROJECT` | 目前資料夾 | 預設專案 |
| `MEETING_HOME` | `%LOCALAPPDATA%\ai-meeting-room`/`~/.local/share/ai-meeting-room` | 進行中的會議、AI 執行紀錄、主審副本 |
| `MEETING_EXPORT_DIR` | `docs/meetings` | 逐字稿存放位置(相對於專案) |
| `MEETING_AI_RUN_LIMIT` | `8` | 你沒發言時 AI 最多連講幾則 |
| `MEETING_AUTO_RUN_LIMIT` | `120` | 開啟**自主會議**時的防失控上限 |
| `MEETING_HOST_NAME` | `主持人` | 中文會議裡 AI 怎麼稱呼你 |
| `CLAUDE_BIN`、`CODEX_BIN`、`AGY_BIN` | 自動 | 三個命令列程式的路徑 |

## 目前狀態與已知限制

- 在 **Windows 11** 開發與測試(Claude Code 2.1、Codex 命令列 0.159、Antigravity 命令列 Gemini 3.8 Flash)。macOS/Linux 的路徑已寫好但還沒實測,歡迎回報。
- 每位 AI 要等自己這一輪想完才會發言,所以訊息是一則一則跳出來,不是逐字顯示。
- 網頁每 1.5 秒查一次新訊息;上一次還沒查完就跳過、不重疊,已經顯示過的訊息不會再畫一次(舊版在 AI 忙的時候可能同一則顯示兩次)。
- 三位同時開會,三家訂閱的額度會同時消耗。每個席位旁會顯示用量:GPT 和 Claude 顯示 5 小時與每週額度用了幾 %(整個帳號,讀命令列自己的紀錄),滑鼠移上去看恢復時間;Gemini 顯示這場會議用掉多少 token(Google 不提供剩餘額度)。AI 因為額度用完而離席時,會議裡會寫明並附恢復時間,不再一直重試。
- **Windows 上用 Claude 桌面版**:在桌面版裡面安裝的程式會被放進它自己的隔離資料夾,你自己開的 PowerShell 看不到。請在你自己的終端機安裝這些命令列程式。
- **Windows 上的微軟商店版 Python**:商店版在隔離環境裡執行,它叫起來的 AI 會一啟動就結束(錯誤訊息「Broken pipe」),寫的檔案也會被轉存到私人資料夾。`start_bg.ps1` 現在會在有其他 Python 3.9 以上時跳過它;也可以設 `MEETING_PYTHON` 自己指定。
- **PowerShell 顯示「已停用指令碼執行」**:把 `npm` 改打成 `npm.cmd`。

## 授權

MIT
