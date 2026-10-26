# Streamlit Community Cloud 部署

- Repository：https://github.com/p77151087-jpg/IR-HW3 （公開、獨立 HW3）
- Branch：`codex/streamlit-cloud`
- Main file：`cloud_app.py`
- Python：**3.12**（本機 3.12.14）
- 網站：https://p77151087-ir-hw3.streamlit.app/ （使用者於 2026/10/27 提供部署網址與網站畫面；匿名操作及雲端日誌仍待獨立核對）

部署分支採 `manifest.json` 的逐檔 allowlist，額外包含 manifest 本身；`main` 與既有歷史保留。原始語料、C 四模型 run 和保存評估的 manifest、原始副檔逐位元保留，不重訓、不刪除原 run 的 hash 項目。單檔必須小於 100 MiB。所有檔案透過 `.gitattributes` 禁止換行轉換，避免 Windows/Linux checkout 改變歷史 SHA256。

網站依賴：根目錄入口、`ir_hw1` 沿用 tokenizer/model 定義、`ir_hw3` 程式與排名表 JS、固定 stopwords、兩份 snapshot 的 JSONL/selection/manifest/原始 XML、當前 queries/design/reference_rules、完整 `20261024-c-four-models`（含四個 Gensim 模型、vectors/vocabulary/metadata/loss、TF/TF-IDF 稀疏矩陣及統計、句子順序、原始碼副本、成果 CSV/JSON/圖表/報告）、`20261026T105110.598151Z-af1e25ab` 完整 PubMed 自動參考評估，以及兩份 HW3 報告。部署清單列出每個檔案大小與 SHA256。

不發布 `.venv`、bytecode、tmp、log、secrets、人工標註與草稿、output、本機其他歷史 run。Gensim 模型每個約 14 MiB，無需 LFS 或外部下載；啟動只讀 vectors 與矩陣、按需快取，完整模型仍保留供完整性驗證及重現。互動圖採 Altair，中文字型由瀏覽器提供，不依賴 Windows 字型；保存 PNG 原樣提供下載。

雲端入口永久啟用程序級展示模式；後端保存、匯入、下載語料、訓練函數及 Gensim train 被拒絕，另由 audit hook 阻擋專案內檔案寫入。數值公式、C 前處理、模型及歷史 run 不變。快取限記憶體或 OS temporary directory，Matplotlib 字型快取位於 OS temporary directory；Streamlit server address/port 由平台管理。`start_hw3.cmd` 仍明確使用 localhost:8503，本機 `app.py` 不啟用展示限制。

更新：在本機完整版完成新成果與驗證，將新 run 另存；確認要展示的 run 常數。執行 `.venv/Scripts/python.exe -B -X utf8 scripts/build_cloud_bundle.py`，review manifest，測試 cloud entry，再以清單更新雲端分支（禁止盲目 git add 整個資料夾、禁止 force push）。執行 `scripts/build_cloud_bundle.py --verify --tracked` 後推送，Community Cloud 自動更新。requirements 更新會重新安裝；Python 版本在部署 Advanced settings 設為 3.12。不得直接在雲端產生正式成果。

本機驗證使用獨立埠 8513；完整測試、數值驗證與雲端測試輸出放在本機 `tmp/cloud-validation`，部署證據摘要將記錄於本文件。正式上線前另檢查雲端 build logs、應用 logs、主要功能與匿名可存取性。

## 已完成的部署前驗證

- 完整測試：249 passed；本機完整版 14 項介面測試另行通過。
- cloud_app：六方法 Top 10、候選明確採用、摘要高亮、四模型／近鄰／詞對／熱圖／散點、評估與下載通過；12 個修改後端與直接寫檔全部拒絕，190 個受保護檔案 hash 不變。
- 四模型離線重載與 62 個 artifact 全部通過；獨立矩陣誤差 0，詞對最大誤差 2.78e-16，近鄰最大誤差 2.22e-16，C 前處理及原始來源指紋一致。
- Python 3.12 x86_64 Linux binary wheels 與全相依已成功解析及下載；實際 Linux 執行仍須以 Community Cloud build/runtime logs 確認。本機 pip check 通過。
- Git 診斷：實際根目錄為 IR-HW3，core.bare=false、無 GIT_DIR/GIT_WORK_TREE 污染、原始 main/remote 可正常讀取；不刪除 .git、不 force push。採隔離 index 建立展示分支，main、工作樹與歷史資料不因篩選而刪除。

機器可讀證據見 validation.json；公開網址已由使用者提供；匿名操作與雲端日誌仍待獨立核對。

- 獨立檢索數值：900,000 cosine 分數，最大誤差 1.11e-16；180,000 BM25 分數誤差 0。B/C/D × standard/smooth 六設定全部通過；文件 L2 等價及兩次實驗逐位元重現通過。驗證 run 與 verification.json 另存 tmp/cloud-validation/numeric，沒有覆寫 reports/verification.json 或舊 run。
- 最終展示 AppTest 峰值 Windows working set：600.98 MiB（包含六方法、四模型、圖表與評估）；這是單程序本機測量，Linux 實際使用量待部署日誌確認。快取為共享模型/engine 加有限筆數的查詢快取，不產生全詞彙密集相似度矩陣。
- HW2 原始保護指紋：93 個檔案全部不變；本次未對 HW2 執行修改或部署。

更新分支的實際指令：重建並核對清單後執行 `scripts/prepare_cloud_commit.py`（隔離 index、保留工作樹），再執行 `git push origin refs/heads/codex/streamlit-cloud`；不切換到精簡分支刪除本機歷史資料。

- 乾淨部署包：僅複製 allowlist 與 manifest 到獨立暫存目錄，再執行完整 cloud_app 介面與後端保護檢查，全部通過；作業題目 PDF 亦已納入。路徑大小寫與常見憑證簽章掃描通過。

2026/10/27：依使用者要求移除側欄「雲端展示版」提示框。cloud_app 介面煙霧測試通過，Top 10 正常；程序級展示模式與後端寫入拒絕持續啟用，demo_policy.py 未修改。
