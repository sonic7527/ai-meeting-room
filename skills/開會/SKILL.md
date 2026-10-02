---
name: 開會
description: 開一場「使用者＋Claude／GPT／Gemini」AI 會議(電腦裡裝了哪些就請哪些):自動在背景啟動本機 AI 會議室、用目前所在的專案開新會議、在 Chrome 開出這場會議的新分頁。可同時開多場(每場一個分頁)。用戶說「開會 / 三方會議 / 找 GPT、Gemini 一起討論 / 開會議室 / 叫 AI 們討論 / 讓其他 AI 檢查程式」時使用。
---

# 開會(AI 會議室)

一下指令就要做完三件事:會議室在跑、會議建好、Chrome 新分頁打開。不要問用戶確認細節,從他的話整理;他沒說的用預設值。

## 1. 找會議室程式

依序找第一個有 `hub.py` 的資料夾:`$AI_MEETING_ROOM_DIR`、`~/ai-meeting-room`。

## 2. 確保會議室在背景執行

- Windows:`powershell -ExecutionPolicy Bypass -File "<資料夾>/start_bg.ps1"`
- macOS / Linux:`bash "<資料夾>/start_bg.sh"`

輸出「already running」或「started」就好;關掉對話也會繼續跑。

## 3. 寫會議設定檔(用 Write 工具、UTF-8,存在暫存資料夾)

```json
{"title": "20 字內標題",
 "topic": "背景、用戶已經定下的限制(原話)、要討論出什麼",
 "project": "<目前工作資料夾的 git 根目錄;不是 git 專案就用目前資料夾>",
 "lang": "zh-TW",
 "mode": "discuss",
 "lead": ""}
```

- `project`:**就是目前所在的專案資料夾**(`git rev-parse --show-toplevel`),用戶明說別的專案才換。
- `lang`:跟用戶的語言一致(`zh-TW` 或 `en`)。
- `mode`:`discuss`(討論,預設);用戶要檢查程式用 `review`。
- `lead`:`""` 平等討論(大家都只能看,預設);用戶指定誰主審才填。主審在專案外的 git 獨立副本改程式,推送與部署要先問用戶。
- `seats`:**預設不填**,會議室先是空的,由用戶在網頁按「邀請」選人;只有用戶在指令裡明說要請誰(例如「找 GPT 跟 Gemini 開會」)才填那幾位。
- `seat_cfg`:**用戶指定模型才填**,否則省略(會議室會沿用用戶上次選的模型)。

## 4. 建立會議並開 Chrome 新分頁

`python "<資料夾>/open_meeting.py" "<會議設定檔>"`(依電腦用 `py` 或 `python3`;設 `PYTHONIOENCODING=utf-8`)。
輸出一行 JSON:會議 id、網址、各位 AI 入席結果。

## 5. 回報用戶(繁體中文、短)

會議標題、專案、網址;一句提醒:「按上方『邀請』請 AI 入席;在訊息上按右鍵可回覆、否決;要結束按散會。」有 AI 入席失敗就照實說原因。開會期間不要逐則轉述,散會後再一次回報。

## 6. 在背景等散會

用 Bash `run_in_background: true` 跑:
```
until curl -s "http://127.0.0.1:7720/api/rooms/<urlencode 過的 id>/messages?after=99999" | grep -q '"export"'; do sleep 15; done; echo 散會
```
收到通知後讀 `<專案>/docs/meetings/<日期>_<標題>/transcript.md`,**先把結果攤給用戶**(各方重點、共識、分歧、要用戶決定的事),對其他 AI 的意見逐條表達你的看法;結論由用戶下。

散會匯出時已經只留採用的附件(按過 ✓ 的,加上最後一則沒被否決的)。用戶拍板、工作做完(上線、合併或部署)後再清一次:那個資料夾裡用戶沒採用的檔案、過程中自己做的暫用預覽頁和截圖全部刪掉;提交時只放逐字稿、發言紀錄和採用的檔案。
