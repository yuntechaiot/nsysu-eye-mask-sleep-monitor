# nsysu-eye-mask-sleep-monitor · 深睡體驗營

## 雲端 LINE 與帳號入口（2026-11-18）

最新架構使用既有 Supabase 與 Streamlit 雲端：受試者從 LINE 選單綁定、隔日 09:00 開始收到個人日誌連結，未填每兩小時提醒，正式提交後停止當日提醒。真實 LINE 本機後端與 Windows Demo 工作已停用，正式運作不依賴使用者電腦；使用者另行手動啟動的隔離網頁驗收只模擬 LINE。

LINE 已接通既有 Supabase 雲端，僅開放本人收件人；使用者已在手機完成雲端綁定，首次提醒為台灣 2026/11/19 09:00。本版另依使用者要求統一 DocterCloud 管理者登入、移除重複連線表單、提供首頁本人 QR Code 登入，並補上官方 LINE 入口。238 個 Python、79 個 JavaScript／隔離 PostgreSQL 測試、五種寬度 QR UI、build／lint／型別檢查通過。真正 DocterCloud 上游成功登入及首次排程送達仍須各自驗收；詳見 [雲端實作文件](docs/CLOUD_LINE_IMPLEMENTATION.md) 與 [登入／本人 QR Code](docs/UNIFIED_LOGIN_AND_PERSONAL_QR.md)。

## 隔離本機網頁驗收

本輪從 GitHub `origin/main` 的 `7e2deb8897a29e3cdd677b19ba41b88dbe704022` 建立獨立 worktree，完整保留原工作目錄。使用者已手動開啟隔離本機驗收工具，可查看測試登入資料、模擬 follow、設定台灣時鐘與執行提醒，不發送真實 LINE；此工具不是雲端版的執行依賴。

管理者以已授權的 DocterCloud 帳密登入一次後，工作區提供「產生受試者日誌 QR Code」與「查看研究資料」，直接接續同一次平台授權。一般頁面只保留真實官方 LINE ID 與加入連結。技術設定在 [LINE 設定文件](docs/LINE_SETUP.md)，驗收與限制見 [本輪交付報告](docs/ACCEPTANCE_REPORT.md)，審查與修正見 [EGM 審查報告](docs/goldfish_review_report.md)，進度見 [PROGRESS](docs/PROGRESS.md)。


獨立的 Apple 風格、手機優先版本。原始專案 `../NSYSU` 與原網站 https://eye-mask-sleep-monitor.streamlit.app/ 不受此版本部署影響。

- Repository: https://github.com/yuntechaiot/nsysu-eye-mask-sleep-monitor
- Streamlit: https://nsysu-eye-mask-sleep-monitor.streamlit.app/
- Branch: `main` · 入口: `streamlit_app.py` · Python: `3.12`

## 功能

保留原專案的四步驟睡眠日誌、送出前確認、台灣日期與 24 小時時間、三態問項、授權歷史查詢與編輯／刪除、受試者搜尋／新增／改名／移除／還原、固定 QR／邀請連結、CSV 匯出。Dashboard 保留日誌與 DocterCloud 登入、18 類平台資料、原始紀錄、HRV、睡眠分析、圖表模式、JSON 匯出、研究資料管理與匯入／同步。

沿用原有資料來源、授權與研究公式；此版本部署不會執行資料庫 migration。兩個網站連接同一研究資料來源，使用者實際儲存或管理資料時會反映在共用資料中。

## 設計

系統字體、灰白表面、藍色主要操作、寬鬆的卡片與清楚的文字層次。手機上表單單欄、日期與時間上下排列、評分按鈕至少 48px，導覽允許換行。浮動導覽與表單操作區使用霧面材質。

`apple-motion.js` 使用 requestAnimationFrame 與解析解的臨界阻尼 Spring（response 0.32s、damping 1）。按下、拖離、返回與釋放時重新設定目標，保留目前位置／速度，不攔截 click 或延遲送出。鍵盤操作同樣有回饋，並支援減少動態、減少透明度及高對比偏好。Dashboard 原生元件保留原互動行為。

## 本機啟動

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

依 `.streamlit/secrets.toml.example` 設定本機 Secrets 或環境變數。不要提交實際金鑰、帳密、匯出或研究資料。

## 驗證

```powershell
python -m pytest -q
npm ci --ignore-scripts
npm run build
npm run lint
npm test
python tools/verify_cloud.py
python tools/verify_apple_ui.py
```

測試設定使用 CI workflow 中的合成公開金鑰。瀏覽器回歸攔截資料庫請求，所有測試寫入只存在記憶體，不使用真實研究資料。

詳見 [設計分析](docs/APPLE_DESIGN.md) 與 [獨立部署設定](GITHUB_STREAMLIT_SETUP.md)。

## 定時開啟網站

GitHub Actions 每 2 小時用 Playwright 開啟原版與 Apple 版的公開首頁，必要時按下 Streamlit 喚醒按鈕，確認原生應用執行完成並維持有效連線，另記錄首頁是否顯示。排程不登入或提交表單，也不修改原有網頁功能。使用方式、手動執行與限制見 [定時訪問說明](docs/STREAMLIT_BROWSER_VISIT.md)。
