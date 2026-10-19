# BioSearch · IR-HW3

本專案獨立位於 `C:\成大專案\IR-HW3`。目前使用 **3,000 篇 GLP-1 英文 PubMed 摘要**：完整保留原 1,000 篇快照，依相同搜尋條件增加 2,000 篇。沿用原始 tokenizer 與五方法檢索／評估，另依使用者要求加入第六種 BM25。HW2 的程式、資料、模型與環境未修改。繳交日期：2026/10/27。

## 語料擴充與版本

目前快照：`data/corpus/glp1-3000-20261015/`；原快照：`data/corpus/glp1-1000-20260929/`，維持唯讀。3,000 篇以 PMID 去重、限英文非空摘要；原 1,000 篇的文件欄位、內容、順序及 JSONL 位元組前綴均保留。新增文件依本次 PubMed `pub date` 候選順序納入，搜尋式仍為 GLP-1／glucagon-like peptide-1 的標題或摘要，出版日期截止仍為 **2026/09/29**；取得時間為 2026/10/15。這是原快照的擴充聯集，不能稱作當日搜尋的純粹前 3,000 名，也不是隨機樣本。

新增部分取得 2,100 篇原始紀錄，排除 26 篇，納入 2,000 篇；另 74 篇合格但未納入。原始 XML、搜尋回應、排除理由、取得時間、來源 URL 與 SHA256 隨新快照保存。`base-snapshot.json` 保留原 manifest。需要重現取得流程時執行 `scripts/expand_corpus.py`；已完成且參數相同的快照只驗證，不重新下載或覆寫。

語料擴充會改變 N、DF、IDF 與文件 norm，須在新固定語料上重新比較五方法。舊 1,000 篇實驗保留原 corpus hash，不能直接當成 3,000 篇結果。CLI 可用 `--snapshot data/corpus/glp1-1000-20260929` 讀取原基準；網站預設使用 3,000 篇。既有 `manual.json` 若屬於另一個 corpus hash，保持原檔不動，新語料標註另存 `data/judgments/by-corpus/<corpus_sha256>/manual.json`，不自動沿用舊判讀。

## 啟動

雙擊根目錄 **`start_hw3.cmd`**，瀏覽器開啟 **http://127.0.0.1:8503**。保持啟動視窗開啟，結束時按 Ctrl+C。HW3 使用自己的 `.venv`；不需要啟動 HW2，也不會占用 HW2 的 8501／8502。

本次交付已啟動一個背景 HW3 服務，可直接開啟網址。若要停止這個背景服務，雙擊 `stop_background_hw3.cmd`；它只檢查並停止有紀錄且命令符合本專案的 Python 程序。之後再以 `start_hw3.cmd` 前景啟動。

首次建置或套件遺失時，使用 Python 3.12 以上，在 PowerShell 執行：

```powershell
Set-Location -LiteralPath 'C:\成大專案\IR-HW3'
powershell -ExecutionPolicy Bypass -File scripts\setup_hw3.ps1
```

初次安裝需要網路；語料已隨專案保存，建置完成後可離線搜尋、比較、標註與評估。`requirements.txt` 為直接依賴，`requirements-lock.txt` 保存本次通過驗證的完整環境。搬到另一台電腦時重新建立 `.venv`，不要直接複製虛擬環境。

## 四個工作頁

1. **語料與設定**：文件數、tokens、詞彙數、CF／DF／IDF、五種向量權重與 BM25 公式與詞表下載。
2. **搜尋與排名**：Top 10 與小數分數、命中片段、完整原始摘要、逐詞 TF／DF／IDF／權重與 cosine 貢獻。
3. **方法比較**：同查詢的六組排名、Top 10 新進／移出文件與名次升降、顯式 L2 前後的 cosine 一致性，以及 raw dot 的補充對照。
4. **效能評估**：10 個固定查詢、人工相關性標註、候選池或全語料閱讀、CSV 匯入／匯出、P@k／Recall@k／MRR／nDCG@k、實驗報告匯出。

六種方法共用側欄前處理；側欄 IDF 選項適用原五種向量方法。BM25 使用獨立固定 IDF。預設採 C（原 tokenizer＋停用詞）與標準 IDF；可切換 B、D 或平滑 IDF。比較 weighting 時固定這些設定。

原 HW2 的 Zipf／回歸／殘差、Word2Vec／PCA／t-SNE 與活動文章庫管理沒有放入新介面。保留原文閱讀、詞頻與搜尋；搜尋專用的複合詞展開改為一致、可查核的文件／查詢分詞。拼字候選已獨立移植至互動搜尋，操作如下。

## 互動搜尋的拼字候選

在「搜尋與排名」輸入英文查詢，打字稍停（200 ms）即更新候選。例如輸入 `insulinn`，會出現可點選的 `insulin`。每個可能拼錯的詞分別顯示最多 3 個候選，標明詞在查詢中的位置；滑鼠停在按鈕上可查看替換後的完整查詢、編輯距離及語料 CF。

- 按「搜尋」直接使用輸入原文，不採用任何候選。
- 點選某個候選詞才會替換該次出現的詞並搜尋；其他詞、空白、標點及連字號保留。例如 `(insulinn), glucosee; GLP-1` 點選第一詞的 `insulin` 後，實際搜尋 `(insulin), glucosee; GLP-1`。
- 採用後輸入框與實際搜尋同步，畫面顯示「原始查詢 → 採用後查詢」。繼續修改輸入時會提醒目前結果仍屬於上次提交的查詢，直到再次按搜尋或點選候選。

候選沿用 HW2 的手寫 Levenshtein DP：4–5 字母最多 1 次編輯，6–64 字母最多 2 次；依距離升冪、CF 降冪、詞典序排序。校字詞彙只取 HW3 保存的 **原固定 1,000 篇摘要**（`data/corpus/glp1-1000-20260929/`），不讀 HW2 活動庫；使用相同 NFC／casefold／撇號及連字號正規化，保留停用詞和未 stemming 詞形。即使搜尋選 D／Porter，候選也維持原詞形。搜尋與評估仍使用目前的 3,000 篇語料。

已知詞不更動；未知詞若包含數字、非 ASCII 字元、長度 ≤3 或 >64、全大寫縮寫、混合大小寫，或為帶內部標點的複合詞，皆保留原文，例如 `GLP-1`、`BRCA1`、`TNF`、`mTOR`、`eGFR`、`1.5`、`cancerr-treatment`。無候選也保留原文；未知生醫詞不一定是錯字。

校字詞彙／索引按語料檔案與 tokenizer／校字來源指紋快取；單詞候選有界快取。輸入更新只重跑搜尋控制區，不執行完整排名；結果也按已提交查詢、方法、正規化與 engine 快取。候選按鈕使用 callback 同步輸入與搜尋狀態，過時候選不覆寫較新的輸入。

**校字只作用於互動搜尋。** 人工、規則弱標籤、PubMed 自動參考、批次實驗、CLI 與評估排名輸出持續使用 `data/queries.json` 的原始查詢。校字未加入 tokenizer、`Engine.rank` 或 `evaluate`；搜尋頁的 session_state 不參與正式評估，也不寫回查詢、標註或既有實驗。實作位於 `ir_hw3/spelling.py`，不匯入 HW2，無新增依賴。此次驗證另存 `reports/spelling-port-20261018/`。

## 權重定義

自 2026/10/16 起，Log TF 與兩種 IDF 的對數統一使用 **log10（底數 10）**。nDCG 的排名折扣仍依標準定義使用 log₂。舊 ln 報告保留於 `reports/HW3_REPORT.md`，舊實驗 manifest 的公式與 hash 不回寫；新實驗另存且記錄 `logarithm_base=10`。

文件與查詢使用相同詞彙表、前處理及權重。查詢重複詞保留實際 TF；OOV 不加入查詢向量。僅摘要正文參與計分，標題只供閱讀。

| 方法 | 詞在文件／查詢中出現 f 次，f > 0 |
|---|---|
| 原始 TF | f |
| Log TF | 1 + log10(f) |
| 僅 IDF | IDF（有出現就給權重，不使用重複次數） |
| TF-IDF | f × IDF |
| Log TF-IDF | (1 + log10(f)) × IDF |

f=0 時權重均為 0。標準 IDF=`log10(N/DF)`；平滑 IDF=`log10((N+1)/(DF+1))+1`。N 包含前處理後可能變成零向量的文件。預先建立每篇文件的 Counter、DF、倒排表與全文件 norm，不將集合 CF 誤當文件 TF。

原五種方法使用 cosine；第六種 BM25 使用獨立分數。皆僅返回分數 > 0 的文件；最多顯示 10 篇，完整非零排名供 MRR 計算。相似度不是正確率。為使浮點等價的結果穩定，排序先將分數取 12 位小數，再按數字 PMID 升冪同分排序；畫面保留 6 位小數，CSV 保存原始精度。

對非零向量，cosine 已除以兩個 L2 norm，所以顯式 L2 前後理論排名相同。raw dot 另作補充實驗，不能稱作未正規化 cosine。空白、全停用詞、OOV、零 IDF／零向量會返回無結果。

## 第六種方法 BM25

新增 BM25，固定 k1=1.2、b=0.75；BM25_IDF=`log10(1+(N−DF+0.5)/(DF+0.5))`。使用相同語料、前處理及查詢，僅摘要正文計分；dl 為前處理後 tokens，avgdl 包含全部文件，查詢 TF 線性累加。BM25 不使用側欄的標準／平滑 IDF、不做顯式 L2，分數可超過 1。詳見 [公式、差異、限制與重現](docs/BM25.md)。

六種方法已接入搜尋、方法比較、評估、候選池及 CLI（`search --method bm25`）。新實驗保存逐方法 scoring 與 BM25 參數，L2 檢查只含原五方法。舊五方法實驗與報告保留；不同方法清單的歷史 run 不直接產生受控差值。

## 人工相關性標註

`data/queries.json` 包含 10 個查詢與主題意圖。每個查詢都可由六種方法各 Top 20 的聯集開始閱讀，也可切至全部 3,000 篇，補查池外文件。

- `-1`：未標註，與不相關不同。
- `0`：不相關。
- `1`：相關。
- `2`：高度相關。

每筆人工判讀必須填寫理由。儲存到 `data/judgments/manual.json`，以語料和查詢 SHA256 防止舊標註套用到新資料。每次儲存讀取最新檔案合併，寫檔使用暫存與原子替換。CSV 以 `qid,pmid,grade,reason` 為判讀欄位，每列另附 `source=human,corpus_sha256,queries_sha256`；匯入時驗證版本、查詢、文件、整數等級、理由與重複紀錄，整批合法才合併。舊版四欄 CSV 須使用者明確勾選已核對版本才可匯入；有錯誤或部分缺漏的版本欄位不允許略過。無版本 CSV 無法自行證明原始語料／查詢版本。

請先參考 [人工判讀指南](docs/ANNOTATION_GUIDE.md)：它提供四級準則、理由範本與十查詢的納排界線建議，尚待你確認，沒有預填人工標籤。逐篇介面先顯示完整摘要，可用上一篇／下一篇閱讀，並篩選未標註文件；候選池進度與池外判讀數分開呈現。

評級與理由的草稿在同一個 Streamlit 連線中跨文件、查詢、範圍及工作頁保留，側欄持續提醒並提供 JSON 備份。**草稿尚未寫入檔案、不納入評估；關閉或重新整理連線前請儲存或下載備份。** 可儲存目前一篇或全部草稿，只合併實際改動的紀錄；缺理由或寫檔失敗會保留草稿。同筆紀錄若已被其他操作改動，儲存會拒絕覆蓋，請先備份草稿、還原為最新已儲存版本後重新判讀。有草稿時暫停 CSV 匯入，避免互相覆蓋。`-1` 的備忘理由只留在草稿，需改為 0／1／2 才能儲存為正式判讀；清空理由並儲存 `-1` 則移除既有判讀。

若採人工來源，至少需對 10 個查詢建立判斷依據並如實揭露涵蓋範圍。原題也允許依文件主題標籤建立簡單相關集合，本次報告採下述自動參考來源，沒有把人工判讀設為執行自動評估的前提。人工介面逐查詢區分「尚未標註」「已判讀但尚未找到相關文件」「已有相關文件」；有正例不代表候選池或全語料已讀完。僅標註候選池有 pooling bias；未標註文件評分時暫按 0 處理，因此同步報告 judged@k。Recall 分母是「已知相關集合」，標註不完整時不能宣稱完整語料 Recall。

平均指標沿用「至少有一篇已知相關文件才納入」的政策。畫面、`metrics_summary.csv`、`query_status.csv`、manifest 及 RQ 解讀均列出固定查詢總數、實際納入數、排除數與原因。沒有可納入的查詢時，平均指標顯示未計算（CSV 為空值），不填入零分；只完成 3 個可評估查詢時，平均母數就是 3／10。指標圖並排且固定 0–1 刻度。

## 自動參考評估與弱標籤對照

另依使用者指定加入 **PubMed 主題參考＋弱規則回退**，來源為 `pubmed_hybrid`，見 [規則與限制](docs/PUBMED_REFERENCE.md)。優先使用已保存 XML 的 MeSH、藥物／化學物質、補充概念與關鍵字；概念依據不足時才獨立套用原摘要 weak rule。每筆保存來源與證據，採二元 0／1，不寫入人工檔。這是自動參考評估，Recall 只針對規則集合。網站在「效能評估 → 效能比較 → 評估標註來源」切換；CLI 用 `experiment --source pubmed`。新 run 另存 `reports/pubmed_hybrid/runs/`，附完整規則、metadata、30,000 筆標籤、涵蓋率與 Top k 來源明細，原 human／weak_rules 結果保留。

人工標註初始為空。專案另提供**明確標示為 weak_rules 的示範**：每個查詢公開多組概念詞，摘要必須每組至少命中一詞，才給二元相關標籤。規則在原摘要上執行、覆蓋目前整批語料，不讀取任何排名。它仍與詞彙搜尋共享訊號，可能高估詞彙方法，不能視為人工或醫學相關性的標準答案。

原 `reports/weak_rules/` 根目錄保留先前的流程與數值示範，在歷史頁標為 legacy；不能視為目前程式的最新輸出。新弱標籤實驗另存 `reports/weak_rules/runs/`，人工結果另存 `reports/human/runs/`。兩者不互相覆蓋、不冒用來源。標註原文依據與限制隨報告保存。

每次執行以 UTC 時間與隨機短碼建立獨立 run，包含完成狀態與來源指紋，完成所有輸出後才發布至正式目錄。明確指定 `--output` 時只接受不存在或空目錄，拒絕覆寫已有成果。失敗暫存目錄保留供診斷，不列為成功歷史。效能頁「重現與報告」可查看歷史、設定、指紋與平均母數；輸出檔損壞的 run 不列為完整成功結果。

歷史比較先檢查人工／弱標籤來源、語料、查詢、判讀、k、程式、公式、同分規則與環境證據。任一不符則列出原因，不計算可被誤當受控比較的指標差值。前處理或 IDF 可作為明列的設定差異；若兩者同時變動，不能把效果歸因於單一因素。查詢／語料改版時，既有人工 JSON、CSV 與草稿不會自動遷移；需保留舊版並重新核對判讀。

## 重現

```powershell
# 語料、原始 XML、複製檔案完整性；正常使用不需要存取 HW2
.\.venv\Scripts\python.exe -B -X utf8 -m ir_hw3.cli verify

# 額外確認這次保護的 HW2 原始檔指紋仍相同
.\.venv\Scripts\python.exe -B -X utf8 -m ir_hw3.cli verify --source

# 搜尋：最高 10 名
.\.venv\Scripts\python.exe -B -X utf8 -m ir_hw3.cli search 'semaglutide weight loss' --method log_tfidf

# 六方法 × 十查詢；先用弱標籤完整跑通
.\.venv\Scripts\python.exe -B -X utf8 -m ir_hw3.cli experiment --source weak

# 平滑 IDF／Porter 對照，與預設輸出分開保存
.\.venv\Scripts\python.exe -B -X utf8 -m ir_hw3.cli --condition D --idf smooth experiment --source weak --output reports/D-smooth

# 完成人工標註後
.\.venv\Scripts\python.exe -B -X utf8 -m ir_hw3.cli experiment --source human

# 列出可追溯的歷史實驗；compare 後接兩個 run 目錄
.\.venv\Scripts\python.exe -B -X utf8 -m ir_hw3.cli history --source weak_rules
.\.venv\Scripts\python.exe -B -X utf8 -m ir_hw3.cli compare <left-run-directory> <right-run-directory>

# 數學、完整語料、標註儲存與實際 Streamlit UI 測試
powershell -ExecutionPolicy Bypass -File scripts\test_hw3.ps1

# 獨立 NumPy 計分與兩次實驗輸出逐位元核對
.\.venv\Scripts\python.exe -B -X utf8 scripts\verify_hw3.py

# 六組前處理／IDF 的後端計時，保留獨立效能紀錄
.\.venv\Scripts\python.exe -B -X utf8 scripts\profile_hw3.py
```

每次實驗輸出：`rankings.csv`、`metrics_per_query.csv`、`metrics_summary.csv`、`query_status.csv`、`normalization.csv`、`annotation_pool.csv`、`term_statistics.csv`、使用的 `queries.json` 和 `judgments.json`、`manifest.json` 與 `RQ_DISCUSSION.md`。manifest 記錄公式、控制設定、程式／資料／輸出 SHA256 及依賴版本。相同設定的 CSV 可逐位元比較。

`verify_hw3.py` 以兩個新的弱標籤 run 核對重現性，將兩路徑與 manifest hash 寫入 `reports/verification.json`，保留舊輸出。目前獨立 NumPy 分數驗證涵蓋 B／C／D × 標準／平滑 IDF 六設定：五方法 cosine 與 BM25 分開計數及報告誤差；效能計時與數值正確性證據分開保存。效能紀錄位於 `reports/performance/`，為單程序後端計時，包含共用快取與 lazy vector 建置，不等於瀏覽器延遲。

P@k 分母固定為 k，即使返回不足 k 篇；MRR 的每查詢 RR 使用完整返回排名；nDCG 使用 `2^grade−1`。若標準 IDF 讓所有查詢權重為 0，不強行返回任意零分文件。

## 需求與報告

題目副本：`docs/Homework-3.pdf`。對應表：`docs/HW3_REQUIREMENTS.md`。本次完整報告：[六方法自動參考評估、BM25 與 RQ1～RQ5](reports/HW3_REPORT_BM25.md)；[原五方法 log10 報告](reports/HW3_REPORT_LOG10.md)完整保留，含標籤來源、完整規則、來源涵蓋、逐查詢指標、實際排名例子、偏差限制及重現指紋；沒有宣稱已人工驗證。報告由固定歷史 run 衍生，不回寫原實驗；`scripts/build_hw3_report.py --report <新檔名>` 可重建並核對。原 `reports/HW3_REPORT_TEMPLATE.md` 保留供未來人工驗證版本使用，自動參考與人工結果持續分流。

操作展示流程見 [約 6 分 30 秒的 demo](docs/DEMO.md)。已確認人工判讀可依查詢意圖納入人體、動物與細胞研究，理由須註明類型；其餘查詢特有的納排界線仍依判讀指南逐項確認。

資料來源與複製指紋位於 `reports/provenance.json`。`ir_hw1/models.py`、`ir_hw1/preprocessing.py` 為未修改的沿用元件；其餘檢索／介面／評估程式放在 `ir_hw3/` 與根目錄 `app.py`。沒有複製 HW2 的 `.git`、`.venv`、訓練模型或整個活動索引。
