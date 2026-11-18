# LINE 與研究帳號設定

**2026-11-18 雲端版更新：** 現在採既有 Supabase Edge Function／Cron 與 Streamlit 原生綁定頁，使用官方 Account Linking；不使用本機 Python 服務、SQLite worker 或 LIFF。雲端已啟用並接通正式網站；有效名冊帳號核對與官方確認成功後，立即收到本人日誌測試連結，正式提醒從台灣隔日 09:00 開始。最新設定與已驗證項目以 [CLOUD_LINE_IMPLEMENTATION](CLOUD_LINE_IMPLEMENTATION.md) 為準。

正式圖文選單現已設定為所有好友共用預設；原本人專屬 Demo 覆蓋已移除。手機退出並重開聊天室後最多約一分鐘更新；LINE 電腦版不顯示此圖文選單。正式部署使用 `tools/cloud_line_menu.py`，單人 `tools/live_line_menu.py` 僅供舊隔離 Demo。API 建立的選單及優先順序可參閱 [LINE 官方說明](https://developers.line.biz/en/docs/messaging-api/rich-menus-overview/)。

因手機仍未顯示的回報，已補強為目前 7 位有效好友直接掛載同一份正式選單；之後已驗簽且符合資格的加入好友／綁定操作也會在背景同步最新全體預設。個人掛載優先於全體預設，設定立即生效；使用者仍可自行收起選單，手機顯示鍵盤時須切回選單列。

下文保留先前本機／自管後端方案的設定與驗證紀錄，不能當成雲端版的缺件清單或啟動指令。本機 Demo 已依使用者要求停止。

一般網站只讀取 `LINE_OFFICIAL_ACCOUNT_ID`，以此產生官方加入連結；未設定時使用已核實的 @823bciot。綁定頁只有 LINE 操作入口，沒有加入一般導覽；管理者工作區也沒有綁定、好友、提醒或技術面板。

## 已確認與尚缺項目

本節為正式部署需求清單。已授權的單一本人本機 Demo 接線、綁定、圖文選單與取消綁定實測狀態，見 [LIVE_LINE_DEMO](LIVE_LINE_DEMO.md)；它不代表正式資料庫或全體好友已開通。

只讀 `GET /v2/bot/info` 回應 HTTP 200，確認既有私有測試 Token 有效，實際官方帳號為 **@823bciot**。未輸出 Token，未發送訊息。舊私有檔有 Login channel、LIFF ID 與公開 origin，但不能據此證明目前公開端點運行本次程式、LIFF `openid` scope 正確或 Webhook 已註冊。

目前缺少／尚待確認：

| 項目 | 阻擋的驗收 |
|---|---|
| `LINE_CHANNEL_SECRET` | 真實 follow／unfollow／指令 Webhook 簽章與重送 |
| 本輪後端的公開 HTTPS Webhook、綁定頁與反向代理 | LINE 到本次後端的端到端連線 |
| 已核實的 Login channel／LIFF `openid` scope、相同 provider | 真實受試者 LINE ID token 核對 |
| 私有帳號名冊及研究帳號 → 日誌代碼的核實對應 | 正式研究帳號核對與受試者對應；使用者已更正帳號為 `ycc…`，與日誌代碼格式一致；正式研究歸屬仍須核對 |
| `LINE_READONLY_DATABASE_URL`、新私有 snapshot migration 與研究 enrollment | 讀取正式完成狀態、既有研究有效期及固定日誌 capability |
| 持久化磁碟、獨立每分鐘 scheduler／worker、正式監控 | 服務重啟後持續提醒與不補發過期工作 |
| Official Account Manager 歡迎訊息狀態 | 上線前須關閉 Manager 另一份綁定邀請，或移除其重複內容；目前沒有證據可確認設定 |
| 本輪明確授權的真實測試收件人與測試環境 | 真實 LINE 推播及手機 LINE 內瀏覽器測試 |

既有測試 Token 不會被複製進隔離驗收服務。舊私有收件人紀錄不會自動被視為本輪可發送的授權。正式提醒開關維持關閉。

## 驗證模式與帳號名冊

目前只有 `RESEARCH_AUTH_MODE=local_research`：後端核對研究預先建立的私有帳號及 salted Werkzeug scrypt／PBKDF2 雜湊。帳號已依 2026-11-18 更正為 `ycc00000001`～`ycc00000050`；保留字串、前導零及精確小寫格式，舊 `yc` 前綴拒絕；格式通過但未登錄仍拒絕。不會自動註冊。

基準 `Platform.login` 是獨立的 DocterCloud 登入路徑。本輪沒有取得可用的、經授權的平台測試帳密，因此沒有取得其實際登入成功回應。沒有 Docter+ API Key 不會被當作驗證成功。若設定其他正式驗證模式，服務會明確失敗，不回退成本地成功。

名冊檔必須放在 Git 忽略的 `private/` 或受控外部路徑。格式為 JSON 陣列，每筆必須有 `account`、`password_hash`、`study`、`member`，可有 `starts`、`ends`（ISO 日期，皆含邊界）。使用者實際的帳密清單不可寫進 Git、網址或文件。請由受控工具使用 `werkzeug.security.generate_password_hash` 準備雜湊；此 repository 的匯入工具只接受雜湊，沒有帳密生成規則。

```
python tools/reminder_worker.py --init-state
python tools/import_research_accounts.py --roster private/approved-roster.json --state private/line-state.sqlite3
```

重複帳號、同一日誌成員對應多個研究／帳號、錯誤日期或未提供雜湊都會中止匯入。私有名冊啟用狀態在 SQLite `accounts.active`；綁定停用在 `bindings.active`。本輪不提供一般網站的管理介面。

**身分限制：** 本研究指定的初始憑證可被推測。雜湊、限流與唯一性可降低外洩／覆蓋風險，但不能證明第一次綁定者就是本人，也不能解決冒綁。依需求沒有額外增加受試者驗證步驟。

## 私有資料庫變更與回復

新 SQLite schema：[line_state.sql](../backend/nsysu/sql/line_state.sql)，回復檔：[rollback_line_state.sql](../backend/nsysu/sql/rollback_line_state.sql)。初始化只透過明確 CLI 執行；正式 factory 不自動建庫或遷移。schema version 為 3（明確初始化時依序套用 line_state.sql、line_state_v2.sql 與 line_state_v3.sql；正式 factory 不自動升級）。v3 增加一次性取消確認與綁定取消歷史。升級前停 web／worker，用 SQLite backup API 備份整庫，再以原 LINE_STATE_PATH 執行 `python tools/reminder_worker.py --init-state`；需回復時停止服務，以備份資料庫及相容版本程式一起恢復，不在運行中的資料庫刪欄位。SQLite 必須是單一主機共用的本機持久磁碟，不能用多主機或網路檔案系統。所有 worker 共用同一絕對路徑。

兩份 Supabase migration 均由本機 CLI `migration new` 建立，只在 PGlite 隔離 PostgreSQL 驗證：

- `20261117095650_active_staff_session.sql`：現有私有 staff helper 同時核對當前 Auth user 與 `auth.sessions`，撤銷後原 JWT 不能再讀研究資料。
- `20261117101218_private_line_snapshot.sql`：新增私有研究 enrollment 與 backend-only snapshot。`anon`／`authenticated` 不能執行，`nsysu_line_reader` 是 NOLOGIN 能力角色，沒有直接讀取日誌、名冊或 Vault 的授權。

正式套用前先備份並在測試環境核對 Auth schema。私有登入角色、密碼與該角色的 `nsysu_line_reader` membership 由受控 DB 管理流程另外建立，設定預設唯讀交易，連線設在 `LINE_READONLY_DATABASE_URL`，不可放瀏覽器。研究 enrollment 必須由管理者確認後，在 `nsysu_private.line_subjects` 寫入核實的 `member_id`、`study_id` 與既有有效期；不存在有效期時留 NULL，不擅自新增期限。SQLite 名冊的 study 必須相符。worker 不會自行建立 enrollment，也不建立／輪換 QR secret；請先透過既有管理者 QR 功能建立固定日誌連結。

回復：先停止 web／worker、備份完整 SQLite 及私有 enrollment；套用 [rollback_private_line_snapshot.sql](rollback_private_line_snapshot.sql) 與 [rollback_active_staff_session.sql](rollback_active_staff_session.sql)，並將程式／state 備份作為同一組恢復。SQLite DROP 腳本會刪資料，只用於隔離驗證或已備份後的明確回復。正式資料庫本輪沒有套用或回復任何 migration。

## Webhook、綁定與提醒

Webhook 對原始 bytes 先驗簽，才解析 JSON；事件識別持久化、整批交易失敗會回滾，回傳非 2xx 供 LINE 重送。重複事件不再新增邀請；不支援事件記錄後略過。好友狀態依事件毫秒排序；相同時間以 unfollow 優先，不允許較舊 follow 覆蓋封鎖。

follow 或文字 `開始綁定`／`綁定`／`bind`，排入歡迎訊息及 LIFF 入口。聊天交易 commit 後立即由背景 sender 發送本次新事件的持久 outbox，不等待每分鐘排程；Webhook 不等待外部推播。背景發送與 worker 共用單筆 claim／attempt／lease／固定 retry key，worker 仍負責網路失敗接續與日誌時段。一般環境只有 `LINE_PUSH_ENABLED=true` 才可即時發送；本機單人 Demo 則檢查自己的私有 `demo_send_enabled`。LIFF 只送 ID token 到後端；後端對 LINE verify endpoint 核對 issuer、audience、expiry、subject。URL 參數、profile、前端 User ID 都不能授權。關閉／取消授權或 token 過期時，回到 LINE 重新取得入口。

聊天室圖文選單提供「開始綁定／重新綁定／取消綁定」。三者透過已驗簽的私人使用者 postback 處理，也接受文字「重新綁定／取消綁定」。開始／重綁只提供 LIFF 入口與目前綁定說明，不自動解除舊帳號。取消先顯示目前帳號及「確認取消／保留綁定」；確認碼為隨機、只存雜湊、限同一 LINE、十分鐘內一次有效。新的確認、保留、封鎖或新綁定會使先前的確認失效；舊確認不能取消後來的新綁定。

確認取消與待發日誌取消在同一交易提交，保留原綁定時間、提醒起日及研究對應於 `binding_history`，不刪日誌或名冊。已發送／已交給 LINE 的訊息不能撤回。取消後原帳號釋放，可輸入另一個已登錄帳號的帳密；他人的綁定仍拒絕覆蓋。新的綁定由新成功日期的台灣次日 09:00 開始（受原研究期間限制）；未取消而同帳號重送／refollow 保持原時間。綁定已由管理者停用時，不可透過取消流程解除限制。

`python tools/live_line_menu.py` 只輸出預覽；`--apply` 只將選單掛到私有設定已確認的單一 Demo 收件人，不設定全體預設選單。執行前保存原 per-user／default 設定，完成後 API 讀回核對；可用 `--restore private/live-demo/backups/menu-....json` 回復該使用者原選單。PNG 使用既有白／藍配色及三格圖文，不包含帳號或憑證。此工具需 requirements-lock.txt 的 Pillow，預設讀 Windows 微軟正黑體。

`POST /api/line/bind` JSON 為 `id_token,account,password`，成功只在寫入交易 commit 後回傳 `status=bound,bound_at,first_reminder_at,verification=local_research`。錯誤為 400 格式、401 身分／帳密、403 停用／研究無有效日、409 綁定衝突、429 限流、503 外部／設定錯誤。相同 LINE／帳號重送回原結果，其他身分不能覆蓋。LINE 綁定不產生管理者 session。

登入嘗試限制使用持久化 15 分鐘窗口：每個直接連線 IP 30 次，每個已驗證 LINE 身分及每個帳號 fingerprint 各 5 次。反向代理不信任任意 `X-Forwarded-For`，部署時由固定可信代理另外配置真實 IP；未配置時可能共用代理 IP 限制，但不允許請求者自行繞過。

首次提醒是首次綁定成功的**台灣日期加一天** 09:00；尚未開始的研究延後至原研究起日。原綁定時間及起日不因重綁／refollow 重設。後端預設時段為 **09、11、13、15、17、19、21 時**。**21:00 是目前未指定晚間截止時間時採用、可調整的預設最後時段**，不是新研究期限。

每個時段只有對應研究＋成員＋台灣醒來日期＋HH:mm 一個業務工作。只有既有日誌 RPC 成功保存的 `sleep_logs`、相同成員與 `date` 且 `date_definition='wake_date'` 視為完成；開啟連結／草稿不算。基準資料沒有研究欄位，因此私有 enrollment 強制一位日誌成員只對應一個研究。其他成員、日期或研究不會停止本次提醒。

發送工作先 commit 不變的 payload／retry key，再 commit 一次 attempt 與 60 秒租約，最後逐筆重新驗證並發送／保存結果。SQLite 寫入鎖只涵蓋單筆最後檢查與有界 HTTP，busy timeout 45 秒、HTTP 10 秒、DB 查詢 10 秒。每筆外部呼叫前重新讀時鐘，不使用整批開始時的舊時間。崩潰後租約到期才重試，相同 payload、相同 `X-Line-Retry-Key`，最多三次；attempt 不因崩潰回滾。

2xx 或有 `x-line-accepted-request-id` 的 409 記為 `accepted`，只表示 LINE 接受 API，**不代表已送達／已讀**。網路逾時記 `uncertain`，5xx 記 `retry` 並保留 uncertainty，30／60 秒指數退避；重試仍是同一工作。第三次仍無法確認則 `uncertain_final`。先前任何未釐清的逾時／5xx／崩潰結果，會由持久 uncertainty 欄位保留，不能被後續失敗覆蓋成確定未送；只有 LINE 接受的確認結果才清除此旗標。429（限流／額度）與其他 4xx 留下失敗代碼，不無限重試。日誌待發工作只有在預定時間後十分鐘內、同一台灣日期可送，過期略過；21:00 工作最晚可在 21:10 重試。已送出而結果未知的過期工作保留 `uncertain_final`。歡迎／綁定邀請沒有目標日誌日期，允許在事件後十分鐘內跨午夜發送，避免 23:59 加好友的邀請消失。

完成、封鎖、停用、研究結束、撤銷 QR 時，發送前最後檢查會取消／略過；已被 LINE 接受的競態訊息不能保證撤回。日誌提交成功但最後一次 snapshot 尚未看到提交的瞬間，仍可能有一則已在發送中的訊息。

## 獨立執行環境

```
pip install -r requirements-lock.txt -r requirements-line.txt
PYTHONPATH=backend waitress-serve --listen=127.0.0.1:8000 --call nsysu.server:create_app
python tools/reminder_worker.py              # dry run
```

反向代理提供公開 HTTPS，同時轉送 `/line`、`/api/line/*` 與日誌頁。不要記錄 query string、Authorization、請求 body 或完整 token；既有固定 QR 是寫入 capability，也要排除於 access log。應用程式的開發／驗收 access logger 已去除 query。

[nsysu-web.service](../deploy/nsysu-web.service)、[nsysu-reminders.service](../deploy/nsysu-reminders.service) 與 [timer](../deploy/nsysu-reminders.timer) 是部署範本，沒有安裝或啟動。timer 每分鐘觸發一次，不補跑停機積欠。`--send` 還需明確 `LINE_PUSH_ENABLED=true` 才可真的推播；本輪不變更此開關。

Streamlit Cloud 本身不承擔此排程；一般頁面開著、Streamlit session 或瀏覽器計時器都不會觸發提醒。原版與 Apple 版兩小時喚醒 workflow 原封保留。

## 本輪核對的官方資料

- [LINE Webhook](https://developers.line.biz/en/docs/messaging-api/receiving-messages/)
- [LINE 指定使用者圖文選單](https://developers.line.biz/en/docs/messaging-api/use-per-user-rich-menus/)
- [Account Linking（已比較，本輪採 LIFF）](https://developers.line.biz/en/docs/messaging-api/linking-accounts/)
- [LIFF 後端身分驗證](https://developers.line.biz/en/docs/liff/using-user-profile/)
- [固定 retry key 與重試狀態](https://developers.line.biz/en/docs/messaging-api/retrying-api-request/)
- [Supabase Sessions](https://supabase.com/docs/guides/auth/sessions)
- [Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security)
