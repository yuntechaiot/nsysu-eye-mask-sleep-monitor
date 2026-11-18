# LINE 全程操作與既有雲端串接

2026-11-18 現況：使用者已自行推送 07344b5，既有 Streamlit 研究綁定頁已實際顯示。LINE Webhook 已改至 Supabase 並通過 LINE 官方 API Verify（200）；已啟用本人 allowlist 與雲端 Cron。使用者親自回報綁定成功，資料庫確認 ycc00000050 於台灣 11/18 10:14 綁定，首次提醒為 **2026/11/19 上午 09:00**。該日期日誌尚未完成，固定填寫 capability 有效。

尚未以真實排程驗證 11/19 的提醒送達及提交後停發，不能把設定成功或合成測試宣稱成已送達。先前 11/18 的手機提醒／提交測試屬隔離本機版本，未匯入雲端正式資料。

## 執行架構

- 官方 LINE @823bciot 的開始綁定／重新綁定／取消綁定選單。
- Webhook：https://ztsyxnrnemvcladbaaem.supabase.co/functions/v1/nsysu-line/webhook，簽章核對、事件去重、即時 durable outbox。
- 既有 Streamlit ?view=line 採 LINE 官方 Account Linking；帳密核對後回 LINE 最後確認，只有成功 callback 才保存綁定與宣告成功。
- 私有 nsysu_line schema、12 張 RLS 表與受限 NOLOGIN backend role；瀏覽器無 schema/table 權限，backend 不能直接讀 Vault 或日誌表。
- Cron 每分鐘檢查台灣 09／11／13／15／17／19／21 時段，十分鐘 grace，不跨日補發。21:00 是目前最後時段的預設值。
- 只有相同受試者／研究範圍／醒來日期的正式保存才算完成；開表單及草稿不算，每天重新判斷。
- 取消綁定須本人兩步確認與十分鐘一次性 proof，確認後停止後續工作、保留日誌與歷史，才可改綁其他帳號。

設定為 enabled=true、allow_all=false，allowlist 僅本人；nsysu-line-cloud-minute active。沒有開放其他好友試發。Cron 採兩分鐘一次性票證，資料庫只存 SHA-256、原子消耗並拒絕重放，排程命令無長效秘密。

本機真實 LINE 的 Windows 工作仍 Disabled、demo_send_enabled=false、64670／64672 停止。使用者手動開啟的 64660／64661 僅為隔離網頁驗收，不是真實 LINE 的執行依賴；關閉電腦不影響雲端 Webhook 與 Cron。

## 資料與修正

沿用既有 Sleep Log System（東京）、50 位受試者及固定日誌邀請，不新增研究期限、不輪換 QR、不匯入本機綁定時間或假日誌。首次提醒按真正成功的台灣日期加一天計算。

首次真實操作發現 postgres.js JSONB 參數被重複序列化，事件收到卻未送出。已改用原生 JSON 寫入、正規化讀值並修復受影響事件，保留原事件與去重識別。該操作被 LINE API 接受一次，之後本人在手機完成綁定。測試 adapter 已涵蓋原生序列化差異。

已套用三份 cloud_line migration（20261117184146／20261117184622／20261117185710）；管理者 session 修正由使用者正式套用。單一登入另已套用 20261118022540_unified_docter_staff_auth.sql、20261118023311_complete_staff_auth_activation.sql。舊 Python reader migration 未採用，不能執行 db push --include-all 擅自補套。

首頁本人 QR 經研究配發帳密核對，只回傳該帳號既有固定 URL；不要求 LINE 已綁定、不授予管理權限、不改提醒。管理者使用 DocterCloud 唯一密碼來源，平台 token 加密保留於私有雲端。見 [登入與 QR 設計](UNIFIED_LOGIN_AND_PERSONAL_QR.md)。

## 驗證與限制

238 Python、79 JavaScript／隔離 PostgreSQL、Deno check、build／lint／Ruff／mypy 通過；375／414／768／1024／1440px QR UI 檢查通過。另以實際雲端 inline document 驗證啟動順序，並涵蓋多層 iframe 登入交接。雲端 API 已驗證本人固定 QR、CORS、未知管理者及無 token 拒絕。真正 DocterCloud 成功登入仍須使用者輸入自己的研究管理者帳密驗收，不能用 mock 代替。

Secrets 僅存雲端與忽略 Git 的私有備份。組織 Free，未建立付費主機、專案、分支或升級方案。啟用前 LINE 月額度確認為 200、已用18；50 人每天一則、30 天即 1,500 則，擴大前須另確認容量與授權。此例不是新增研究期間，本次仍限本人。
