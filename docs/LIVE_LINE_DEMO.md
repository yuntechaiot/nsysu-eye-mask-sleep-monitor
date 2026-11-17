# 本機真實 LINE Demo

## 使用者禁止本機後端；本次服務已停用（2026-11-18）

最新要求：不在使用者電腦架設後端，且希望完全使用 LINE 端服務。已依要求匯出本機工作的 XML 及私有設定備份，停用 `NSYSU_Local_LINE_Demo_Worker`，將私有 `demo_send_enabled=false`，停止本次 64660／64661／64670／64672 的服務及只轉送 64670 的 cloudflared。核對四個本次 Demo port 均無 listener；沒有停止其他工作、修改原版程式、刪除帳密／綁定／日誌或改動正式資料庫。這些本機驗收網址目前無法使用，不能再當成已啟動服務交付。

正式執行範圍尚待釐清：LINE 官方內建提供圖文選單、固定／關鍵字回覆及群發；官方 Messaging API 與 Account Linking 架構要求開發者提供 bot server／服務登入頁。研究帳密核對、個別成員的日誌完成判斷與條件式排程，需要另外的程式與資料儲存，不能僅上傳到 LINE 官方帳號即執行。已提供「保留完整功能、改外部雲端且使用者全程操作 LINE」或「只用 LINE 官方內建、接受功能縮減」兩個範圍供使用者確認；在答覆前不自動部署外部服務、不重啟本機後端、不推送 GitHub。

官方依據：https://developers.line.biz/en/docs/messaging-api/building-bot/ 、https://developers.line.biz/en/docs/messaging-api/linking-accounts/ 、https://tw.linebiz.com/manual/line-official-account/oa-manager-autoreply/ 。

## 視窗與關機限制（2026-11-18）

發現本機每分鐘工作原本以互動登入者的 `python.exe` 啟動，可能閃出命令列視窗。已先匯出 XML 備份，再只更新 `NSYSU_Local_LINE_Demo_Worker` 的 action 為同一環境的 `pythonw.exe`、Settings.Hidden=true；觸發間隔、執行引數、工作目錄、其他工作與正式提醒設定不變。安裝腳本同步使用 windowless interpreter，缺少時明確中止。獨立 smoke check 以 Win32 GetConsoleWindow 驗證無 console，排程執行結果以 Task Scheduler 讀回為準。

目前仍是本機服務：webhook／LIFF endpoint 指向轉送本機 64670 的暫時 HTTPS，日誌、綁定及提醒資料在本機 SQLite，每分鐘 worker 在本機且以 Interactive 使用者執行。電腦關機／休眠／斷網時，本次開發的綁定、取消綁定、日誌提交、即時回覆與提醒不能持續服務；官方聊天室和平台保存的選單仍可顯示。已綁定資料保留在磁碟，不等於關機仍執行。現有工作不是完整的開機自啟動方案，重開後還需啟動 gateway／HTTPS tunnel。

要讓此電腦關機仍可運作，必須另行部署持續運作的後端、公開 HTTPS、持久儲存與獨立排程，並完成正式資料來源設定。GitHub push 只保存程式，不會自動提供常駐 webhook 或提醒服務。目前未部署、未推送，正式提醒旗標保持關閉。管理者驗收登入只適用 64660 的合成資料站，帳密存於受控私有檔，不能當作正式站／DocterCloud／LINE 管理登入。

## 本人收訊、提交與當日停發已驗證（2026-11-18）

依使用者指示將本機測試時鐘設為 `2026-11-18T09:00:00+08:00`，手動執行真實提醒檢查。`ycc00000050` 的 09:00 日誌提醒由 LINE API accepted、attempts=1；使用者親自回報「已收到，正在填寫」，並確認所詢問的是這一則的時間，不是重複收到。09:00 為模擬測試時間，手動檢查是在真實現在發送，不代表等待實際時鐘抵達 09:00。

隨後後端確認原日誌表單正式提交並保存 `member=ycc00000050,date=2026-11-18`，相同日期 snapshot completed=true。接著分別把 Demo 時鐘推進到 11:00、13:00，各執行一次真實檢查：沒有新的日誌發送，原 09:00 工作仍為唯一一筆、accepted、attempts=1。因此本人的真實收訊→填寫→提交→同日停發路徑已驗證；這是隔離資料庫與單一收件人測試，不是正式研究資料庫驗收。

目前 Demo 時鐘停在 `2026-11-18T13:00:00+08:00`。沒有推進到隔日，沒有清除使用者提交或繞過同時段去重，也沒有推送 GitHub。精簡證據在本機 `artifacts/live-line-demo/real-receipt-submit-stop-20261118.json`；不含 LINE User ID、憑證或日誌答案。

## 即時選單回覆與大字版（2026-11-18）

使用者回報取消確認要等待、選單文字太小，並要求點擊後立即出現。已移除正常聊天操作對每分鐘排程的依賴：驗簽、去重及綁定交易 commit 後，立即喚起背景 sender，只發送這次新事件的持久 outbox key。Webhook 不等待外部 HTTP，不觸發日誌排程；仍使用原本的獨立 claim、attempt／lease、固定 retry key 與最後檢查。重送事件不會再次喚起同一訊息，API 失敗／程序中止時才由既有 worker 接續。即時發送同樣受本機停止開關與本人 allowlist 限制。

三個選項主字級由 82 改為 176，移除小字說明，390px 寬預覽可完整顯示三個名稱。新版 PNG 與 per-user 掛載均已從 LINE API 讀回核對，預設選單不變。本機 gateway 已重啟；目前資料顯示本人已取消原綁定，可再從「開始綁定」測新帳號。沒有替使用者執行取消，沒有改動測試時鐘或正式資料。

驗證：Python 218 passed（新增四個測試，含不跑 tick 即開始發送、慢 HTTP 不阻擋 webhook、commit 後才通知、簽章／停止開關、重送去重與持久失敗接續），Ruff／mypy 通過。實際手機收到所需時間尚待使用者點擊驗收，不能用 API 或合成測試宣稱手機延遲數字。先前瀏覽器 11 組與 JS 27 的結果保留；本輪未變更一般網站 UI。GitHub 尚未推送。

## 聊天室選單與更換帳號（2026-11-18）

已將三格圖文選單「開始綁定／重新綁定／取消綁定」掛到已授權的本人 LINE。Messaging API validate、圖片上傳、指定使用者 link 及讀回核對成功；未更動全體好友預設選單。原選單設定存於私有 checkpoint，可回復。手機的實際顯示仍由使用者驗收，不以 API 成功代替實機畫面。

Demo 操作：重開官方聊天室，展開「研究帳號選單」。若要更換，點「取消綁定」，收到目前帳號與確認按鈕後點「確認取消」，再由回覆的「開始綁定」輸入新研究帳密。只點「取消綁定」而未確認，或選「保留綁定」，都保留舊綁定。直接重綁同帳號保留首次時間；取消後的新綁定按新的台灣成功日期計算次日 09:00。

取消是已驗簽的本人私人 postback，需十分鐘內的一次性確認碼。過期、他人、重送、已保留及舊綁定確認不會取消目前新綁定；仍不可覆蓋另一個 LINE 的帳號。確認後同一交易保存取消歷史、移除目前綁定並取消舊日誌待發／重試工作；已填日誌保留。已交給 LINE 的訊息不保證撤回。正常回覆現已改為即時背景發送，原每分鐘 worker 只負責日誌與失敗接續，沒有新增排程。

本機兩份私有 DB 均備份後升級 schema 3，原綁定、時間與 outbox 完整保留；本機服務及 worker 恢復。測試時鐘未推進，仍為 2026-11-17 23:59。Python 214、JavaScript 27、瀏覽器 11 組通過，Ruff／mypy 通過；取消及換帳號測試使用隔離資料，不由代理替使用者取消目前真實綁定。原工作目錄 256 個檔案 SHA-256 無變動；未推送 GitHub或套用正式資料庫。

## 帳號更正（2026-11-18）

使用者確認研究帳號應為 `ycc00000001`～`ycc00000050`。後端驗證、私有 50 筆名冊、本機控制頁與合成預覽的帳號前綴已同步更正，舊 `yc` 前綴不再接受。密碼依使用者確認內容在受控私有檔中準備，Git 中只保留接收明確映射／雜湊的通用更新工具，不保存可還原的憑證規則或帳密清單。

更新前已以 SQLite backup API 備份兩份隔離資料庫；通用工具 `tools/replace_demo_roster.py` 在同一交易中更新 account fingerprint、password hash 及既有 binding foreign key，保留 member／study、首次綁定時間、提醒起日、日誌及既有 capability。也已清除本次測試者先前錯誤輸入累積的 Demo 嘗試限制，未清除正式資料或綁定。

已逐筆核對 50 筆新憑證、舊 alias 剩餘 0、foreign-key error 0；`01`／`50` 通過，`00`／`51`／舊前綴拒絕。Python 206 passed、JavaScript 27 passed、瀏覽器 11 組及 19 張截圖、build／lint／Ruff／mypy 通過。新增回歸驗證帳號更新後仍保留原綁定日期，以及遇到衝突時整批回滾。瀏覽器回歸另發現管理者登入交接成功後，1.5 秒備援計時器仍回傳資料而造成多餘更新；已限定仍在等待的同一個 nonce 才可使用備援，並驗證成功回應不會重複、逾時後的舊回應及錯誤來源均不接受。

服務已重新啟動；發出一則專供本人的「帳號格式已修正／重新綁定」邀請，LINE API 回傳 accepted。其後後端已透過真實 LINE ID token 驗證並確認本人帳號 `ycc00000050` 綁定成功、active=1。測試時鐘仍停在 `2026-11-17T23:59:00+08:00`，因此首次綁定時間也是此值、提醒起日為 2026-11-18；尚未推進至 09:00，不能宣稱日誌提醒已送達或完整實機驗收已完成。同帳號重開綁定不會重設首次綁定時間。更新前本機 Demo 排程呈停用，已備份其設定並恢復原本每分鐘檢查；正式提醒旗標與其他排程不變。

本輪在既有獨立 worktree 追加真實 LINE 測試接線，不推送 GitHub、不部署正式網站、不變更 `LINE_PUSH_ENABLED=false`、不連正式研究資料。

## 已備妥

- 本機公開 gateway：`http://127.0.0.1:64670`，只提供 LINE 綁定、簽章 Webhook 與已綁定本人 capability 日誌。它沒有管理者、測試身分或憑證查詢 endpoint。
- 本機控制工具：`http://127.0.0.1:64672/`，獨立 listener，絕不作為 tunnel upstream。
- 臨時 HTTPS 入口保存在 `private/live-demo/config.json`，由既有 cloudflared 提供，只轉送 64670。停止 tunnel 後入口失效；不等於正式部署。
- 50 筆隔離研究帳號雜湊與測試用日誌映射存於 `private/live-demo/state.sqlite3`，與正式資料及先前合成預覽分開。帳號核對仍是私有研究名冊，不冒充 Docter+ 官方驗證。
- 同一個 `ReminderService`／`LineAPI` 處理後端驗證、Webhook 去重、唯一綁定、outbox、日期、完成與 retry key。新增 allowlist 同時限制 LINE ID token、Webhook 及實際發送收件人。
- 真實訊息加上「本機 Demo」標示；專用綁定頁與日誌顯示資料是隔離測試資料。控制時鐘可跳到翌日 09:00／11:00，手機訊息仍走真正 LINE API。
- `tools/install_live_demo_task.ps1` 已註冊每分鐘獨立 worker，僅執行本機單一收件人 Demo；私有的 `demo_send_enabled=true` 已在使用者明確確認本人後開放。

## 帳號更正前的 LINE 接線紀錄

使用者已登入 LINE Business ID，並明確授權只使用目前登入的本人 LINE。已從可見管理頁核對：Messaging Channel 2012646112、Login Channel 2012645713 同屬 provider 2005816193，兩個 Channel 的本人 User ID 一致。Secret 只保存於私有設定，未輸出到對話或 Git。

既有「睡眠日誌本機測試」LIFF 2012645713-1czR9eZe 的 scope 已為 openid，不增加新權限；Endpoint 已更新為目前測試 tunnel 的 `/line`。原設定已備份。官方帳號 Greeting messages 與 Auto-reply messages 均為 Disabled，沒有更動它們。

Webhook 已設為目前 tunnel 的 `/api/line/webhook`；LINE Console Verify 實際回報 Success，簽章由本機服務驗證。Use webhook 及 Webhook redelivery 已啟用，只把事件交給有本人 allowlist 的測試 gateway。LINE API 讀回確認 endpoint 相符且 active=true。

`recipient_confirmed=true`、`demo_send_enabled=true` 僅限本機 Demo；正式 `.env` 的 `LINE_PUSH_ENABLED=false` 未變更。Windows 工作 `NSYSU_Local_LINE_Demo_Worker` 已註冊每分鐘執行，最近執行結果 0。此刻尚未收到使用者的聊天事件，因此沒有宣稱真實綁定或收訊完成。

手機下一步：用同一個 LINE 帳號加入 @823bciot，傳送「開始綁定」；約一分鐘內收到【本機 Demo】邀請，點入後用 `http://127.0.0.1:64672/` 展開的研究測試帳密完成綁定。不要在手機輸入 127.0.0.1；手機只點官方訊息的 HTTPS／LIFF 連結。成功後再由控制工具跳到翌日 09:00 驗證真實提醒。

## 帳號更正前的驗證紀錄

- 完整 Python：197 passed，含 10 個新增 gateway／收件人限制／真實 transport 測試替身／提交後停止情境。
- JavaScript：24 passed；隔離 PostgreSQL：59 passed。
- build、lint、Ruff、mypy 通過。一般驗收的瀏覽器回歸另外重新執行，結果以 `artifacts/acceptance/browser-results.json` 為準。
- 實際 HTTPS 路由檢查：`/health`、`/line` 為 200；`/access`、`/state`、`/acceptance/access`、`/api/participants` 為 404，證明未將本機控制或管理資料暴露到 tunnel。ProxyFix 明確只信任 HTTPS scheme，不信任 forwarded client／host，相關測試通過。
- 真實 LINE 訊息：截至接線完成為 0。真實手機 LIFF／綁定／收訊：等待使用者在手機傳送指令並操作；不能以 Console Verify 或合成測試代替此項證據。結果在 `artifacts/live-line-demo/verification.json`。

## 啟動與下一步

```
python tools/live_line_demo.py
python tools/live_line_demo.py --worker
```

第一個命令啟動兩個隔離 listener。第二個命令需要所有私有設定與明確的 Demo 發送開關，缺一就失敗關閉。不要將 tunnel 指向 64660 或 64672。

接線、本人限制及本人帳號綁定已確認，下一步是使用者的提醒收訊與提交後停發驗收。Demo 結束時可停用本機工作的執行，並將私有 `demo_send_enabled` 設回 false；原 LINE 設定保留於 `private/live-demo/console-before-demo.json` 與 `webhook-before-demo.json`。正式提醒開關維持關閉。只有本機 Demo 與使用者驗收完成後，才處理 GitHub 推送。
