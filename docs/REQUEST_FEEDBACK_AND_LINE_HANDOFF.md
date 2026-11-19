# 網頁請求提示與 LINE 同分頁確認

2026/11/19。此提交僅包含請求提示、LINE 綁定確認頁及相關測試；首頁入口與研究資料介面改版仍留在本機，未包含在本次發布範圍。

## 更新行為

- 網頁請求開始時，在操作控制項附近顯示「正在處理，請稍候…」。超過 8 秒顯示連線較慢提示；最後一個並行請求結束後才解除，不自動重送請求。
- LINE 核對帳密前即顯示等待訊息；成功或失敗後解除。重新核對時，舊的確認按鈕會由等待狀態取代。
- 「回 LINE 完成綁定」改為在目前分頁開啟官方 HTTPS 確認網址，減少另開分頁及瀏覽器切換。網址仍嚴格核對官方主機、路徑、本次 linkToken 及 nonce，不改用其他驗證機制。
- 只有既有 LINE 官方成功 callback 才會完成綁定。本次未更動研究憑證、研究資料、綁定規則、提醒起日、排程或停發條件，也不需要重新部署 Supabase LINE 函式。

## 驗證範圍

本機曾以 Chrome 1440×900 與 390×844 檢查等待、同分頁開啟本機示範、重新核對時隱藏舊按鈕，以及模擬慢速／503 後保留表單並解除等待。使用隔離資料與 transport，沒有發送真實 LINE、建立真實綁定或寫入研究紀錄。

**Android／iOS 的實際 LINE App 尚待手機驗收。** 本機導頁成功不代表正式 Account Linking 已通過。網站更新後，請從官方聊天室重新取得「開始綁定」連結，以同一手機 LINE 帳號完成帳密核對及最後確認，再確認聊天室回報綁定成功。

## 隔離導頁示範

推送前從 origin/main 的獨立工作目錄驗證：246 項 Python、96 項 JavaScript 測試通過；隔離資料庫測試、Ruff、mypy（30 個來源檔）、build、前端語法與 git diff --check 亦通過。HTML 除加入狀態節點與 script 外，與原版本一致；Streamlit 嵌入入口只增加同一份提示 script。

```powershell
python -m streamlit run tools/preview_line_handoff.py --server.address 127.0.0.1 --server.port 64713 --server.headless true --browser.gatherUsageStats false
```

這個工具重用正式綁定頁程式，但封鎖外部 requests；兩個欄位留空即可模擬核對，確認按鈕只開啟本機示範收據。請勿輸入真實帳密；127.0.0.1 只供執行工具的電腦使用。

主要實作：`frontend/web/request-status.js`、`backend/nsysu/cloud_line_page.py`。既有 HTML 及 Streamlit 嵌入頁只加入提示所需的資產與狀態節點；沒有套用未驗收的首頁版面。

官方行為依據：[Streamlit link button 會另開分頁](https://docs.streamlit.io/develop/api-reference/widgets/st.link_button)、[LINE Account Linking](https://developers.line.biz/en/docs/messaging-api/linking-accounts/)。
