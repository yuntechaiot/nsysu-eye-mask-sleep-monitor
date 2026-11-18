# 本輪進度（2026-11-17）

2026-11-18 綁定即測試：依使用者要求，官方成功 callback 後即推送對應帳號的日誌測試卡，卡片顯示帳號、日誌日期、首次正式提醒時間；新綁定仍從台灣隔日 09:00 開始，保留兩小時提醒與填完當日停發。同帳號主動重綁可重測，重放 webhook 不重測；送出前核對綁定世代、帳號與邀請，取消／換帳號／撤銷後不送舊連結。開放既有有效名冊受試者完成帳密與官方確認後自行綁定，沒有向既有好友群發補測試。86 Node／隔離 PG（含 28 雲端 LINE）、Deno check、build／lint 通過；既有 Python 238 與原工作目錄保留。詳見 [雲端狀態](CLOUD_LINE_IMPLEMENTATION.md)。下文為歷次紀錄。

2026-11-18 雲端實測與入口更新：使用者已自行推送 `07344b5`，正式 `active_staff_session` 也已套用。既有雲端 `?view=line` 已實際顯示新表單，LINE Webhook 改至 Supabase 並通過 LINE 官方 API Verify，啟用僅本人 allowlist 與專用 Cron。本機真實 LINE 工作仍 Disabled、`demo_send_enabled=false`。修正 postgres.js 的 JSONB 重複序列化與讀取字串差異，恢復先前真實操作；本人回報收到並完成綁定，雲端核對 `ycc00000050`，真實綁定時間為台灣 11/18 10:14，首次提醒 11/19 09:00，capability 有效且當日尚未提交。未改日期、未匯入本機假日誌、未開放其他好友。

最新新增：DocterCloud 管理者是網站唯一密碼驗證來源，移除第二套連線表單；私有雲端保存加密平台 token，內部 RLS session 沿用既有三名管理者。首頁 QR 改用有效研究帳密直接取得登入帳號對應的固定 QR／連結，沒有管理權限或 LINE 綁定副作用；公開官方 LINE 缺設定時使用已核實的 @823bciot。238 Python、79 Node／隔離 PG、五種寬度 UI、雲端 inline 啟動與三層 iframe 交接、Deno check、build／lint／Ruff／mypy 通過；雲端 API 已實測本人固定日誌入口。上游 DocterCloud 成功仍待使用者用真實管理者帳密驗收。詳見 [登入與 QR 設計](UNIFIED_LOGIN_AND_PERSONAL_QR.md)。下方為歷次驗收紀錄。

2026-11-18 返回首頁登入接續修正：研究頁原使用的 `st.link_button` 開啟無 opener 的新分頁，首頁的分頁儲存空間因此沒有登入資料。已改為專用返回元件及受控 postMessage 交接，核對來源 origin、實際開啟的視窗與一次性 nonce；網址只帶非秘密的 `auth_return=1`，不包含憑證，也不改成永久 localStorage。重新整理後會依非秘密的來源標記重建可信交接連線，讓續期／主動登出持續同步，授權仍由原後端檢查。225 個 Python、55 個 Node／隔離 PG 測試、build／lint／Ruff／mypy 通過。使用者手動重啟後，四項真實 Edge 瀏覽器檢查通過：首頁登入→研究→返回→重新整理；模擬憑證到期後自動續期、研究資料可讀且再次返回取得新憑證；主動登出清除相關頁面；直接登入研究頁後返回首頁。證據在 `artifacts/return-session/checks.json` 與截圖；測試連線僅 localhost，不改日誌、時鐘或正式資料。沒有推送、部署或啟用真實 LINE。本機登入 access token 為一小時；操作時提前 30 秒檢查並續期，未設定閒置或固定最長登入時間。

2026-11-18 雲端版：使用者明確同意「全程 LINE 操作、後台沿用 Supabase、不使用電腦」，並保留每兩小時提醒及填完停發。已完成並部署停用狀態的 Edge Function、12 張 RLS 私有表／受限 backend role、50 筆 PBKDF2 名冊及 inactive Cron；沒有匯入本機假日誌或綁定時間。雲端 HMAC、DB 連線、一次性排程票證與重放拒絕、snapshot 固定 capability 均已驗證。223 Python、45 Node／隔離 PG、Deno check、build／lint／Ruff／mypy 通過。綁定頁程式已完成但尚未發布；依原始指示，未同意前不 push，所以 LINE Webhook 尚未切換、推播與 Cron 均停用，雲端手機完整流程尚待發布後驗收。LINE 現月額度 200／已用18，只保留本人測試範圍；沒有升級付費方案。詳見 [雲端部署狀態](CLOUD_LINE_IMPLEMENTATION.md)。

2026-11-18 已依「不要在我的電腦架設後端」停用本次每分鐘工作及 Demo 發送旗標，停止本次四個服務 port 與 64670 tunnel，資料及程式保留。先前驗收網址現已停止。後續使用者已確認完整功能沿用既有 Supabase 雲端，實作狀態見上段；不重啟本機服務。下文先前成果為本機驗證紀錄，不代表那些服務仍在運作。

2026-11-18 背景視窗修正：本機 LINE 每分鐘排程原用 python.exe／Interactive，已備份 XML，改成同環境 pythonw.exe 並 Hidden=true，保留每分鐘觸發與所有業務規則，安裝腳本同步修正。windowless smoke 證實 GetConsoleWindow=0；沒有手動觸發額外 LINE 推播。已明確說明目前電腦關機後自訂 LINE 功能停止，GitHub push 不等於常駐部署；正式上線未完成。

2026-11-18 本人真實提醒驗收：依使用者指示推進 Demo 時鐘至 09:00，`ycc00000050` 一則提醒 accepted、attempts=1，使用者親自確認收到；其後原日誌表單成功保存 2026-11-18 日誌，snapshot completed=true。11:00、13:00 各執行一次檢查，均無新日誌發送，原提醒保持唯一一筆。本人收訊→提交→當日停發路徑已驗證；時鐘停在 13:00，未測隔日恢復，未推送 GitHub，未連正式研究資料。細節見 [真實 LINE 本機 Demo](LIVE_LINE_DEMO.md)。

2026-11-18 回應速度與可讀性：聊天交易 commit 後立即喚起背景 sender，只處理本次新事件工作，Webhook 不等待 LINE HTTP、也不執行日誌 tick；失敗才交由既有每分鐘 worker 接續。仍保留固定 retry key、durable lease 與去重。三選項字級 82→176、移除小字說明，手機 390px 預覽及 LINE 上傳圖片／本人掛載讀回核對完成；gateway 已重啟。Python 218、Ruff／mypy 通過。手機延遲待使用者實際點擊驗收；目前後端已無本人有效綁定，使用者可再綁新帳號。未推送 GitHub。

2026-11-18 聊天室操作：本人專用三格圖文選單已建立、上傳及掛載，API 讀回相符，全體預設選單不變。新增驗簽 postback／文字指令與兩步取消確認，確認碼同本人、十分鐘、一次性，保留日誌及取消歷史、取消舊待發提醒後可綁新帳號。schema 3 已在兩份本機 DB 備份後升級，原本人 `ycc00000050` 綁定保留，待使用者親自驗收取消／換帳號。Python 214、JS 27、瀏覽器 11 組及 Ruff／mypy 通過；正式資料／旗標及 GitHub 不變。詳見 [Demo 操作](LIVE_LINE_DEMO.md)。

2026-11-18 帳號更正：依使用者確認，LINE Demo 已改為 `ycc00000001`～`ycc00000050`，舊 `yc` 拒絕。私有 50 筆名冊及兩筆合成預覽已備份後更新，保留日誌、capability、研究對應及既有綁定時間；解除本次輸入錯誤造成的 Demo 限流。Python 206、JavaScript 27、瀏覽器 11 組、build／lint／Ruff／mypy 通過。回歸發現的登入交接備援計時器重複回應已修正並加測。服務／本機每分鐘工作恢復，新的本人重綁邀請已交給 LINE（accepted）；後端隨後確認本人 `ycc00000050` 真實綁定成功。測試時鐘仍為 2026-11-17 23:59，提醒起日 2026-11-18，待使用者進行提醒及停發驗收。沒有推送 GitHub，正式資料及提醒旗標未更動。

最新追加：使用者已登入 LINE 管理帳號，明確授權只測試本人。公開 gateway 64670、獨立控制工具 64672、受限 HTTPS tunnel 已啟動；Secret 私下保存，測試 LIFF 已更新、Webhook 驗簽回報 Success、active=true，每分鐘本機 worker 已啟動且僅允許本人。正式提醒旗標仍 false。Python 197 passed；手機聊天事件／綁定／收訊仍待使用者實際操作確認。詳見 [真實 LINE 本機 Demo](LIVE_LINE_DEMO.md)。以下為先前合成驗收完成紀錄。

狀態：本地實作、合成測試、瀏覽器操作與可開啟驗收版本完成；等待使用者驗收。正式 LINE／實機端到端因必要外部設定及測試授權不足而未執行。

- 基準：fetch 後的 `origin/main`，完整 SHA `7e2deb8897a29e3cdd677b19ba41b88dbe704022`。
- 新分支：`codex/line-diary-acceptance-20261117`；worktree：`../NSYSU_line_acceptance`。
- 原 `NSYSU_apple_design` 內容完整保留，未使用 reset／clean。只逐項重用已讀過的 auth bridge，沒有覆蓋整套未推送改版。
- 原版與 Apple 版每兩小時喚醒 workflow 未變更。新提醒由獨立每分鐘 worker 處理，不使用網站喚醒工作當提醒排程。
- 管理者一次登入、QR／研究資料交接、權限撤銷後返回原位置、登出清除私有快取完成。
- LIFF 後端身分驗證、私有研究帳號核對、follow／指令邀請、Webhook 簽章／去重、唯一綁定、限流完成。
- 台灣次日 09:00 首提醒、每日七時段、正式提交後停止、研究期間、封鎖／停用停止、持久狀態、固定 retry key、三次 durable attempt／租約、十分鐘 grace 完成。
- SQLite schema v1＋明確 v2 升級及回復測試、兩份私有／session PostgreSQL migration 與權限／回復測試完成；沒有套用正式資料庫。
- 測試：Python 187、JavaScript 24、隔離 PostgreSQL 59、瀏覽器 11 組通過；build／lint／Ruff／mypy 通過。
- 19 張自動桌面／手機寬度截圖、GitHub 基準改善前對照與實際操作錄存完成。實機驗證未執行。
- 真實 LINE 只讀 bot-info 回應 200，確認官方 ID；真實訊息發送 0。私有 token 沒有複製給驗收服務。
- EGM readiness 及兩次獨立程式審查的有效 findings 均已修正並加入回歸；沒有宣稱完整 interactive loop 收斂。
- 已啟動 `http://127.0.0.1:64660/acceptance`，研究服務 64661；操作見 [驗收報告](ACCEPTANCE_REPORT.md)。
- 尚缺正式設定及具體影響見 [LINE_SETUP](LINE_SETUP.md)。本輪沒有 push、PR 或部署，也沒有變更正式提醒開關。不得將代理測試通過當作使用者已驗收。

最後保留驗證及精確變動清單由本輪 `private/original-manifest.json`（開始時 SHA-256）與 `artifacts/worktree-preservation.json` 記錄。它們只供本機驗收，不包含憑證，也未加入 Git。

最後 SHA-256 保留稽核：原目錄全部受檢檔案內容未變更，原 status 仍為 87 項；喚醒 workflow 的 Git blob 與遠端基準一致。精確受檢檔案數見上述本機 JSON。
