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
2. 合成頁面的喚醒、iframe、WebSocket 與失敗判定由獨立工作流程 `streamlit-browser-tests.yml` 在自動訪問程式變更、PR 或手動觸發時驗證。測試失敗仍會標示紅燈，但不阻擋定時訪問。
3. 在 GitHub Linux runner 的 Xvfb 虛擬桌面內，以全新、未登入的完整 Chromium 開啟每個公開首頁，讓網頁處於前景工作階段。
4. 若看到 Streamlit 的「Yes, get this app back up!」，按下喚醒。
5. 確認同一主機的 Streamlit WebSocket 已收到資料，且原生應用已完成執行（`stApp` 的執行狀態為 `notRunning`）。若託管平台外框停在載入畫面 30 秒，會嘗試直接開啟頁面內實際存在、同主機的公開應用 iframe，再確認工作階段。
6. 保持連線 15 秒，確認應用執行完成且連線仍有效後結束。首頁 `#home-page` 是否可見另列在報告中，不以首頁版型判定防休眠是否成功；此工作流程不是完整的網站功能健康檢查。每個網站最多嘗試 2 次，每次等待上限 150 秒。
7. 任一網站失敗，整個工作流程會標示失敗。Actions 摘要與 JSON 報告列出各站結果，報告保留 7 天。

只允許 HTTPS 的 `*.streamlit.app` 根網址，不允許帶帳密、查詢參數、邀請 token 或管理路徑。唯一自動點擊的按鈕是託管平台的喚醒按鈕；不登入、不點選表單、不提交日誌、不開啟研究資料。原版專案、前端、後端 API、資料庫結構與計算邏輯都不修改。

## 手動執行與停用

開啟儲存庫的 **Actions → Streamlit browser visit**：

- **Run workflow**：立即執行一次，分支選 `main`；每站嘗試次數預設為 2，快速檢查可選 1。
- **Disable workflow**：停止之後的排程。
- 點進執行紀錄，可看摘要、日誌與 `streamlit-browser-visit-report` 附件。

本機測試：

```powershell
python -m pip install -r tools/requirements-keepalive.txt
python -m playwright install chromium
python tools/test_streamlit_browser_visit.py
python tools/streamlit_browser_visit.py
```

## 2026-11-08 執行紀錄檢查

檢查 11 月 5 日至 11 月 8 日（台灣時間）的 12 次自動排程及其實際報告：

- 11 次兩站都成功，首頁可見、原生應用執行完成，且 WebSocket 在收到資料後持續連線。
- [11 月 7 日 22:58 的報告](https://github.com/yuntechaiot/nsysu-eye-mask-sleep-monitor/actions/runs/42383883591)確認兩站都出現休眠按鈕、自動點擊並成功恢復。原版與 Apple 版分別約需 46.5、43.9 秒（含維持連線 15 秒）。
- [11 月 8 日 14:12 的報告](https://github.com/yuntechaiot/nsysu-eye-mask-sleep-monitor/actions/runs/42453698543)確認兩站仍能正常開啟，分別約需 19.4、18.7 秒；當時不需要喚醒。
- 唯一[失敗的排程](https://github.com/yuntechaiot/nsysu-eye-mask-sleep-monitor/actions/runs/42345547658)在 11 月 7 日 14:06 的合成測試中，隱藏 iframe 案例超過原先 3 秒期限；實際網站訪問被略過，沒有網站逾時報告。日誌不足以確定該次 iframe 延遲的底層原因。

因此將合成測試移至獨立工作流程，正向案例等待上限由 3 秒改成 10 秒，失敗時輸出完整案例判定欄位；負向案例仍驗證逾時與失敗。網站訪問程式的成功標準、每站 150 秒上限與重試次數維持原設定。

這段紀錄也出現兩次成功訪問相隔約 17 小時（期間一次測試失敗），之後兩站均已休眠並成功喚醒。排程延遲與漏跑仍可能超過 Streamlit 的閒置門檻，不能據此承諾永不休眠。

## 限制

此排程用來減少休眠機會，不是永不休眠或服務持續可用的保證。官方目前的閒置門檻為 12 小時；平台仍可因維護、資源限制或政策調整停止應用。

GitHub Actions 的排程可能延遲或在高負載時丟棄工作。公開儲存庫連續 60 天沒有活動時，排程也可能自動停用；請在 Actions 頁確認狀態並重新啟用。不使用自動空白 commit 或寫入儲存庫的方式維持活動。

- [Streamlit 休眠規則](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app#app-hibernation)
- [GitHub Actions 排程限制](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [GitHub Actions 計費說明](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
