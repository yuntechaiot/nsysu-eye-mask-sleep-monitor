# nsysu-eye-mask-sleep-monitor · 深睡體驗營

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

GitHub Actions 每 4 小時用 Playwright 開啟原版與 Apple 版的公開首頁，必要時按下 Streamlit 喚醒按鈕，確認原生應用執行完成並維持有效連線，另記錄首頁是否顯示。排程不登入或提交表單，也不修改原有網頁功能。使用方式、手動執行與限制見 [定時訪問說明](docs/STREAMLIT_BROWSER_VISIT.md)。
