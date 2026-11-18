# 管理者與受試者入口

2026-11-18 使用者明確指定：網站管理者帳號就是 DocterCloud 研究管理者帳號；首頁的日誌 QR Code 則由受試者使用研究配發帳密自行取得。

## 管理者登入

首頁與原生研究頁都使用同一個 `nsysu-staff-auth/login`。密碼只送到既有正式研究者 API `https://icare.docter.pro/back-end/app/login/researcher`，不再用另一組 Supabase 密碼驗證。僅對應既有三個已授權研究管理身分，不能藉任意 DocterCloud 帳號新增網站管理者。

上游成功後，後端用 Supabase Admin generate_link 與 verify 交換內部 Auth session，不寄信、不建立新研究管理身分，也不改既有研究資料權限。資料 API 沿用個人 JWT、`auth.sessions` 與既有 RLS。

DocterCloud access token 使用 AES-GCM 加密，綁定內部 user/session UUID，保存在私有 `nsysu_staff.sessions`；瀏覽器不收到該 token。研究頁經驗證後由雲端取回解密 token，免除第二個登入表單，重新整理／內部 JWT 續期亦可接續。管理者主動登出會撤銷內部 session 並透過外鍵清除該平台快取。

角色使用 `raw_app_meta_data` 與既有 `diary_username` 對應，不信任 user_metadata。新 schema 的設定表僅供資料庫 owner 管理，API／瀏覽器有明確拒絕 policy；token 表只有 backend SELECT，寫入經 backend-only definer 核對目前 session。限流採持久化每帳號五次／十五分鐘及全域上限。密碼不存入資料庫、網址或紀錄。

部署 migration：`20261118022540_unified_docter_staff_auth.sql`、`20261118023311_complete_staff_auth_activation.sql`。遷移先保留既有登入；首次真實 DocterCloud 驗證成功並保存加密 token 後，原子啟用 `require_docter`，資料庫便拒絕沒有 DocterCloud 證明的舊 session。回復使用 [rollback SQL](rollback_unified_docter_staff_auth.sql)，並回復相容的網站／函式版本；既有 auth 身分與研究資料保留。

Edge Function 的 `NSYSU_STAFF_TOKEN_KEY` 僅存雲端 Secrets 與忽略 Git 的私有備份；內建 Service Role 只用於該雲端函式，不放進 Streamlit 公開設定或前端。

管理者是否需要重新登入也取決於 DocterCloud 回傳的有效期限與實際 API 授權狀態；不把內部 JWT 一小時期限當作 DocterCloud 的期限。

## 受試者取得自己的 QR Code

首頁「產生日誌 QR Code」開啟受試者表單，核對私有研究名冊中已登錄且有效的 `ycc00000001`～`ycc00000050`。採已核准的 PBKDF2 雜湊，不在 Git 存密碼或產生規則；此處是研究帳號核對，沒有宣稱完成未實作的 Docter+ 官方受試者登入 API。

`nsysu-line/diary-access` 每次只回傳登入帳號對應的固定填寫 URL。沿用原 Vault capability，不輪換 QR、不要求 LINE 已綁定、不授予管理者／歷史查詢權限，也不改變 LINE 綁定或提醒。完成當日填寫不阻止重新取得自己的固定 QR；連結不綁死單一日期。

私有 snapshot 核對研究有效期、封存與邀請撤銷；錯誤密碼及停用帳號無法取得連結。每帳號五次／十五分鐘；瀏覽器 CORS 僅開放本網站。關閉視窗會清除密碼、URL、QR 與過期非同步回應。

## 驗證與邊界

238 Python、79 JavaScript／隔離 PostgreSQL 測試、Deno check、build／lint／Ruff／mypy 通過。375／414／768／1024／1440px 五種寬度的真實瀏覽器 UI 測試使用合成回應，核對 QR、帳號對應、無管理者登入及無水平溢位。

雲端內嵌腳本在所有功能模組載入後才啟動，實際 inline document 的瀏覽器回歸已核對官方 LINE 區塊可見，避免同步設定回應造成初始化競態。登入交接也涵蓋 Streamlit 三層 iframe 包裝，仍核對 origin、已開啟視窗子樹與 nonce。

既有雲端已實測健康檢查、未知管理者拒絕／無登入 token 拒絕、CORS，以及本人研究帳號取得固定日誌 capability；未建立臨床日誌。實際 DocterCloud 成功登入須由使用者輸入自己的既有管理者密碼驗收，不能用 mock 取代上游成功證據。

Security Advisors 沒有新增警告；保留既有 [Auth leaked-password protection 警告](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection)，未自行升級方案。沒有新增付費專案／分支或付費主機。
