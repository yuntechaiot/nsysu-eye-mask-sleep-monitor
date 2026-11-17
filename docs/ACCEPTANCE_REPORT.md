# 本輪交付與驗收（2026-11-17）

## 可操作入口與 Git 基準

- 已啟動並確認可開啟：[隔離驗收工具](http://127.0.0.1:64660/acceptance)、[實際網站](http://127.0.0.1:64660/)、[專用綁定頁](http://127.0.0.1:64660/line)。研究資料服務在 `http://127.0.0.1:64661/`；請由網站的「查看研究資料」進入，以驗證登入交接。
- Repository：`https://github.com/yuntechaiot/nsysu-eye-mask-sleep-monitor.git`。已 fetch 並核對遠端預設分支 `origin/main`，沒有其他發布分支約定。
- GitHub 基準完整 SHA：`7e2deb8897a29e3cdd677b19ba41b88dbe704022`，commit 為 `Visit both Streamlit apps every two hours`。不是以本機未提交改版當作基準。
- 本輪本地分支：`codex/line-diary-acceptance-20261117`。
- 本輪 worktree：`C:\Users\User\Desktop\yuntech\HRV_Smart_EyeMask\NSYSU_line_acceptance`。
- 原工作目錄：`C:\Users\User\Desktop\yuntech\HRV_Smart_EyeMask\NSYSU_apple_design`，原分支 `main` 追蹤 `origin/main`；開始時 87 項未提交／未追蹤變動，沒有額外未推送 commit。原檔保留；本輪內容只在新 worktree。
- 沒有 push、PR、正式部署、正式 migration、正式提醒開關變更。原版／Apple 版兩小時喚醒 workflow 保持原樣。

若需重啟，在本輪 worktree 的 PowerShell 執行：

```powershell
..\NSYSU_apple_design\.venv\Scripts\python.exe tools/preview_acceptance.py
```

此命令同時啟動本機 Flask 與 Streamlit，預設連接埠為 64660／64661；不會停止其他既有 listener。一般新環境先建立 venv，安裝 `requirements-lock.txt` 與測試／開發相依套件。以 `--directory private/acceptance-new` 可建立另一份全新的隔離測試資料，保留原驗收紀錄。

## 管理者、QR、研究資料驗收

1. 在驗收工具展開「查看本機測試登入資料」。這些是隨機建立、僅本機有效的合成帳密，也存於忽略 Git 的 `private/acceptance/access.json`。
2. 點「開啟實際網站」→「研究人員／管理者登入」。畫面應為「管理者登入」、欄位「管理者帳號」「管理者密碼」、按鈕「登入管理工作區」。
3. 登入後有「產生受試者日誌 QR Code」與「查看研究資料」兩個主要任務，不出現第二份管理登入。
4. 選 QR 任務，選擇合成受試者，核對「睡眠日誌填寫入口」、對象、QR 與可複製連結。兩位邊界代表樣本的連結不同；重新整理、返回工作區再進入，仍保留對象。QR 只授予既有新增日誌用途，不是 LINE 綁定 QR，也不授予歷史讀取權限。
5. 回工作區點「查看研究資料」。新分頁應直接顯示「管理者已登入」，選擇承接自 QR 的受試者，按「查看資料」可使用原本八個研究頁籤與合成量測資料。HRV／睡眠計算沿用原模組。
6. 「重新連接 DocterCloud」是另外的平台資料授權，不重用管理者帳密。隔離驗收明確停用它的外部連線；輸入合成資料只會顯示失敗，不會假裝官方成功。
7. 可在驗收工具「撤銷測試管理者 Session」，重新開 QR 頁；應要求管理者登入一次，成功後返回原受試者 QR。從研究頁登出也會清除網站 session、姓名、歷史、匯出與 QR 快取。

一般網站只顯示已透過只讀 LINE bot-info API 確認的官方 ID **@823bciot**、加入連結與一句說明。沒有綁定狀態、清單／數量、User ID、好友狀態、提醒時間表、開關、發送紀錄、LIFF／Webhook 技術面板。

## LINE 與快速時鐘驗收

1. 驗收工具維持初始台灣時鐘 `2026-11-17 23:59`，點「模擬加入官方 LINE」，再點「執行一次提醒工作」。只會產生合成歡迎邀請，不會產生當日日誌提醒。
2. 點處理結果中的「開始綁定」。這是同一套正式 `/line` 頁，只是身分提供者明確替換為測試 adapter。輸入驗收工具顯示的研究帳密。
3. 後端驗證及寫入完成後，畫面顯示「綁定成功」及 `2026/11/18 上午09:00` 的首次提醒。沒有「Docter+ 官方驗證成功」等未經證實的宣稱。
4. 將時鐘設為 `2026-11-18 09:00`，點「設定測試時間」與「執行一次提醒工作」。應只有一個該成員／日期／時段的日誌工作。重按不重複發送。
5. 點「填寫睡眠日誌」但先不送出。將時鐘改 `11:00` 再執行，會有第二個時段提醒。開表單不算完成。
6. 若要直接驗證 **10:30 提交 → 11:00 停止**，在 09:00 工作後將時鐘設 10:30，從訊息連結完成原有四步驟，最後按「確認送出日誌」；11:00 再執行，當天不新增工作。若已驗證 11:00 的第二次提醒，可在 11:30 提交，再檢查 13:00 停止。
7. 將時鐘設成 `2026-11-19 09:00` 再執行，會針對新的醒來日期產生工作，不追發昨天所有漏填。
8. 模擬封鎖後，後續時段停止；恢復 follow 不重置首次綁定時間及起日。「模擬傳送開始綁定」讓已加好友者重取入口。技術狀態只在此本機驗收工具及私有資料庫，沒有加入一般網站。

隔離範例使用兩位合成邊界樣本，沒有載入正式 50 位受試者資料；正式程式支援私有名冊中有效的全部帳號。測試密碼與正式研究憑證無關。所有模擬呼叫均標記 simulated，正式 factory 不會在缺設定時自動套用這些 adapter。

## 本輪實際結果

| 類別 | 實際執行結果 | 範圍／證據 |
|---|---|---|
| Python 合成／既有回歸 | **187 passed** | `artifacts/pytest-final.log`；既有日誌、HRV、睡眠分析、平台解析及新綁定／提醒情境 |
| JavaScript | **24 passed** | `artifacts/node-final.log`；含登出時仍在下載的匯出競態 |
| 隔離 PostgreSQL | **59 passed** | `test-results/postgres.json`；RLS、寫入 capability、撤銷 session、私有 snapshot、migration 套用／回復 |
| 瀏覽器 | **11 組檢查通過** | Edge 真實 Flask／Streamlit／四步驟表單；`artifacts/acceptance/browser-results.json` |
| 建置／lint／型別 | 通過 | `npm run build`、`npm run lint`、Ruff、mypy（24 個後端模組） |
| 真實 LINE | **只讀 bot-info HTTP 200；訊息發送 0** | 已確認真實官方 ID／既有測試 Token 可讀；未完成真實 follow、LIFF 身分與推播端到端 |
| 實機／LINE 內瀏覽器 | **未執行** | 已測桌面瀏覽器的 320／390／430／1440px；不能當作手機實機結果 |

這些數字來自本輪指令，不沿用先前工作區的測試結果。關鍵新增回歸包含：發送前時鐘跨越延遲窗口、後續成員出錯不回滾先前接受結果、程序崩潰仍計入三次上限、午夜歡迎邀請、逾時後接到 5xx 仍保留不確定結果。

## 十八項需求的證據對照

| # | 情境 | 已執行的證據 |
|---|---|---|
| 1 | 管理者只登入一次 | 瀏覽器 cross-origin handoff、QR／研究八頁籤 |
| 2 | 管理者名稱與欄位 | 瀏覽器 label 斷言、登入截圖 |
| 3 | 一般網站 LINE 資訊範圍 | 瀏覽器禁止技術／狀態面板文字斷言、人工畫面檢查 |
| 4 | 不同受試者 QR／保留選擇 | 瀏覽器不同 capability、重新整理及鍵盤選擇 |
| 5 | follow 邀請與重送去重 | 簽章／event ID 單元測試與瀏覽器合成 follow |
| 6 | 字串前導零、邊界、未登錄拒絕 | `test_account_string_boundaries` 及帳密／未登錄測試 |
| 7 | 本地核對宣稱一致 | API verification 值、綁定頁文案、正式模式不回退測試 |
| 8 | 成功／重送／衝突／到期／取消 | idempotent、409、invalid token、LIFF 取消提示 |
| 9 | 23:59 次日 09:00 首次提醒 | 控制時鐘測試與成功畫面 |
| 10 | 七個時段各一個工作 | 全天 clock sweep、重跑與唯一鍵測試 |
| 11 | 點開不算；提交後停止 | 實際四步驟提交後停止、10:30 提交單元測試 |
| 12 | 其他日期不算本次完成 | exact-date／其他成員單元測試與私有 SQL predicate |
| 13 | 隔日新目標／不追發 | 單元與瀏覽器次日時鐘 |
| 14 | 重送／併發／逾時／重啟 | 多 worker、固定 payload/retry key、崩潰／持久 attempt 測試 |
| 15 | 封鎖／停用／研究結束 | 六種停止條件、refollow 不重置起日 |
| 16 | 停機恢復與有界延遲 | 十分鐘 grace、午夜日誌不補發、歡迎邀請例外 |
| 17 | URL／身分越權 | 既有 SQL／JS capability 隔離、LINE 不產生 staff token、RLS／session 撤銷 |
| 18 | 保留原日誌／HRV／分析 | 全部既有 Python／JS／PGlite 回歸與實際研究 renderer |

## 改善前後與截圖

未附老師原始兩張截圖，因此「改善前」是**直接從上述 GitHub 基準 commit 的原程式重新啟動／擷取**，不是聲稱看過未提供的圖片。

| 畫面 | 改善前 | 改善後 |
|---|---|---|
| 一般網站登入 | 日誌帳號與用途混雜 | 管理者標題、管理者欄位、登入管理工作區 |
| 研究頁登入交接 | 再次出現「登入日誌與研究資料」，並重用管理者帳密登入平台 | 既有 session 直接開研究資料，DocterCloud 授權獨立 |

原始對照檔：`artifacts/acceptance/before-home-login-1440.png`、`before-dashboard-login-1440.png`。改善後：`after-admin-login-1440.png`、`after-dashboard-no-second-login-1440.png`。完整自動截圖共 **19 張 PNG**，另有啟動後人工確認的 `live-acceptance-controller.jpg`。

![桌面管理工作區](../artifacts/acceptance/workspace-1440.png)

![320px QR 頁](../artifacts/acceptance/qr-320.png)

![手機綁定結果](../artifacts/acceptance/binding-success-390.png)

## 驗證限制、設定與修改摘要

帳號核對是私有名冊的 `local_research`，不是 Docter+ 官方登入。初始憑證可被推測，第一次綁定者的真人身分無法單靠這個流程證明。沒有擅自增加受試者驗證步驟；雜湊與限流不被描述為解決冒綁。

完整外部缺項及其阻擋步驟見 [LINE_SETUP](LINE_SETUP.md)：目前主要缺 Channel Secret、本輪公開 HTTPS／LIFF 設定確認、核實私有名冊／日誌代碼／研究 enrollment、唯讀 DB、持久 scheduler 及明確授權的真實測試收件人。既有 token／LIFF 檔不代表本輪真實端到端已完成。歡迎訊息去重還需確認 Official Account Manager 的另一份歡迎邀請已關閉。

後端新增綁定、Webhook、私有狀態／outbox、獨立 worker、名冊匯入、隔離 provider；調整 cloud／server／dashboard session 交接及登入用途。前端延用原 HTML／CSS／QR／四步驟日誌，新增簡潔工作區、LINE 加入短訊與專用手機綁定頁。新增兩份 Supabase migration、SQLite schema／明確 v2 升級及回復腳本、systemd 部署範本與驗收工具。沒有改動研究公式模組或原喚醒 workflow。

EGM 審查及逐項修正見 [審查報告](goldfish_review_report.md)。進度、原目錄保留證據及 Git 狀態見 [PROGRESS](PROGRESS.md)。目前請依上述流程驗收；只有使用者明確表示驗收通過／功能完整／確認完成後，才另詢問是否推送。
