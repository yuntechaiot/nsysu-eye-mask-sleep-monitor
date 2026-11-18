# LINE 全程操作與既有雲端串接

目前狀態：雲端後端已部署為停用待驗收，網站綁定頁尚未發布，LINE Webhook 尚未切換。不能宣稱已可從手機完成雲端綁定。225 個 Python、55 個 JavaScript／隔離 PostgreSQL 測試、Deno check、build／lint／Ruff／mypy 通過。雲端部署未使用本機 server；其後使用者另行要求本機頁面驗收，已由使用者手動開啟隔離驗收服務，返回首頁／重新整理／續期／登出的四項瀏覽器檢查通過。

2026-11-18 使用者明確確認：受試者全程在 LINE 操作，後台可沿用既有 Supabase；不使用使用者電腦。保留首次綁定台灣次日 09:00、未填每兩小時提醒、提交成功停止當日提醒。原本機真實 LINE 後端與 Windows 工作保持停用。

## 目標架構

- LINE 圖文選單：開始綁定、重新綁定、取消綁定；已驗簽的操作立即回覆。
- Supabase 專用 Edge Function：Webhook、研究帳號核對、官方 Account Linking 回傳事件、訊息發送與失敗接續。
- 既有雲端網站：專用研究帳號表單。採官方 Account Linking，登入核對後回 LINE 完成；不把帳密輸入到聊天室，也不把帳密放網址。
- Supabase 私有 schema：研究帳號雜湊、唯一綁定、一次性確認、事件去重及 durable outbox。瀏覽器角色不能讀取。
- Supabase Cron：每分鐘檢查台灣時段與既有日誌正式提交紀錄；09／11／13／15／17／19／21 預設時段、十分鐘 grace、不跨日補發。
- 日誌與固定 capability：沿用既有睡眠日誌、提交 RPC 與 Vault 邀請，不複製本機測試日誌進正式資料，也不輪換既有 QR。

## 執行限制

已確認既有 Sleep Log System（東京）正常，50 位受試者及其固定日誌 capability 均存在。已新增專用 Edge Function、12 張私有 RLS 表、最小權限 NOLOGIN backend role、50 筆 PBKDF2 註冊資料及專用 Cron。研究 scope 使用既有日誌專案識別碼，不虛構新的研究期限；本機假日誌及人為綁定時間未匯入正式資料。

已套用 migration：`20261117184146_cloud_line_gateway.sql`、`20261117184622_cloud_line_scheduler.sql`、`20261117185710_cloud_line_net_schema.sql`。檔案名稱已依實際雲端 migration history 對齊，沒有混入尚未套用的舊 session／Python reader migration。不要執行 `db push --include-all` 擅自補套其他 migration。

雲端函式：`https://ztsyxnrnemvcladbaaem.supabase.co/functions/v1/nsysu-line`。`/health` 是 process liveness；實際 DB 連線另用一次性票證呼叫停用狀態的 `/tick`，回傳 200、jobs=[]，同票證重放為 401。Webhook 原始 bytes HMAC 煙霧測試 200、processed=0；未驗簽請求為 401。這些是受控 API 驗證，並非宣稱 LINE Console Verify 或手機收訊已完成。

`config.enabled=false`、`allow_all=false`、allowlist 僅原先本人；Cron `nsysu-line-cloud-minute` 為 inactive，每分鐘規則已建立。pg_net 呼叫雲端公開健康端點實測 200、沒有逾時或錯誤，證明資料庫到 Edge 的雲端網路可用。Cloud binding 為 0，必須於正式雲端入口重新綁定，才能依真正的成功日期計算首次提醒。本機真實 LINE 的 Windows 工作保持 Disabled、64670／64672 停止；使用者另行手動啟動的 64660／64661 僅提供隔離網頁驗收。

Edge Function Secrets 已安全設定，沒有寫進 Git。Cron 採兩分鐘一次性票證：資料庫只存 SHA-256，排程命令不含長效秘密，只有資料庫排程可以建立票證，函式原子消耗且拒絕重放。`pg_net` 新安裝位置已修正到 extensions；安全 Advisors 僅保留既有 Auth leaked-password protection 警告，未自行變更 Auth 方案或密碼政策。12 張表皆啟用 RLS，瀏覽器不能讀私有 schema，backend role 也不能直接讀 Vault 或日誌表，只能透過範圍受控的 snapshot。

目前 LINE 月額度 200，已使用 18（2026-11-18 讀回）。50 人每天一則，30 天即 1,500 則；若全部未填、每日七時段，30 天上限為 10,500 則，尚未含互動訊息。這是計費容量示例，不是新增研究期間。此輪不升級方案，不對其他受試者試發。Supabase 組織目前 Free，未建立付費主機／分支或升級方案。

初次雲端驗收仍限原先明確授權的本人收件人，不能向正式 50 位受試者試發。後續擴大使用必須以使用者確認的範圍執行。程式不輸出研究密碼、LINE token、完整 nonce 或 diary capability。

既有網站的雲端發布須更新 GitHub 程式；原使用者要求仍保留：未取得推送同意前不 push。完成程式與隔離測試後，提供實際變動／部署步驟，再處理必要的推送確認。新付費資源或方案升級不得自行建立。

## 驗證

準備 Node 與隔離 PostgreSQL 行為測試：綁定邊界／密碼、LINE 簽章、官方 nonce 同身分且一次有效、綁定唯一性、兩步取消、首次隔日、正式提交與目標日期、同時段去重、逾時／重試／重啟及停用限制。真正雲端發布後另核對 Webhook、本人收訊與不依賴本機的操作，不能以本機測試或排程設定代替已送達證據。

## 發布後續

先更新既有雲端網站，使 `?view=line` 提供研究帳密表單；核對後顯示 LINE 官方確認按鈕，只有 accountLink 事件提交成功才在聊天室宣告成功。這次採官方 Account Linking，不使用本機 LIFF 網址，也不要求研究密碼輸入聊天室。網站只需要公開的 Function URL 與官方 LINE ID，不能放 Channel Secret／Access Token。

程式推送／網站發布仍受使用者最初的明確限制。已讀回正式管理者 session helper，目前尚未核對 `auth.sessions`；若發布整份管理者登入更新，須個別審查／套用 `active_staff_session` migration，才能讓資料庫一併拒絕已撤銷的 session，不能用 `db push --include-all` 一次帶入舊 reader 方案。取得本次雲端驗收發布同意後，核對線上綁定頁、將 Webhook 切至 `/webhook` 並做 LINE Console Verify，再僅開放本人與啟用專用 Cron；最後執行手機綁定與提醒驗收。未取得同意前不 push、不切 Webhook、不開放全體。
