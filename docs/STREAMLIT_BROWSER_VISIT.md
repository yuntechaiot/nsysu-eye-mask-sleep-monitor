# Streamlit 免費定時訪問

GitHub Actions 工作流程：`.github/workflows/streamlit-browser-visit.yml`。
排程在公開儲存庫 `yuntechaiot/nsysu-eye-mask-sleep-monitor` 執行，使用 GitHub 提供的 Ubuntu runner，電腦不必保持開機。不新增付費服務、不需要網站帳密或 Supabase 金鑰。

## 訪問範圍

`tools/streamlit_sites.json` 明確列出兩個公開首頁：

- 原版：<https://eye-mask-sleep-monitor.streamlit.app/>
- Apple 版：<https://nsysu-eye-mask-sleep-monitor.streamlit.app/>

Apple 版已改名，因此不使用舊的 `nsysu-apple-design.streamlit.app` 網址。
若只要照顧其中一個網站，從 JSON 清單移除另一筆即可。

## 排程與行為

每 4 小時執行一次。預定台灣時間為每日 00:17、04:17、08:17、12:17、16:17、20:17，實際執行時間可能延遲。

1. 安裝獨立的 Playwright 依賴與 Chromium，不安裝或啟動專案後端。
2. 用本機合成頁面驗證喚醒、iframe、WebSocket 與失敗判定。
3. 以全新、未登入的瀏覽器工作階段開啟每個公開首頁。
4. 若看到 Streamlit 的「Yes, get this app back up!」，按下喚醒。
5. 等待日誌首頁 `#home-page` 可見，同時確認同一主機的 Streamlit WebSocket 已收到資料。
6. 保持連線 15 秒，確認仍可使用後結束。每個網站最多嘗試 2 次，每次等待上限 150 秒。
7. 任一網站失敗，整個工作流程會標示失敗。Actions 摘要與 JSON 報告列出各站結果，報告保留 7 天。

只允許 HTTPS 的 `*.streamlit.app` 根網址，不允許帶帳密、查詢參數、邀請 token 或管理路徑。唯一自動點擊的按鈕是託管平台的喚醒按鈕；不登入、不點選表單、不提交日誌、不開啟研究資料。原版專案、前端、後端 API、資料庫結構與計算邏輯都不修改。

## 手動執行與停用

開啟儲存庫的 **Actions → Streamlit browser visit**：

- **Run workflow**：立即執行一次，分支選 `main`。
- **Disable workflow**：停止之後的排程。
- 點進執行紀錄，可看摘要、日誌與 `streamlit-browser-visit-report` 附件。

本機測試：

```powershell
python -m pip install -r tools/requirements-keepalive.txt
python -m playwright install chromium
python tools/test_streamlit_browser_visit.py
python tools/streamlit_browser_visit.py
```

## 限制

此排程用來減少休眠機會，不是永不休眠或服務持續可用的保證。官方目前的閒置門檻為 12 小時；平台仍可因維護、資源限制或政策調整停止應用。

GitHub Actions 的排程可能延遲或在高負載時丟棄工作。公開儲存庫連續 60 天沒有活動時，排程也可能自動停用；請在 Actions 頁確認狀態並重新啟用。不使用自動空白 commit 或寫入儲存庫的方式維持活動。

- [Streamlit 休眠規則](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app#app-hibernation)
- [GitHub Actions 排程限制](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [GitHub Actions 計費說明](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
