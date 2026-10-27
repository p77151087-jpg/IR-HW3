# HW3 詞彙關聯：方法與實際觀察

主成果：[C 完整報告、十詞全部近鄰與 45 詞對](../reports/word_association/runs/20261024-c-four-models/REPORT.md)。此功能獨立於 RQ1–RQ5 的文件檢索評估，沒有將詞關聯一致度當成檢索正確率。

網站以「找相關詞／比較兩個詞／整體分析」分區，先看互動輸入與結果；設定、資料／訓練資訊及下載各自收合。單詞與詞 A／B 可選附中文提示的預選詞；選單只代填英文，允許自行修改，按比較按鈕才更新。中文提示僅協助選詞，不參與向量、翻譯擴查或計分。

2026/10/27：「比較兩個詞」另加 TF-IDF／Embedding 並排 XY 空間圖，保留原兩詞分數表、整體分析的熱圖與 45 詞對散點。兩張圖都使用固定十個參考詞與已提交詞 A／B 的去重聯集；只保留在兩空間都有有效向量的同一詞集，參考詞並非各自 Top 10 近鄰。A／B 用橘／藍色，其他參考詞為灰色；相同 A／B 合併為一個紫色點。缺少任一比較詞時不補造座標。更換詞需按「比較詞對」；更換上方 Embedding 模型會更新右圖，與相同詞集的 TF-IDF 圖保持對照。

投影只複製顯示詞的完整向量：TF-IDF 為文件 L2 後的 3,000 維詞欄，Embedding 為原始 100 維詞向量；各詞先 L2，再在各自空間以置中、無 whitening 的完整 SVD 做 PCA，固定主成分符號以利重現。沒有重訓、修改原矩陣或向量、建立全詞彙密集矩陣，亦不使用二維座標重算原始 cosine、近鄰或檢索排名。兩圖共用 XY 範圍，SVG 保持等比例座標，中文提示列出詞與座標；圖旁顯示原始 cosine 與兩主成分的變異保留比例。XY 主成分意義在兩空間不同，不能直接比較左右座標或以線段長度代替原始關聯；PCA 有資訊損失，換詞集會重新投影。資料、座標及方法收合呈現。此處詞向量 L2 與 RQ4 的文件 L2 實驗分開。

投影驗證：`.venv/Scripts/python.exe -B -X utf8 scripts/verify_association_projection.py --output reports/association-xy-20261027/numeric.json`。輸出不覆寫既有檔；以獨立 Gram 矩陣特徵分解核對四模型、固定詞對／自訂詞／相同詞共 32 個空間投影，核對原始 cosine、變異保留比例、逐次重現與缺向量處理，並記錄程式、語料與模型 manifest 指紋。既有模型及實驗 manifest 不改寫。

PCA 初版完成結果另存 `reports/association-xy-20261027/`：當時完整測試 **257 項通過**（投影與介面 16 項為其子集），32 個投影的 Gram 幾何最大誤差 8.22×10⁻¹⁵、cosine 最大誤差 4.44×10⁻¹⁶，重複輸出完全一致。另重跑六設定的 900,000 個 cosine、180,000 個 BM25、50 組文件 L2 等價及兩次實驗重現；93 個 HW2 保護指紋未變。原模型與 62 份既有 artifact 保留，原始 verification.json 已先備份，新驗證與 weak_rules run 另存。瀏覽器核對提交詞對、切換模型、相同詞集與寬窄排列，修正 HTML-only 容器清除 SVG 及重新載入時的舊類別快取問題。XY 僅為本機功能更新；尚未推送雲端部署分支。

2026/10/27 後續新增「XY 降維方式」PCA／t-SNE 切換，預設仍為 PCA。兩模式使用同一組有效詞、同一批原始模型與完整詞向量，保留既有 PCA 座標、原始 cosine 及其他圖表。t-SNE 直接使用各詞 L2 後的完整 3,000／100 維向量，不把 PCA 二維結果作為輸入。新依賴只安裝於 HW3：scikit-learn 1.9.1、threadpoolctl 3.7.0；版本寫入兩份 requirements，既有套件未升降版。

t-SNE 採 exact、Euclidean、random initialization、random_state=42、n_components=2、early_exaggeration=12、learning_rate=auto、max_iter=1000、n_iter_without_progress=300、min_grad_norm=1e-7、n_jobs=1，計算時限制為一個執行緒。約 10～12 詞，依使用者指定將網站預設改為 perplexity=5，收合設定保留 2／3／5；這是便於探索的小樣本設定，未宣稱最佳。有效詞集若縮小，實際值同步限制為至多 n−1，兩圖一致並記錄參數。完整模型保持唯讀，重新投影不等於重新訓練 Word2Vec。

t-SNE 以局部近鄰為主，群間距離、群大小、左右圖的線段長度與座標都不能當成原始關聯強弱或正確率。X／Y 僅為 t-SNE 座標，不稱作主成分；不提供 PCA 的變異保留比例。固定 seed 僅供在相同版本環境重現，不能證明群聚有效；換詞集、模型、perplexity 會改變排列，十詞結果僅作探索示意。圖旁保留原始 cosine，詳細設定列於收合區。optimizer_reported_kl 是套件回報的最佳化診斷值，不是正確率或資訊保留比例，也不跨空間選優；其回報時點可能在最後座標更新之前，驗證另計算輸出座標的 KL。

新增驗證以 `scripts/verify_association_projection.py --projection tsne --perplexity 3 --output <新的JSON路徑>` 執行。對四模型、兩組固定詞對、自訂 metformin 詞與相同詞，三種 perplexity 共核對 **96 個 t-SNE 投影**；另核對 **32 個 PCA 投影**。獨立熵二分搜尋核對高維鄰近機率，Student-t 機率核對輸出座標的 KL 目標，並檢查原始 cosine、相同詞集、有限座標與固定種子重現。全部通過：機率最大誤差 2.09×10⁻¹⁷、KL 目標最大誤差 3.89×10⁻¹⁶；完整測試 **264 項通過**（23 項投影／UI 為其子集）。結果、參數與來源 hash 另存 `reports/association-tsne-20261027/`，PCA 初版紀錄與舊模型 manifest 保留。本機功能已更新，尚未推送雲端分支。

方法來源：[scikit-learn TSNE 官方文件](https://scikit-learn.org/stable/modules/generated/sklearn.manifold.TSNE.html)、[van der Maaten 與 Hinton 原論文](https://www.jmlr.org/papers/v9/vandermaaten08a.html)、[原作者 FAQ](https://lvdmaaten.github.io/tsne/)。

TF-IDF 與 Embedding 分別用文章分布及上下文解釋。「找相關詞」的兩張長條圖與清單使用相同近鄰結果，送出不同詞後同步更新，cosine 軸固定 0–1；重複送出相同分析詞、模型、k 及成果版本會說明結果維持相同。表格「兩邊前 k 名都有／只在這邊前 k 名」是兩個前 k 名集合的比較，未入另一邊的前 k 名不代表該詞不存在或不相關。重疊定義與 CF／DF 留在明細。

「整體分析」保留並直接顯示兩張熱圖及 45 詞對散點圖，附讀圖說明；逐詞明細與原始分數可展開。這些圖使用固定十詞，不隨單詞或詞對輸入改變；更換模型會更新右邊的 Embedding 熱圖，散點仍同時顯示四組模型。全部圖表、近鄰、CSV 及摘要已更新為 C 重建結果，原 B 模型與 run 依使用者要求移除，不再提供版本切換。

此區先顯示四模型的平均 Top-10 重疊率（6%、5%、8%、21%）與有效分析詞數。此表固定使用每個分析詞的前 10 名，與互動顯示詞數分開；進階表仍可看指定 k 的重疊及 Spearman。以本次最高的 Skip-Gram 視窗 5 為例，21% 代表平均每十個近鄰約 2.1 個相同，表示部分重疊但整體不同，不能解讀成正確率或語意能力優劣。說明與結論從保存的 C 結果呈現，不重新計分或訓練。

熱圖提示為「詞 A／詞 B／cosine 相似度」。散點提示為「模型／詞對／詞對編號／TF-IDF 相似度／Embedding 相似度／共同出現摘要篇數」，四模型名稱以中文「視窗」顯示；詞對編號不是排名，共同出現篇數也不等於語意正確。只更改欄位標示及圖例文字，180 個點、原始分數、色階與原圖均保留。

頁面另列平均重疊率的三步算法：逐詞各取兩份 Top-10、計算共同詞數÷10，再對有效分析詞取平均。以保存的 Skip-Gram 視窗 5 結果為例，semaglutide 的共同詞只有 subcutaneous，該詞為 1÷10＝10%；十詞共同詞數依序為 1、2、0、2、2、3、0、3、3、5，平均為 21÷(10×10)＝21%。每個分析詞各自計數，不是將十詞共同詞去重後計算。明細可展開，缺向量者不當作 0% 納入平均，短清單的分母仍為請求 10。

散點圖前列出向右看文章分布、向上看上下文，以及相同詞對四模型共用 X 位置的讀法；圖後可切換兩組實例。semaglutide／liraglutide 的 X＝0.193423，四模型 Y 依序為 0.527409、0.448017、0.618126、0.759650，共現 155 篇；insulin／receptor 的 CBOW 視窗 2 座標為 (0.235051, 0.132613)，共現 430 篇。例表直接讀取保存的詞對原始分數，與 180 個點一致；切換不篩選或改變原圖。分數高低描述各自空間的接近程度，不是模型正確率。

## 固定資料與訓練

`data/corpus/glp1-3000-20261015` 經既有 `load_corpus` 逐檔核對 JSONL、selection、原始 XML SHA256、完整 manifest、PMID 唯一性／順序、英文非空摘要，實際 3,000 篇。語料 SHA256：`1166fc12efdabe5e9713e816d47e244b0b51ab19d7ba677f602d26c722f0f4c7`。snapshot.json 本身的 SHA256 另記於每模型 metadata。

文件採 HW2 的 PMID 字串升冪；篇內保留來源摘要區塊、句子與剩餘 token 順序，保存 document_order.json 與 sentences.jsonl。`english-rules-v1` 保護縮寫、小數、URL／DOI／email；context 不跨文件、摘要區塊或偵測句子。逐篇檢查句子 tokens 展平與整個摘要區塊直接 C 前處理完全一致，並核對與檢索引擎 C 相同。實際為 32,656 個非空句、539,158 tokens；全文 C 詞彙 31,662，四模型 min_count 後各 17,578。

固定停用詞表為 `resources/stopwords.json`（132 詞），SHA256：`d907482b2aabc0443ae05c95e0c9685ef6f8ff8789370a34c004a498d1abc406`。no、not、without 刻意保留；不 stemming、不展開複合詞。停用詞先從摘要及訓練序列移除，再建立 TF-IDF 和四組模型，並非只篩選顯示。若句子移除後為空則略過；window 按留下的詞計算，故原始文字中相隔較遠的詞可能在移除後進入同一窗口。

四組只有 sg 與 window 不同，各自建立新的 Word2Vec 再 build_vocab／train，沒有讀取任何舊權重：

| 參數 | 設定 |
|---|---|
| 架構／窗口 | CBOW w2、CBOW w5、Skip-Gram w2、Skip-Gram w5 |
| vector_size／epochs／min_count | 100／30／2 |
| negative／sample／seed／workers | 5／0.001／42／1 |
| alpha／min_alpha | 0.025／0.0001 |
| cbow_mean／ns_exponent | 1／0.75 |
| shrink_windows／sorted_vocab | True／1 |
| hs／batch_words／null_word | 0／10000／0 |
| max_vocab_size／max_final_vocab | None／None |
| 初始化 hashfxn | SHA256 前 8 bytes little endian，沿用 HW2 |

參考來源為 HW2 embeddings.py、embedding_experiment.py、word_embedding/summary.json 與實際模型 metadata；來源指紋及原設定在 `reports/word-association-20261024/hw2-reference.json`。程式只匯入 HW3 自己的模組，執行時不讀 HW2。

Gensim 4.4.0、NumPy 2.5.4、SciPy 1.18.1、Python 3.12.14。每個模型保存新初始化向量指紋、完整模型、詞序／CF、原始 vectors.npy、30 epochs loss 與時間、有效／原始訓練 token 次數、版本與所有來源指紋。loss 是 Gensim 單次 train 的累積差值，浮點累積可能失去精度，不能當語意正確率或架構比較依據。

## TF-IDF：先文件正規化，再比較詞欄

只用摘要、C 前處理；移除固定停用詞、不 stemming、不展開搜尋複合詞。重新計算 3,000 篇的文件 TF、CF、DF、IDF 與 norm。完整詞表建立稀疏矩陣 A（3000×31662）：

`A[d,t] = TF(d,t) × log10(3000/DF(t))`

先令 `r[d] = sqrt(sum_t A[d,t]^2)`，再用 `A[d,t]/r[d]`（零列保持零）。固定完整詞彙空間計算 r，不受選詞、min_count 候選池、畫面篩選影響。詞 t 的向量是正規化後的完整文件欄 `u(t)=A[:,t]`，維度 3000，最後計算兩欄 cosine。Word2Vec 用原始 100 維詞向量在自己的空間計算 cosine；不同維度不互算、不相減，也不使用二維投影代替。

若不做文件 L2，每個詞欄乘正的固定 IDF 後，`cos(cu,dv)=cos(u,v)`，因此欄 cosine 與純 TF 相同；零 IDF／零欄不適用。本方法的 IDF 影響透過完整文件 norm 間接改變各文件座標。這個性質及計算順序由小型手算測試核對。

## 公平比較及邊界

固定十詞為 semaglutide、liraglutide、dulaglutide、tirzepatide、insulin、glucose、obesity、diabetes、receptor、glp-1。本次十詞在五種空間全部有效，無缺詞或零向量；完整狀態、CF／DF 保存於 term_status.csv。

共同候選池取四模型詞彙與 TF-IDF 非零欄交集，排序保存，共 17,578 詞。所有方法使用相同 C 前處理及 min_count=2 所得門檻，不在顯示階段事後篩選數字、一般詞或共同近鄰。Top-k 搜尋整個池，排除自身，所有方法只返回正 cosine；零分不補足，返回不足 k 明列。詞對、熱圖、散點保留負 cosine，沒有截成零。ties 先按 12 位小數分數降冪，再依 Unicode 詞典序；CSV 保留原始精度。

重疊率＝兩個 Top-k 詞集合交集數／請求 k，k=5／10／20；即使返回不足 k，分母不變。anchor 缺失或零向量為 NA，不當作零重疊；平均明列實際有效分析詞數。本次全部 10 詞有效且每方法均足額返回。

十詞固定順序取 combinations，形成 45 個不重複詞對，無對角線或反向重複。Spearman 使用完全相同詞對順序、共同有限值及平均 ties ranks；少於 2 對或常數陣列為 NA。沒有以 p 值宣稱顯著，因詞對共享詞彙。兩種一致指標均不是語意正確率。

## 結果與解釋

| 模型 | 平均 Top-10 重疊 | 45 詞對 Spearman |
|---|---:|---:|
| CBOW w2 | 6% | 0.3116 |
| CBOW w5 | 5% | 0.4387 |
| Skip-Gram w2 | 8% | 0.4095 |
| Skip-Gram w5 | 21% | 0.5159 |

兩種關係有局部一致，但整體近鄰集合差異很大。這次 Skip-Gram w5 與 TF-IDF 的一致程度最高；這只描述單次 seed 下的一致度，不能推論語意較好或普遍優於其他架構。

例如 liraglutide／tirzepatide 在 85 篇共同出現，C 的 TF-IDF=0.1354，CBOW w2=0.6201：同一治療領域的藥物可能有相近的句內使用情境，卻分布在不同藥物研究文件。這是上下文解釋的合理推測，沒有逐句人工 gold 判定。semaglutide／liraglutide 的 TF-IDF=0.1934，四模型依序為 0.5274、0.4480、0.6181、0.7596；各方法有不同分數分布，不能以絕對大小判定優劣。

insulin／glucose 的 TF-IDF=0.3483，四模型依序為 0.2198、0.2316、0.4007、0.4464。receptor／glp-1 的 TF-IDF=0.5291，四模型依序為 0.4698、0.2727、0.5855、0.6842；架構與窗口改變會影響特定詞對，不能只看一個群或平均分數。

窗口差異也不是同方向：CBOW w2→w5 的 Spearman 由 0.3116 升為 0.4387，但 Top-10 重疊由 6% 降到 5%；Skip-Gram w2→w5 的兩項指標則由 0.4095／8% 升為 0.5159／21%。這是本次 C 單次訓練的觀察，不能直接解讀成一般化的語意能力改善。

C 已移除固定停用詞，semaglutide 的 TF-IDF 前三為 oral、agonist、weight；CBOW w2 前三為 dulaglutide、metformin、liraglutide。Top-10 中仍可能出現數字（如 2）或縮寫，因為它們不在停用詞表內；不能為了讓結果看起來較好而事後刪掉。低頻詞與少量文件共現仍可能使近鄰不穩定，完整十詞及 45 對保留在主報告。

## 限制及驗證

GLP-1 單一主題摘要不是隨機語料；低頻詞、規則式句界及單次 seed 限制穩定性與一般化。四模型各只訓練一次；不能據此宣稱架構普遍最佳，也不能把舊 1,000 篇模型差異全部歸因於語料增加。

正式訓練與單元測試分離。小型測試涵蓋詞欄手算、完整文件 L2、IDF 抵消、固定池、自己排除、ties、OOV／零向量、負分、缺值／常數 Spearman、短 Top-k、句界／順序、新初始化／保存／新程序重載及檔案損毀拒絕。介面測試阻止 train／Engine.rank，驗證切換、表單、圖表及側欄獨立。

離線驗證重建實際 C TF／CF／DF、完整稀疏 TF-IDF、全部 45 詞對，以及每方法 15 個詞的 Top-20，並以 NumPy／SciPy 獨立核對。同時檢查與檢索 C 相同、全部詞表及訓練序列不含停用詞，並驗證四組完整模型離線重載、參數、CF 及 62 份成果檔案 hash。矩陣最大誤差為 0，詞對為 2.78×10⁻¹⁶，近鄰為 2.22×10⁻¹⁶。結果與誤差保存於 `reports/association-c-20261024/numeric.json`；訓練程式及停用詞表凍結於新 run 的 sources。

重現指令、UI 操作與成果位置見 [README](../README.md)。本次完整測試 236 項通過，涵蓋新增的 C 前處理及 UI 停用詞檢查；另外的 27 項單元測試和 6 項 UI 測試屬同一套測試的子集，不能相加當成不同測試。依 AGENTS.md 重跑檢索數值驗證，六設定共核對 900,000 個 cosine 與 180,000 個 BM25 分數，最大誤差分別為 1.11×10⁻¹⁶ 與 0；93 份 HW2 保護指紋未變。前次 verification.json 另存於 `reports/verification.before-association-c-20261024.json`，新實驗各存獨立 run，沒有覆寫原人工標註與檢索歷史實驗。
