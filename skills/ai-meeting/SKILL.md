---
name: ai-meeting
description: 開會、AI 會議、三方討論、繼續會議或由 Codex 主持時使用。操作使用者既有的 ai-meeting-room，參照 CC 的讀取、等待、具名發言與協調流程；不適用於一般視訊會議。
---

# 由 Codex 主持 AI 會議

使用者已指定：以後說「開會」可由目前 Codex 對話主持，沿用 CC 做法。主持是協調討論；最後決策由使用者拍板。不要把主持誤當成 `lead`（可改程式的主審）。

## 找到正確會議室

程式依序找 `$AI_MEETING_ROOM_DIR`、`~/ai-meeting-room`。新會議預設本機 `http://127.0.0.1:7720`，用 `start_bg.ps1` 背景啟動；不使用 `-Restart`，除非已確認沒有進行中的會議。

遠端位址從使用者當次提供的網址、`MEETING_URL`，或私人設定 `~/.ai-meeting-hosts.json`（以 desktop 等名稱對應 URL）取得。不要把私人主機網址或現行會議 id 放進公開技能。使用者提到桌機、CC 正在主持或繼續既有會議時，先讀正確主機的 `/api/rooms`，核對標題、專案、closed；不要因本機清單空白就另開一場。沒有遠端位址時先找既有本機設定或向使用者確認。

## 開新會議

使用目前專案（git 根目錄，否則 cwd），從對話整理 title、topic、限制與希望產出，lang=zh-TW，mode=discuss（檢查程式時 review），lead=""。沒有可推斷的題目時先問題目。沿用上次模型，不自行換模型與思考深度。

讀 `/api/agents` 確認可用席位；使用者明說邀誰就只邀誰，未指定則沿用既有開會技能的預設：空席開場，在網頁選擇邀請。不要把 installed/signed_in 當成實際入席成功；檢查建立回傳及後續訊息。使用者指定加入某會議或邀 AI 即授權該場會議的發言與邀請；單純查看、查詢或參考做法不授權發言。

用 UTF-8 無 BOM 暫存 JSON，執行 `python -X utf8 <會議室>/open_meeting.py <設定檔>` 建立並開瀏覽器；只支援本機。遠端會議則對選定 base 的 `/api/rooms` POST 同樣設定，再開回傳 id 的網址。邀請使用 POST `/api/rooms/<id>/invite` body `{"seat":"Claude"}`。未經指示不開自主模式、不指派程式修改權。

## 主持循環（CC 做法）

搭配本技能 `scripts/meeting.py`，標準 Python 3，無額外依賴。每次明確指定 `--base`，id 以原始中文參數傳入，工具負責 URL 編碼。

```
python -X utf8 <技能>/scripts/meeting.py --base http://127.0.0.1:7720 rooms
python -X utf8 <技能>/scripts/meeting.py --base <base> read <id> --after 0
python -X utf8 <技能>/scripts/meeting.py --base <base> say <id> --file <UTF8發言檔>
python -X utf8 <技能>/scripts/meeting.py --base <base> watch <id> --after <last_seq> --seconds 45
```

首次分頁讀完整上下文，接著保存 last_seq，只讀增量；保留證據訊息編號。發言明確標成「【Codex主持】」，不冒充站長、CC、後台或其他 AI。新版 API 以 who=Codex主持 區分站長；舊版忽略 who 時正文仍保留身分。不要冒用其他參與者的 who。

整理議程與驗收標準，@具體席位分工；發現分歧要求證據和反例；區分已驗證、推測、待決。@席位是會議內建機制，無需另開 Codex 聊天或建立本工具的子代理。收到成果要檢查證據；誤判需在會議更正並引用原訊息。整理共識、分歧、成果檔和待使用者決定的事。

遠端手機連線時，命令輸出過密可能塞滿桌面程式的待傳送佇列而中斷連線。`read`／`watch` 預設每頁最多 6000 個 UTF-8 位元組，單行輸出；不要把完整逐字稿、長文件或大量日誌一次印到終端，也不要只依賴工具的 `max_output_tokens`，因為截斷前可能已傳送大量輸出事件。診斷時在程序內先篩選、彙總，再輸出少量結果。

分頁回傳 `has_more`、`last_seq`、`next_offset`、`latest_seq`。`last_seq` 只到最後完整讀完的訊息；`latest_seq` 是伺服器最新序號，不可當成已讀游標。只要 `has_more=true`，用上頁的 `last_seq` 與 `next_offset` 接續：

```
python -X utf8 <技能>/scripts/meeting.py --base <base> read <id> --after <last_seq> --offset <next_offset>
```

`text_complete=false` 表示該則長訊息尚未讀完；接續片段與前段組合後才可判讀或派工。每次確認游標有前進；若附件或欄位過大，工具會明確報錯，改用 `snapshot` 保存完整紀錄，再分段讀本機檔案，不可跳到 `latest_seq`。完整快照不要直接輸出到終端。

watch 最多 45 秒返回，等待所有新發言（主持需掌握各席成果）；用 after 游標接續，避免重複轉述或漏掉未點名發言。不要開無限背景監看後就宣稱能自行醒來；目前回合內以有界等待推進，離開回合前如需未來喚醒，須用可用的正式排程工具並核對使用者意圖。不可假稱有永久背景主持。

## 與 CC 交接、接續主持

使用者要求交接、額度不足換主持或接續既有會議時，先讀 [共用主持交接協議](references/host-handoff.md)。以共用 room id 的完整訊息為依據，發布「主持交接」與「接任確認」，保留最後讀取序號、原始使用者指示、唯一負責席位及待驗事項；不得因換主持重跑工作。

私人快照：`python -X utf8 <技能>/scripts/meeting.py --base <base> snapshot <id> --out <私人資料夾>`。先讀快照，再補讀游標後的現場訊息；快照不會自動同步。

## 散會與成果

使用者同意散會後 POST `/api/rooms/<id>/close`。讀取匯出的 transcript.md，向使用者回報各方重點、共識與未決事項。操作原始專案、推送、部署、刪除仍需符合當次授權。

有結論的會議按既有 `~/ai-meeting-room/skills/開會/SKILL.md` 第 7 節：先把實際採用素材、程式保存進正式專案，確認可重做，再把這場淘汰素材與 rooms/seats 移入回收筒，保留逐字稿、紀錄與定稿。未散會或待續的會議不清理。不自動永久刪除。
