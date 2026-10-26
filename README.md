# BioSearch · IR-HW3

## Streamlit Community Cloud 展示版

公開網站：[BioSearch · HW3](https://p77151087-ir-hw3.streamlit.app/)。儲存庫：[p77151087-jpg/IR-HW3](https://github.com/p77151087-jpg/IR-HW3)。部署分支 `codex/streamlit-cloud`，入口 `cloud_app.py`，Python **3.12**。2026/10/27 移除側欄展示版提示框，後端唯讀保護持續啟用。

展示版保留六方法 Top 10／分數、明確採用的拼字候選、原始摘要／命中高亮／計分說明、四模型近鄰與詞對比較、熱圖／散點／整體分析，以及已保存的評估圖表和報告下載。雲端後端拒絕訓練、語料擴充／下載、標註儲存／匯入與實驗保存；互動評估只在記憶體計算。C 前處理、公式、模型與歷史成果不變。本機 `app.py` 保留原功能，`start_hw3.cmd` 繼續使用 localhost:8503。

部署清單、逐檔 SHA256、Linux 環境設定、更新方式與驗證狀態見 [deployment/README.md](deployment/README.md)。依 `requirements.txt` 安裝 Linux 套件，不搬移 Windows 虛擬環境；平台管理 address/port。更新展示分支前必須重建部署清單、核對完整模型與副檔、驗證展示版，再推送指定分支。原始實驗紀錄不改寫。

本專案獨立位於 `C:\成大專案\IR-HW3`。目前使用 **3,000 篇 GLP-1 英文 PubMed 摘要**：完整保留原 1,000 篇快照，依相同搜尋條件增加 2,000 篇。沿用原始 tokenizer 與五方法檢索／評估，另依使用者要求加入第六種 BM25。HW2 的程式、資料、模型與環境未修改。繳交日期：2026/10/27。

## 目前十個預設查詢：TF/DF 四類＋六種搭配

依 2026/10/24 使用者圖片重新設計。搜尋頁可從「預設查詢（Q01～Q10）」填入並搜尋，方法比較、人工標註與正式評估使用同一版本。

| 查詢 | 類型 | 文字 |
|---|---|---|
| Q01 | 高 TF 高 DF | GLP-1 |
| Q02 | 低 TF 高 DF | receptor |
| Q03 | 高 TF 低 DF | MASLD |
| Q04 | 低 TF 低 DF | hypertension |
| Q05 | 高 TF 高 DF 搭配 低 TF 高 DF | GLP-1 receptor |
| Q06 | 高 TF 高 DF 搭配 高 TF 低 DF | GLP-1 MASLD |
| Q07 | 高 TF 高 DF 搭配 低 TF 低 DF | GLP-1 hypertension |
| Q08 | 低 TF 高 DF 搭配 高 TF 低 DF | receptor MASLD |
| Q09 | 低 TF 高 DF 搭配 低 TF 低 DF | receptor hypertension |
| Q10 | 高 TF 低 DF 搭配 低 TF 低 DF | MASLD hypertension |

四類代表詞依序為 GLP-1（高 TF／高 DF）、receptor（低 TF／高 DF）、MASLD（高 TF／低 DF）、hypertension（低 TF／低 DF）。命中文件平均 TF ≥3 為高、≤1.6 為低；DF ≥20% 為高、≤5% 為低，基準是 3,000 篇＋C。每篇文件仍使用實際 TF；不把 CF 當作文件 TF，也不在查詢中重複詞。詳見 [分類統計、門檻及限制](docs/QUERY_DESIGN_TFDF.md)。

網站所有查詢選單共用完整條件標籤；例如 Q05 顯示「高 TF 高 DF 搭配 低 TF 高 DF」。這只是顯示名稱的轉換，`data/queries.json` 的查詢文字、分類代號、hash、參考標籤與既有實驗版本保持不變。

舊十查詢、規則及報告完整保留。新規則綁定 queries hash，新人工路徑區分 corpus＋queries；同名 Q01 不會套用舊答案。新舊查詢的平均指標不能直接視為受控改善。新結果：[TF/DF 查詢報告](reports/HW3_REPORT_TFDF.md)；原疾病／藥物查詢報告仍是歷史成果。

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

## 五個工作頁

1. **語料與設定**：文件數、tokens、詞彙數、CF／DF／IDF、六種方法的白話說明與詞表下載。方法表只顯示「方法／意義」，已移除公式欄；計算公式仍記錄於本說明、程式與實驗 manifest，計分不受影響。
2. **搜尋與排名**：原五種權重固定使用 cosine，BM25 使用獨立分數；Top 10 顯示查詢詞命中次數、摘要總詞數，另提供命中片段、完整原始摘要，以及逐詞 TF／DF／IDF／權重與計分貢獻。搜尋頁不提供「先做 L2 正規化」選項。
3. **方法比較**：同一篇文章在六種方法中的 Top 10 名次總覽，各方法的分數／命中次數／摘要總詞數明細，以及分開呈現的共同、新進、移出文章；提供顯式 L2 前後的向量長度／cosine／排名對照，另保留 raw dot 與 cosine 並排對照。
4. **效能評估**：固定使用 PubMed 主題參考＋弱規則回退，選 k 後執行六方法評估，顯示四張指標圖、精簡平均表與逐查詢結果；提供弱規則與十查詢平均的白話說明。
5. **Embedding／TF-IDF 詞彙關聯**：固定 3,000 篇／C 前處理（移除停用詞）／四組新訓練 Word2Vec，提供單詞近鄰、兩詞 cosine、十詞重疊與 45 詞對 Spearman、同色階熱圖、可辨識詞對的散點及 CSV。

方法比較頁在 BM25 參數後補充本批語料的選用理由：GLP-1 索引詞在單篇命中摘要中最多出現 16 次，因此需要詞頻飽和，保留重複命中的訊號而讓邊際加分遞減；C 前處理後摘要長度的第 10、90 百分位分別為 114、246 詞，因此仍需要長度校正，降低長摘要因命中機會較多而取得的優勢。頁面直接從目前 Engine 的摘要長度與 GLP-1 postings 計算這些統計，不讀取評估標籤或排名。這些特性支持採用兼顧詞頻飽和與長度校正的 BM25 基準，但無法單獨推導出最適合的數值；`k1=1.2、b=0.75` 沿用 [Lucene／Elasticsearch 預設值](https://www.elastic.co/docs/reference/elasticsearch/index-settings/similarity)，尚未經本語料調參證明優於其他組合。統計及來源指紋保存在 `reports/bm25-rationale-20261026/corpus-stats.json`；未修改參數、計分、標籤或正式實驗。

語料頁的「搜尋詞項」同步篩選表格與 DF 長條圖，採不分大小寫的包含比對；表格最多 100 詞、圖表取符合詞項中 CF 最高的前 20 詞。沒有符合詞項時清空圖表，清除輸入則恢復總覽。「下載完整詞項統計」仍包含整份詞彙表，篩選不改變語料統計或檢索結果。

效能圖表：在「效能評估」選擇 k，再按「執行六種方法評估」。Precision@k、Recall@k、MRR、nDCG@k 分成四張六方法長條圖，固定 0–1 刻度，顯示四位小數與查詢母數；寬畫面兩欄、窄畫面向下排列。圖旁保留來源、查詢納入數及自動參考的 Recall 限制；無可納入查詢時不繪製零分圖。圖表直接使用既有平均指標，不改變評估公式。

「圖表顯示」可選全部查詢平均或 Q01～Q10；預設保留平均。單查詢模式的四張圖與六方法表格直接使用該查詢既有逐查詢指標，不重新評估或改變資料；切回平均會恢復原平均值。單查詢的倒數排名標為 RR，平均模式為 MRR；兩者均使用完整排名。查詢編號、實際文字及來源在圖旁標明；沒有參考正例的查詢顯示未計算原因，不畫零分圖。更換 k 後保留檢視選擇，須重新執行評估；下載平均與完整逐查詢 CSV 的內容與精度不受檢視切換影響。

依使用者指定，效能頁已移除人工標註／實驗紀錄頁籤與來源選單，固定為「PubMed 主題參考＋弱規則回退」。主畫面保留固定來源、k、查詢納入數、執行按鈕及結果；平均表只顯示方法與四項指標。「弱規則是什麼？十個查詢如何評估？」提供白話說明與 Q01～Q10 完整查詢文字。每個方法對十個查詢分別排名、計算指標，再對可納入查詢平均；不把十組合成一次搜尋，也不使用互動搜尋框的臨時文字。逐查詢結果、規則明細與下載／保存仍收合。更改 k 或參考標籤版本後不顯示過時圖表。原人工檔、保留元件、歷史 run、CLI 的 human／weak／pubmed 來源與評估公式均保留；網站不讀寫人工檔、不掃描實驗歷史。

搜尋與方法比較明細表格的「查詢詞命中次數」為各不重複查詢詞在單篇摘要內的 TF 加總，不要求相鄰，不將查詢重複 TF 再乘入出現次數；OOV 不增加次數。「摘要總詞數」為摘要正文經 C 前處理後的 token 數（移除停用詞，不含標題），不是全文字數或向量 L2 norm。Top 10 CSV 同步提供 `query_term_hits` 與 `abstract_length_tokens`；這些欄位只補充顯示，原排名、分數與正式實驗輸出不變。

方法比較總覽採一列一篇文章，列出六種方法各自的名次，並以「詞命中數／文章長度」取代原「Top 10 方法數」欄位。兩個統計欄位與搜尋、各方法明細共用計算方式；文章長度指 C 前處理後的摘要 token 數。CSV 同步輸出 `query_term_hits` 與 `abstract_length_tokens`。總覽使用可左右捲動的原生表格，完整標題自動換行，固定左側 PMID 與表頭，亦可聚焦後以 ←／→ 捲動；所有標題及儲存格文字先做 HTML escape。原內部排序維持先依入榜方法數、再依最佳名次與數字 PMID；「—」表示該方法前十名之外。

點選總覽的任何欄位標題，第一次由高到低、第二次由低到高，箭頭及提示文字顯示目前方向。PMID、方法名次、命中數與文章長度採數字排序（10 與 2 不會按字串排列）；文章標題採英文文字排序；「—」兩個方向都固定排最後，同值維持原預設次序。表頭按鈕亦支援鍵盤 Enter／空白鍵。排序由專案內固定的 `ir_hw3/ranking_overview.js` 執行，只移動畫面的列，不修改儲存格、排名分數或正式實驗；CSV 保留原預設次序。換查詢或頁面重新渲染後恢復預設順序。

原五方法明細標示 `cosine 分數`，BM25 明細標示 `BM25 分數`，不在同一格混合文件編號與分數。兩方法切換以「基準 → 比較」為方向，分成共同、新進與移出三組；共同文件顯示兩邊名次和明確的上升／下降文字，新進與移出只列已知的 Top 10 名次，沒有把池外名次假定成第 11 名。下載名次變化 CSV 的池外位置明列 `Top 10 外`。上述調整只涉及呈現，不重算或覆寫正式實驗。

網站六種檢索方法固定共用 C 前處理（原 tokenizer＋移除停用詞），原五種向量方法的 IDF 固定為 `log10(N/DF)`；BM25 保留自己的固定 IDF 公式。原題要求前處理、IDF 與 weighting 對照，沒有要求提供前處理／IDF 切換選單，因此網站已移除兩個選單，固定比較條件。CLI 的 B／D、平滑 IDF 及既有實驗仍保留供重現歷史紀錄。

原 HW2 的 Zipf／回歸／殘差、PCA／t-SNE 與活動文章庫管理沒有放入新介面。依老師新增要求，Word2Vec 已以獨立詞彙比較頁加入，四組模型在 HW3 從頭訓練；保留原文閱讀、詞頻與搜尋。搜尋專用的複合詞展開改為一致、可查核的文件／查詢分詞。拼字候選已獨立移植至互動搜尋，操作如下。

## Embedding 與 TF-IDF 詞彙關聯（新增）

第五頁分成「找相關詞／比較兩個詞／整體分析」，預設先看單詞查詢；主畫面用白話說明 TF-IDF 看文章分布、Embedding 看上下文。「比較設定」可更換 CBOW／Skip-Gram、window 2／5 與顯示詞數 5／10／20；訓練參數、四張語料統計卡及版本放入收合的「資料與模型明細」，只有一份完成成果時不顯示單選項 run 選單。

單詞及詞 A／B 都有附中文提示的預選詞（如 insulin／胰島素、glucose／葡萄糖、obesity／肥胖）；選擇只代填英文，仍可自行修改，按比較按鈕才更新結果。輸入一詞後按「比較近鄰」，兩邊同步更新長條圖與中文表格，顯示實際分析詞；相同詞、模型及詞數再次送出時，會說明結果維持相同。「只在這邊前 k 名」只表示另一邊未入前 k 名，不代表該詞完全不存在或不相關。兩張長條圖維持 cosine 0–1 刻度，資料與表格相同；CF／DF 與重疊率分母收在「詞頻與比較規則」。

兩詞模式按「比較詞對」，一次比較 TF-IDF 及四組模型；缺向量顯示「無法計算」，保留原因，不當成 0。整體分析固定十詞，與互動輸入分開：四模型摘要、原有兩張熱圖及 45 詞對散點圖直接顯示並附讀圖方式，逐詞結果與原始分數另收合。熱圖隨所選模型切換，固定詞集不受單詞輸入影響；散點同時包含四組模型。下載與重現另收合；CSV 與報告不隨互動改寫。這頁統一 C，與檢索共用固定停用詞表；模型與資料在建模前移除停用詞，並非顯示時隱藏。單詞或詞對輸入停用詞會明確提示。搜尋拼字及評估 session_state 獨立；切換頁面只載入模型，不訓練或執行文件排名。

「整體分析」最前方有「TF-IDF 和 Embedding 的關係一樣嗎？」說明與四模型平均 Top-10 重疊率表，顯示有效分析詞數；固定使用十個詞的前 10 名，不隨互動 k 或單詞輸入改變。簡單結論按保存結果指出重疊最高的模型及平均共同詞數，清楚說明重疊不等於正確率。原本隨 k 切換的摘要、Spearman 及逐詞明細保留於進階收合區。熱圖與散點的滑鼠提示改為中文，散點顯示模型、詞對、詞對編號、TF-IDF／Embedding 相似度與共同出現摘要篇數；模型值與圖例使用「視窗」文字，保留原始分數及點位。

重疊率表下另有三步計算說明與真實清單範例：semaglutide 在 TF-IDF／Skip-Gram 視窗 5 的共同詞為 subcutaneous，1÷10＝10%；十個有效分析詞的共同詞次合計 21，21÷(10×10)＝21%。可展開十詞明細查共同詞數及詞名。散點圖前說明 X／Y 與四模型的讀法，圖後可選 semaglutide／liraglutide 或 insulin／receptor，對照保存的四組 X／Y 分數、詞對編號和共現篇數；切換範例不篩選原圖或重算分數。

四組均使用同一批 3,000 篇摘要、32,656 個非空句、539,158 tokens；完整 C 詞彙 31,662，每模型與共同候選池 17,578 詞。建模前移除固定 132 個停用詞（`resources/stopwords.json`；刻意保留 no、not、without），不 stemming、不展開搜尋複合詞，僅摘要正文。模型各自新初始化，100 維、30 epochs、min_count=2、negative=5、sample=0.001、seed=42、workers=1；其餘參數沿用並保存。句界不跨文件、摘要區塊或偵測句子；window 按去停用詞後留下的詞計算，未列入停用詞表的一般詞與數字仍可能入榜。

TF-IDF 主版本為 `TF × log10(N/DF)`，先在完整詞表對每個文件列做 L2，再取 3,000 維詞欄向量計算詞間 cosine。Embedding 用原始 100 維向量在自己的空間計算 cosine，不跨空間互算。不先做文件 L2 時，正的固定 IDF 倍數會在詞欄 cosine 抵消；本方法保留的是 IDF 改變文件 norm 後的間接效果。

所有方法共用四模型詞彙與 TF-IDF 非零欄交集。近鄰排除自身，只返回正 cosine，不用零分補足；同分取 12 位小數後按詞典序。重疊分母固定為請求 k；缺向量顯示 NA。固定 45 詞對、熱圖與散點保留負分；Spearman 採相同詞對順序、ties 平均名次，缺值／常數情況明列。重疊與 Spearman 是一致程度，不是語意正確率。

本次 C 的平均 Top-10 重疊：CBOW w2 **6%**、CBOW w5 **5%**、Skip-Gram w2 **8%**、Skip-Gram w5 **21%**；45 詞對 Spearman 依序 **0.3116、0.4387、0.4095、0.5159**。單次 seed 與單一主題不能證明某架構普遍最佳。例如 semaglutide 的 TF-IDF 前三已為 oral、agonist、weight，而非停用詞；這仍不等於人工語意驗證。完整結果見 [比較報告](reports/word_association/runs/20261024-c-four-models/REPORT.md)、[方法與觀察說明](docs/WORD_ASSOCIATION.md)。

成果保存於 `reports/word_association/runs/20261024-c-four-models/`：四組完整模型、詞彙／向量、逐 epoch loss、TF／CF／DF／IDF／文件 norm、文件與句子順序、共同池、CSV、五熱圖與散點，以及程式／語料／停用詞表／依賴指紋。驗證證據另存 `reports/association-c-20261024/`。原 B 詞彙關聯模型與 run 依使用者要求移除；原 1,000 篇快照、既有人工標註、RQ1–RQ5 與檢索評估歷史結果保留。

```powershell
# 明確觸發新訓練；每次建立新 run，既有模型不續訓也不覆寫。
.\.venv\Scripts\python.exe -B -X utf8 -m ir_hw3.embedding_training

# 離線核對模型、hash、統計、45 詞對與獨立計算；不訓練。
.\.venv\Scripts\python.exe -B -X utf8 -m ir_hw3.association_validation --run reports/word_association/runs/20261024-c-four-models

# 將測試結果另存，不覆寫歷史 pytest.xml。
powershell -ExecutionPolicy Bypass -File scripts\test_hw3.ps1 -ReportPath reports/word-association-20261024/pytest.xml -BaseTemp tmp/association-final
```

Streamlit 只讀已完成且通過指紋檢查的模型，並快取模型、稀疏矩陣與按詞近鄰；不建立全詞彙密集相似度矩陣，也不在 rerun 重訓。正式檢索、標註評估、批次 CLI 仍使用原始查詢，沒有加入 Embedding／校字的隱藏前處理。新直接依賴為 Gensim 4.4.0、SciPy 1.18.1、Matplotlib 3.10.8，完整實測版本見 lock 與模型 metadata；只安裝在 HW3 `.venv`。

校字索引支援程式重新載入後沿用既有快取：以穩定的 Mapping 介面區分詞頻字典與已準備索引，避免舊 `SpellingIndex` 因類別重建而被誤當字典、觸發 `.items()` 錯誤。回歸測試重現模組重新載入，核對建議內容不變且候選快取仍被沿用；拼字規則、實際查詢與檢索計分不變。

## 互動搜尋的拼字候選

在「搜尋與排名」輸入英文查詢，打字稍停（200 ms）即更新候選。例如輸入 `insulinn`，會出現可點選的 `insulin`。每個可能拼錯的詞分別顯示最多 3 個候選，標明詞在查詢中的位置；滑鼠停在按鈕上可查看替換後的完整查詢、編輯距離及語料 CF。

- 按「搜尋」直接使用輸入原文，不採用任何候選。
- 點選某個候選詞才會替換該次出現的詞並搜尋；其他詞、空白、標點及連字號保留。例如 `(insulinn), glucosee; GLP-1` 點選第一詞的 `insulin` 後，實際搜尋 `(insulin), glucosee; GLP-1`。
- 採用後輸入框與實際搜尋同步，畫面顯示「原始查詢 → 採用後查詢」。繼續修改輸入時會提醒目前結果仍屬於上次提交的查詢，直到再次按搜尋或點選候選。

候選沿用 HW2 的手寫 Levenshtein DP：4–5 字母最多 1 次編輯，6–64 字母最多 2 次；依距離升冪、CF 降冪、詞典序排序。校字詞彙只取 HW3 保存的 **原固定 1,000 篇摘要**（`data/corpus/glp1-1000-20260929/`），不讀 HW2 活動庫；使用相同 NFC／casefold／撇號及連字號正規化，保留停用詞和未 stemming 詞形。即使搜尋選 D／Porter，候選也維持原詞形。搜尋與評估仍使用目前的 3,000 篇語料。

已知詞不更動；未知詞若包含數字、非 ASCII 字元、長度 ≤3 或 >64、全大寫縮寫、混合大小寫，或為帶內部標點的複合詞，皆保留原文，例如 `GLP-1`、`BRCA1`、`TNF`、`mTOR`、`eGFR`、`1.5`、`cancerr-treatment`。無候選也保留原文；未知生醫詞不一定是錯字。

校字詞彙／索引按語料檔案與 tokenizer／校字來源指紋快取；單詞候選有界快取。輸入更新只重跑搜尋控制區，不執行完整排名；結果也按已提交查詢、方法與 engine 快取。候選按鈕使用 callback 同步輸入與搜尋狀態，過時候選不覆寫較新的輸入。

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

對非零向量，cosine 已除以兩個 L2 norm，所以顯式 L2 前後理論排名相同，搜尋固定直接使用 cosine。「方法比較 → L2 正規化前後比較」依題目**僅正規化文件**：令 `d'=d/||d||`，查詢 q 的權重及重複 TF 保持原值，前後皆計算標準 cosine；後者為 `q·d'/(||q||×||d'||)`。原五方法共用 `ir_hw3/normalization.py` 的文件 L2 實作，未呼叫會同時縮放查詢的舊 `Engine.rank(normalize=True)` 分支；BM25 不適用。頁面顯示完整非零排名是否一致、最大分數差、保持不變的查詢向量長度及變成 1 的首篇文件向量長度，以及逐篇前後名次／cosine；前十名取兩邊聯集，不為無結果補文件。下載含 `normalization_scope=documents_only`、兩邊查詢與文件 norm、文件 L2 後與原始查詢的點積 `document_l2_dot`、標題及原始精度分數。`document_l2_dot` 尚未除查詢 norm，不能直接稱作 cosine。向量 norm 使用完整詞彙空間，與摘要 token 數不同；零向量保留 0，沒有可比較結果時明示原因。

L2 前後完整排名一致時，相同標註與 k 下的 Precision@k、Recall@k、MRR、nDCG@k 也相同；這是排名相同的直接結果，不表示取得新的人工驗證。原始浮點差容許 1e-10，排名使用既有同分規則。下方另並排顯示 raw dot（共同詞權重乘積總和）與 cosine（再除以兩邊向量長度），共用同一權重選項，觀察向量大小對點積排名的影響；raw dot 不能稱作未正規化 cosine。後端 L2 等價驗證與實驗輸出維持保留。空白、全停用詞、OOV、零 IDF／零向量會返回無結果。

新實驗的 `normalization.csv` 與 manifest 明記 `normalization_scope=documents_only`、查詢權重不變、前後查詢 norm、是否有非零結果可供比較；零結果列保留未計算狀態，manifest 揭露納入與略過數。舊雙向 L2 的程式分支、歷史 run 與 2026/10/26 較早的檢查資料保留為歷史證據，不改寫成僅文件的實驗。修正後的直接比較與來源指紋見 `reports/l2-documents-only-20261026/`。

## 第六種方法 BM25

新增 BM25，固定 k1=1.2、b=0.75；BM25_IDF=`log10(1+(N−DF+0.5)/(DF+0.5))`。使用相同語料、前處理及查詢，僅摘要正文計分；dl 為前處理後 tokens，avgdl 包含全部文件，查詢 TF 線性累加。BM25 使用獨立 IDF、不做顯式 L2，分數可超過 1。詳見 [公式、差異、限制與重現](docs/BM25.md)。

六種方法已接入搜尋、方法比較、評估、候選池及 CLI（`search --method bm25`）。新實驗保存逐方法 scoring 與 BM25 參數，L2 檢查只含原五方法。舊五方法實驗與報告保留；不同方法清單的歷史 run 不直接產生受控差值。

## 人工相關性標註（保留資料與元件）

目前網站固定採自動參考評估，人工介面已移出；下述為保留元件與既有資料契約，CLI 仍可使用 human 來源。既有標註與草稿不自動刪除；舊連線若仍有草稿，側欄持續提供 JSON 備份。人工元件的儲存、草稿、衝突及錯誤恢復仍由隔離測試頁驗證，不在網站重新顯示。

`data/queries.json` 包含 10 個查詢與主題意圖。每個查詢都可由六種方法各 Top 20 的聯集開始閱讀，也可切至全部 3,000 篇，補查池外文件。

- `-1`：未標註，與不相關不同。
- `0`：不相關。
- `1`：相關。
- `2`：高度相關。

每筆人工判讀必須填寫理由。儲存到 `data/judgments/manual.json`，以語料和查詢 SHA256 防止舊標註套用到新資料。查詢版本變更時另存 `data/judgments/by-corpus/<corpus>/by-queries/<queries>/manual.json`，不改寫原檔。每次儲存讀取最新檔案合併，寫檔使用暫存與原子替換。CSV 以 `qid,pmid,grade,reason` 為判讀欄位，每列另附 `source=human,corpus_sha256,queries_sha256`；匯入時驗證版本、查詢、文件、整數等級、理由與重複紀錄，整批合法才合併。舊版四欄 CSV 須使用者明確勾選已核對版本才可匯入；有錯誤或部分缺漏的版本欄位不允許略過。無版本 CSV 無法自行證明原始語料／查詢版本。

請先參考 [人工判讀指南](docs/ANNOTATION_GUIDE.md)：它提供四級準則、理由範本與十查詢的納排界線建議，尚待你確認，沒有預填人工標籤。逐篇介面先顯示完整摘要，可用上一篇／下一篇閱讀，並篩選未標註文件；候選池進度與池外判讀數分開呈現。

評級與理由的草稿在同一個 Streamlit 連線中跨文件、查詢、範圍及工作頁保留，側欄持續提醒並提供 JSON 備份。**草稿尚未寫入檔案、不納入評估；關閉或重新整理連線前請儲存或下載備份。** 可儲存目前一篇或全部草稿，只合併實際改動的紀錄；缺理由或寫檔失敗會保留草稿。同筆紀錄若已被其他操作改動，儲存會拒絕覆蓋，請先備份草稿、還原為最新已儲存版本後重新判讀。有草稿時暫停 CSV 匯入，避免互相覆蓋。`-1` 的備忘理由只留在草稿，需改為 0／1／2 才能儲存為正式判讀；清空理由並儲存 `-1` 則移除既有判讀。

若採人工來源，至少需對 10 個查詢建立判斷依據並如實揭露涵蓋範圍。原題也允許依文件主題標籤建立簡單相關集合，本次報告採下述自動參考來源，沒有把人工判讀設為執行自動評估的前提。人工介面逐查詢區分「尚未標註」「已判讀但尚未找到相關文件」「已有相關文件」；有正例不代表候選池或全語料已讀完。僅標註候選池有 pooling bias；未標註文件評分時暫按 0 處理，因此同步報告 judged@k。Recall 分母是「已知相關集合」，標註不完整時不能宣稱完整語料 Recall。

平均指標沿用「至少有一篇已知相關文件才納入」的政策。畫面、`metrics_summary.csv`、`query_status.csv`、manifest 及 RQ 解讀均列出固定查詢總數、實際納入數、排除數與原因。沒有可納入的查詢時，平均指標顯示未計算（CSV 為空值），不填入零分；只完成 3 個可評估查詢時，平均母數就是 3／10。指標圖並排且固定 0–1 刻度。

## 自動參考評估與弱標籤對照

目前網站固定使用 **PubMed 主題參考＋弱規則回退**，來源為 `pubmed_hybrid`，見 [規則與限制](docs/PUBMED_REFERENCE.md)。優先使用已保存 XML 的 MeSH、藥物／化學物質、補充概念與關鍵字；概念依據不足時才獨立套用摘要 weak rule。每筆保存來源與證據，採二元 0／1，不寫入人工檔。這是自動參考評估，Recall 只針對規則集合。CLI 用 `experiment --source pubmed`。新 run 另存 `reports/pubmed_hybrid/runs/`，附完整規則、metadata、30,000 筆標籤、涵蓋率與 Top k 來源明細，原 human／weak_rules 結果保留。

人工標註初始為空。專案另提供**明確標示為 weak_rules 的示範**：每個查詢公開多組概念詞，摘要必須每組至少命中一詞，才給二元相關標籤。規則在原摘要上執行、覆蓋目前整批語料，不讀取任何排名。它仍與詞彙搜尋共享訊號，可能高估詞彙方法，不能視為人工或醫學相關性的標準答案。

原 `reports/weak_rules/` 根目錄保留先前的流程與數值示範，在歷史頁標為 legacy；不能視為目前程式的最新輸出。新弱標籤實驗另存 `reports/weak_rules/runs/`，人工結果另存 `reports/human/runs/`。兩者不互相覆蓋、不冒用來源。標註原文依據與限制隨報告保存。

每次執行以 UTC 時間與隨機短碼建立獨立 run，包含完成狀態與來源指紋，完成所有輸出後才發布至正式目錄。明確指定 `--output` 時只接受不存在或空目錄，拒絕覆寫已有成果。失敗暫存目錄保留供診斷，不列為成功歷史。歷史、設定、指紋與平均母數可從保留的 run 檔案或 CLI `history` 查閱；輸出檔損壞的 run 不列為完整成功結果。

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
