# IR-HW3 工作界線

- 本專案位於 `C:\成大專案\IR-HW3`，只修改此專案。`C:\成大專案\IR-HW2` 為原始成品，維持唯讀。
- 執行與測試使用本專案 `.venv\Scripts\python.exe`，不要改動或依賴 HW2 環境。
- 結構探索先確認 codebase-memory 的 project/generation，再使用 search_graph、trace_path、get_code_snippet；預設 Tier 2。每個依賴的檔案須查 check_index_coverage，已知缺口或 stale/unknown 時直接讀取原始碼。非代碼文字與尚未索引的新碼可讀取或 rg 補足，不能把圖中沒有結果當作不存在。
- `data/`、`reports/` 在圖索引刻意排除；語料與實驗以檔案內容、manifest 和 SHA256 驗證。
- 固定語料，不混用 HW2 的活動搜尋庫。文件與查詢使用相同前處理、詞彙表和 weighting。
- 人工標註與規則弱標籤分開保存及呈現。不能將未標註當成人工不相關，不能將弱標籤或 AI 判讀冒充人工判讀。
- 標準 cosine 在顯式 L2 正規化前後應相同；raw dot 必須另行標示。
- 修改計分或評估後執行 `scripts/test_hw3.ps1`；涉及數值或正式輸出時另執行 `scripts/verify_hw3.py`，保持實驗來源 hash 最新。
