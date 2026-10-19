# 生醫資訊檢索第三次作業報告

## 摘要

本研究以固定的 3,000 篇 GLP-1 英文 PubMed 摘要，實作原始 TF、Log TF、IDF-only、TF-IDF 與 Log TF-IDF 的向量空間檢索，固定前處理與 IDF 定義，比較十個查詢的排名及評估指標。相關集合採用 PubMed 主題資料與摘要 weak rule 建立的自動參考標籤，未進行獨立人工相關性驗證。

在 C 前處理、標準 IDF、cosine 與 k=10 下，IDF-only 與 Log TF-IDF 的平均 P@10 同為 0.9400；Log TF-IDF 的平均 nDCG@10 為 0.9541，TF-IDF 與 Log TF-IDF 的 MRR 均為 1.0000。這些數字衡量對規則參考集合的符合程度。純 weak rule 對照下 nDCG@10 最佳方法改為 TF-IDF，顯示方法結論受到標籤來源影響，不能據此宣稱任一 weighting 普遍最佳。

報告日期為 2026/10/16；作業截止日期為 2026/10/27。

## 1 研究目的與作業範圍

本作業探討詞頻、文件頻率與向量長度如何影響搜尋排名，並用可重現的實驗回答 RQ1～RQ5。原題任務五允許在缺乏既有相關性標籤時，根據文件主題標籤或人工判讀建立簡單相關集合並說明限制。本研究採自動主題參考方案；摘要 weak rule 是額外的詞彙代理判準，於方法與限制中單獨揭露，沒有將其視為人工真值。

系統維持四頁：語料與設定、搜尋與排名、方法比較、效能評估。文件以 PMID 識別，僅摘要正文參與計分，標題供閱讀。介面提供前十名及分數、摘要命中高亮、逐詞權重貢獻、來源分流、實驗保存與歷史查核。HW3 使用獨立環境；HW2 原始成品維持唯讀。

## 2 固定語料與前處理

語料保留原 1,000 篇，於 2026/10/15 以相同 PubMed 搜尋條件增加 2,000 篇，限制英文、非空摘要與 PMID 去重。出版日期搜尋截止仍為 2026/09/29。新增階段取得 2,100 筆原始紀錄，排除 11 筆書籍類紀錄及 15 筆空摘要，另有 74 筆合格但未納入。這是保留舊快照後的擴充聯集，不是隨機樣本，也不是當日查詢純粹的前 3,000 名。原始 XML、搜尋回應、排除理由及 SHA256 均保存。

PubMed 出版日期搜尋涵蓋電子與紙本日期。快照中兩筆期刊卷期年份為 2027、電子出版日期在查詢期間內；文件年份保留卷期年份，不以該欄另做人工日期篩選。

```text
("GLP-1"[Title/Abstract] OR "glucagon-like peptide-1"[Title/Abstract]) AND english[Language] AND hasabstract AND ("1900/01/01"[Date - Publication] : "2026/09/29"[Date - Publication])
```

本實驗共 3,000 篇，C 前處理後有 539,158 個 tokens、31,662 個不同詞項。支援 B（切詞與文字正規化）、C（B 加停用詞移除）、D（C 加 Porter）；本文實驗全部固定 C。DF 是包含詞項的文件數，CF 是全語料出現次數，TF 是單篇文件或單一查詢的實際次數，三者不混用。

## 3 向量權重與控制條件

令 f 為某詞在文件或查詢中的次數，N=3,000，DF(t) 為包含 t 的文件數。f=0 時以下權重皆為零；f>0 時：

| 方法 | 權重 |
| --- | --- |
| 原始 TF | f |
| Log TF | 1 + ln(f) |
| IDF-only | IDF(t)，只記出現，不使用重複次數 |
| TF-IDF | f × IDF(t) |
| Log TF-IDF | (1 + ln(f)) × IDF(t) |

標準 IDF 為 `ln(N / DF)`；平滑選項為 `ln((N+1)/(DF+1)) + 1`。本文使用標準式，沒有將平滑 IDF 或 B／D 設定的效果混入五方法比較。

文件與查詢使用同一詞彙空間、前處理、IDF 及 weighting；查詢重複詞保留實際 TF，OOV 不加入向量與 norm。分數為 `cos(q,d) = Σt w(t,q)w(t,d) / (||q||₂ ||d||₂)`；文件 norm 使用完整文件向量，不只計算命中詞。空白、全停用詞、全 OOV 或零向量安全返回無結果，不以零分文件湊滿十篇。

固定條件為同一語料、十查詢、同一參考標籤、C、標準 IDF、cosine 與 k=10。唯一主要比較因素為 weighting。排序先依分數取 12 位小數降序，再依數字 PMID 升序處理同分；畫面顯示 6 位小數，CSV 保存原始精度。不同方法的分數尺度不能直接當作相關性強弱或正確率比較。

## 4 查詢與自動參考標籤

### 4.1 十個資訊需求

| 查詢 | 搜尋文字 | 資訊需求 |
| --- | --- | --- |
| Q01 | semaglutide weight loss obesity | Semaglutide 與肥胖或減重 |
| Q02 | liraglutide obesity treatment | Liraglutide 與肥胖治療 |
| Q03 | tirzepatide type 2 diabetes glycemic control | Tirzepatide 與糖尿病血糖控制 |
| Q04 | GLP-1 cardiovascular outcomes heart failure | GLP-1 與心血管或心衰竭結果 |
| Q05 | GLP-1 kidney disease renal protection | GLP-1 與腎臟保護 |
| Q06 | GLP-1 gastric emptying gastrointestinal motility | GLP-1 與胃排空或腸胃蠕動 |
| Q07 | GLP-1 nausea vomiting adverse effects | GLP-1 與噁心或嘔吐不良反應 |
| Q08 | GLP-1 insulin secretion pancreatic beta cells | GLP-1 與胰島素分泌或胰島細胞 |
| Q09 | GLP-1 gut microbiota intestinal metabolism | GLP-1 與腸道菌相 |
| Q10 | GLP-1 neuroprotection Alzheimer Parkinson disease | GLP-1 與神經保護或神經退化疾病 |

研究範圍不額外排除人體、動物或細胞研究；自動規則沒有逐篇確認研究類型、設計或臨床適用性。全文也沒有納入計分或相關性裁決。

### 4.2 PubMed 主題依據

從每篇保存的 exact raw_path XML 依 PMID 抽取 MeSH DescriptorName、ChemicalList 的 NameOfSubstance、SupplMeshName 與 Keyword，並核對原始 XML SHA256。MeSH UI、主題重要性標記、qualifier、文章類型及標引狀態供追溯；qualifier 和文章類型不獨立參與概念命中，MajorTopic 不自動轉成高度相關。MeSH 與關鍵字的欄位意義依 [NLM PubMed 說明](https://pubmed.ncbi.nlm.nih.gov/help/#mesh-terms-mh)，查詢與標籤的對應則是本專案規則，並非 NLM 的查詢答案。MeSH 也不能一律稱為人工專家標註。

每個查詢有兩組概念；組內採 OR、組間採 AND。同一文章允許分別從不同主題欄位支持兩組概念，全部命中時給 grade=1、來源 pubmed_metadata。字串採 NFKC、casefold、標點與連字號轉空白後的完整詞序列比對，不做 MeSH 階層展開、線上翻譯或隱含同義詞推理。Q04～Q10 的共享概念組明列 GLP-1、受體／致效劑及若干藥名，不包含單獨 glucagon 或 GLP-2。完整固定別名列於附錄 A。

### 4.3 摘要 weak rule 回退

當主題欄位完全缺少，或存在但不足以支持該查詢全部概念組時，獨立套用摘要 weak rule。回退不將部分主題命中與部分摘要命中拼成正例；摘要本身須支持全部概念組才為 1，否則為 0。規則直接檢查正規化原摘要，不使用檢索的停用詞設定、Porter、TF、DF、分數或排名。英文 casefold，少數彎引號／連字號統一，完整詞／詞組邊界匹配；僅 neuroprotect 與 neurodegenerat 允許已明列的字尾延伸。

| 查詢 | 摘要概念組一 | 摘要概念組二 任一詞 |
| --- | --- | --- |
| Q01 | semaglutide | weight loss、weight reduction、obesity、obese |
| Q02 | liraglutide | obesity、obese、weight loss |
| Q03 | tirzepatide | diabetes、diabetic、glycemic、glycaemic |
| Q04 | G | cardiovascular、heart failure、cardiac |
| Q05 | G | kidney、renal、nephropathy |
| Q06 | G | gastric emptying、gastrointestinal motility、gastric motility、gastroparesis |
| Q07 | G | nausea、vomiting |
| Q08 | G | insulin secretion、insulin release、beta-cell、beta cell、β-cell、β cell |
| Q09 | G | microbiota、microbiome |
| Q10 | G | neuroprotect*、alzheimer、parkinson、neurodegenerat* |

上表的 G 指 `glp-1`、`glucagon-like peptide-1`、`glucagon-like peptide 1`。weak rule 的 G 不會因只出現 semaglutide 等藥名就自動成立，與較寬的 metadata 別名組不同。`*` 是對該兩個指定前綴的說明符號，不是所有詞都做詞幹擴展。

例如 Q01 必須同時出現 semaglutide，以及 weight loss／weight reduction／obesity／obese 中至少一詞。這是詞面共現，不保證主要研究問題是 semaglutide 減重。系統逐筆保存來源、命中詞、metadata 證據、回退原因及原 weak_rule_grade；0 表示規則證據不足，不能稱為人工確認不相關。全程只產生自動二元 0／1，沒有自動等級 2，也沒有新增人工判讀。

### 4.4 實際涵蓋與標籤來源

| 主題欄位 | 有該欄位的篇數 |
| --- | --- |
| MeSH | 1672 |
| 藥物／化學物質 | 1547 |
| 補充概念 | 27 |
| 關鍵字 | 2551 |
| 任一主題欄位 | 2846 |

各欄位篇數可重疊。有任何主題資料的 2,846 篇不代表對每個查詢都有足夠依據；完全沒有主題資料的文章為 154 篇。以下以「查詢－文章」為單位，不能解讀成互不重複的文章數：

| 查詢 | metadata 正例 | weak 回退筆數 | 回退正例 | 參考正例總數 | 較純 weak 新增正例 |
| --- | --- | --- | --- | --- | --- |
| Q01 | 288 | 2712 | 245 | 533 | 52 |
| Q02 | 79 | 2921 | 92 | 171 | 20 |
| Q03 | 139 | 2861 | 143 | 282 | 23 |
| Q04 | 288 | 2712 | 482 | 770 | 46 |
| Q05 | 150 | 2850 | 316 | 466 | 21 |
| Q06 | 30 | 2970 | 77 | 107 | 4 |
| Q07 | 9 | 2991 | 92 | 101 | 0 |
| Q08 | 35 | 2965 | 95 | 130 | 11 |
| Q09 | 49 | 2951 | 114 | 163 | 3 |
| Q10 | 74 | 2926 | 84 | 158 | 4 |

總計 30,000 組中，1,141 組由 metadata 給正例，28,859 組（96.2%）走摘要回退；其中 1,740 組為回退正例。參考正例合計 2,881 組，回退正例占 60.4%。metadata 比純 weak 多 184 組正例。

每個查詢都有 3,000 筆自動結果。沒有主題欄位造成的回退每查詢均為 154 筆，其餘回退是概念支持不足。人工標註完成數為 0；30,000 筆規則結果與人工判讀進度完全不同。

## 5 評估方法

令 Rq 為參考標籤為 1 的文件集合，Top10 為前十名；相關一詞在本節僅指此自動參考。P@10=`|Top10 ∩ Rq|/10`，即使結果不足十篇分母仍固定為十。參考 Recall@10=`|Top10 ∩ Rq|/|Rq|`，分母不是已完整人工判讀的真實相關集合。

每查詢 RR 為完整非零返回排名中第一個參考正例的倒數名次，沒有正例則為零；MRR 為十查詢 RR 平均，不限於前十名。DCG@10 使用 `Σi (2^grade_i−1)/log₂(i+1)`，nDCG 為 DCG 除以依全部參考標籤排出的 IDCG；目前 grade 只有 0／1，故是二元 nDCG，沒有利用人工相關程度。評估依資訊需求與相關集合進行，與單純包含查詢詞不同，見 [IR 評估原理](https://nlp.stanford.edu/IR-book/html/htmledition/information-retrieval-system-evaluation-1.html)與[排名評估](https://nlp.stanford.edu/IR-book/html/htmledition/evaluation-of-ranked-retrieval-results-1.html)。

平均採查詢等權的 macro mean；每查詢至少有一個參考正例才納入。本文固定十查詢全部有正例，因此實際納入 10／10、排除 0，沒有以少數查詢冒充全部。judged@10 均為 1，只表示前十名都有自動規則結果，不表示人工覆蓋率為 100%。50 組結果的完整指標見附錄 B。

## 6 實驗結果

### 6.1 五方法平均

| 方法 | P@10 | 參考 Recall@10 | MRR | 二元 nDCG@10 |
| --- | --- | --- | --- | --- |
| 原始 TF | 0.6700 | 0.0322 | 0.8750 | 0.6953 |
| Log TF | 0.8100 | 0.0423 | 0.9500 | 0.8327 |
| 僅 IDF | 0.9400 | 0.0503 | 0.9500 | 0.9407 |
| TF × IDF | 0.9300 | 0.0499 | 1.0000 | 0.9486 |
| Log TF × IDF | 0.9400 | 0.0509 | 1.0000 | 0.9541 |

Log TF-IDF 與 IDF-only 的 P@10 並列最高；Log TF-IDF 的參考 Recall@10 與 nDCG@10 最高；TF-IDF、Log TF-IDF 的 MRR 均為 1。原始 TF 的平均 nDCG@10 為 0.6953，改 Log TF 後為 0.8327。不同指標各自比較，不相加或疊加。

Recall@10 約 0.03～0.05 不代表程式漏掉 95% 的真實相關文章：每查詢參考正例有 101～770 筆，前十名最多只取十筆。且 macro Recall 先按每查詢的不同分母計算，再平均，不能由平均 P@10 直接換算。

### 6.2 逐查詢 P@10 與 nDCG@10

逐查詢 P@10：

| 查詢 | 原始 TF | Log TF | 僅 IDF | TF × IDF | Log TF × IDF |
| --- | --- | --- | --- | --- | --- |
| Q01 | 0.70 | 0.70 | 1.00 | 0.90 | 1.00 |
| Q02 | 0.40 | 0.80 | 0.80 | 0.70 | 0.70 |
| Q03 | 0.60 | 0.80 | 0.90 | 1.00 | 0.80 |
| Q04 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q05 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q06 | 0.90 | 0.90 | 1.00 | 1.00 | 1.00 |
| Q07 | 0.10 | 0.70 | 1.00 | 1.00 | 1.00 |
| Q08 | 0.80 | 0.70 | 0.70 | 0.70 | 0.90 |
| Q09 | 0.90 | 1.00 | 1.00 | 1.00 | 1.00 |
| Q10 | 0.30 | 0.50 | 1.00 | 1.00 | 1.00 |

逐查詢 nDCG@10：

| 查詢 | 原始 TF | Log TF | 僅 IDF | TF × IDF | Log TF × IDF |
| --- | --- | --- | --- | --- | --- |
| Q01 | 0.7421 | 0.7682 | 1.0000 | 0.9216 | 1.0000 |
| Q02 | 0.4780 | 0.8630 | 0.7163 | 0.7917 | 0.7632 |
| Q03 | 0.5658 | 0.8522 | 0.8900 | 1.0000 | 0.8630 |
| Q04 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| Q05 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| Q06 | 0.9216 | 0.9216 | 1.0000 | 1.0000 | 1.0000 |
| Q07 | 0.2201 | 0.7100 | 1.0000 | 1.0000 | 1.0000 |
| Q08 | 0.8365 | 0.7313 | 0.8007 | 0.7728 | 0.9149 |
| Q09 | 0.9306 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| Q10 | 0.2583 | 0.4807 | 1.0000 | 1.0000 | 1.0000 |

Q04、Q05 五方法的前十名都符合參考集合，故目前指標無法區分它們的前十名品質；這不是五種排序相同，也不是已確認十篇都回答醫學問題。Q02 的 Log TF nDCG@10=0.8630，高於 TF-IDF 的 0.7917 與 Log TF-IDF 的 0.7632。Q03 的 TF-IDF P@10=1.00，高於 Log TF-IDF 的 0.80；Q08 則 Log TF-IDF P@10=0.90，高於 TF-IDF 的 0.70。這些反例說明總平均不能代替逐查詢分析。

### 6.3 標籤來源敏感度

| 方法 | 混合 P@10 | 純 weak P@10 | 混合 nDCG@10 | 純 weak nDCG@10 |
| --- | --- | --- | --- | --- |
| 原始 TF | 0.6700 | 0.6700 | 0.6953 | 0.6953 |
| Log TF | 0.8100 | 0.8000 | 0.8327 | 0.8188 |
| 僅 IDF | 0.9400 | 0.9100 | 0.9407 | 0.8857 |
| TF × IDF | 0.9300 | 0.9000 | 0.9486 | 0.9046 |
| Log TF × IDF | 0.9400 | 0.9000 | 0.9541 | 0.8927 |

此表固定完整排名、查詢、語料、程式與設定，只改評估參考來源，故是標籤敏感度分析，不是搜尋演算法改善實驗。混合規則較純 weak rule 多 184 組正例，且不移除原 weak 正例；五方法的排名檔逐位元相同。所有查詢正例均超過十筆，二元 IDCG@10 不變，新增命中的參考正例即可提高 P@10／nDCG@10，不能將分數增加解讀為更接近人工真值。Recall 則還會受到正例分母增加的影響。

純 weak 下 nDCG@10 最高為 TF-IDF 0.9046，混合來源最高為 Log TF-IDF 0.9541。此改變是來源敏感性的實證，不能反過來證明任何一套標籤比較正確。

## 7 RQ1～RQ5 實驗結論

### RQ1 原始 TF 與 Log TF 如何影響權重

原始 TF 隨出現次數線性增加，Log TF 在 f>0 時以 1+ln(f) 壓縮重複。以 Q01 的 TF-IDF 第一名 PMID 42105046 為例，文件標題為「Semaglutide and Cardiovascular Outcomes in People with Type 2 Diabetes: A SUSTAIN-6 Post Hoc Analysis by Weight Loss Category.」。其實際摘要詞項如下：

| 詞項 | 文件 TF | Log TF | DF | 標準 IDF | TF-IDF | cosine 貢獻 |
| --- | --- | --- | --- | --- | --- | --- |
| loss | 21 | 4.0445 | 854 | 1.2564 | 26.3852 | 0.202359 |
| obesity | 0 | 0.0000 | 1307 | 0.8309 | 0.0000 | 0.000000 |
| semaglutide | 6 | 2.7918 | 708 | 1.4439 | 8.6635 | 0.076359 |
| weight | 11 | 3.3979 | 1195 | 0.9205 | 10.1251 | 0.056889 |

loss 與 semaglutide 的原始 TF 比值為 21/6=3.50，Log TF 比值約為 1.45；重複較多的 loss 因此不再保有原來的相對倍數。權重壓縮不保證每篇分數都下降或每個查詢改善，因為 cosine 的分子與完整文件 norm 都會改變。

實驗上 TF 改 Log TF，平均 P@10 從 0.67 升至 0.81、nDCG@10 從 0.6953 升至 0.8327；但 Q08 的 P@10 從 0.80 降到 0.70。結論是壓縮重複在此參考集合的平均表現有利，並非對所有查詢皆有利。

### RQ2 IDF 為何能降低常見詞的重要性

在固定 N 下，標準 IDF=ln(N/DF)，DF 越大，單詞權重越低。高文件頻率表示區辨文件的能力較弱，不代表該詞在醫學上不重要。以實際集合統計代入：

| 詞項 | CF | DF | 標準 IDF | 平滑 IDF 公式代入 |
| --- | --- | --- | --- | --- |
| glp-1 | 5493 | 1783 | 0.5203 | 1.5201 |
| weight | 3120 | 1195 | 0.9205 | 1.9200 |
| semaglutide | 2107 | 708 | 1.4439 | 2.4428 |

上表的平滑值僅為同一 DF 的公式代入，沒有新增平滑 IDF 排名實驗。當 DF=N 時，標準 IDF 為零，平滑式為一。文件與查詢都使用 IDF 時，未正規化點積中的單詞乘積含 IDF²，最後仍由兩向量 norm 調整；不能只看單詞 IDF 就斷言最終排名。

相同原始 TF 下，加入 IDF 後本實驗平均 P@10 從 0.67（TF）到 0.93（TF-IDF）、nDCG@10 從 0.6953 到 0.9486。這支持 IDF 在此控制設定與規則參考下有助平均排序，不能延伸成臨床重要性或所有語料的結論。

### RQ3 TF-IDF 相較 TF-only 與 IDF-only 的排名表現

TF-IDF 結合重複次數與集合區辨力；IDF-only 忽略文件內重複。TF-IDF 的平均 P@10=0.93，低於 IDF-only 的 0.94，但 nDCG@10=0.9486，高於 IDF-only 的 0.9407，MRR 也由 0.95 提升為 1.00。因此不能只憑單一指標宣稱 TF-IDF 勝出。

以固定 Q01 的實際 Top 10 比較：

| 名次 | 原始 TF | Log TF | 僅 IDF | TF × IDF | Log TF × IDF |
| --- | --- | --- | --- | --- | --- |
| 1 | 42105046 | 42507673 | 42624784 | 42105046 | 42507673 |
| 2 | 42824923 | 42824923 | 42695140 | 42518911 | 42536519 |
| 3 | 42220241 | 41759565 | 42647098 | 42536519 | 41759565 |
| 4 | 42518911 | 42220241 | 41936548 | 42824923 | 42624784 |
| 5 | 42507673 | 41884974 | 42091772 | 42507673 | 42824923 |
| 6 | 42296333 | 42002672 | 42423951 | 42220241 | 42105046 |
| 7 | 41872986 | 42676263 | 42866773 | 41872986 | 42518911 |
| 8 | 39724554 | 42297751 | 42507673 | 42023428 | 41936548 |
| 9 | 41884974 | 42518911 | 42696191 | 41884974 | 41884974 |
| 10 | 41759565 | 42128481 | 38757954 | 42225300 | 42866773 |

各欄為 PMID，由上而下表示該方法的名次；不在某欄不代表整份排名未檢出。Q01 的 TF P@10=0.70、TF-IDF=0.90、IDF-only=1.00；三者 nDCG@10 分別為 0.7421、0.9216、1.0000。TF 與 TF-IDF 第一名相同，但後續文件不同；Log TF 和 Log TF-IDF 第一名為 PMID 42507673，IDF-only 第一名為 PMID 42624784。

Q01 TF-IDF 十篇的分數、標題與參考來源列於附錄 C。以上是可查核的排名差異與規則符合程度，不是逐篇人工內容評鑑。

### RQ4 L2 normalization 前後有何差異

對非零向量，令 q̂=q/||q||₂、d̂=d/||d||₂，則 `cos(q,d)=q̂·d̂=cos(q̂,d̂)`。標準 cosine 本來就除以向量長度，顯式 L2 前後應理論等價。固定五方法、十查詢的 50 組檢查全部排名一致，最大分數差為 1.110223024625157e-16，屬浮點運算差異。這不是 L2 沒有作用，而是比較的兩邊已經具有相同長度校正。

另外以 Q01、TF-IDF 比較 raw dot 與 normalized dot，選兩種排序各前三名聯集作補充：

| PMID | C tokens | 文件 norm | raw dot 名次 | raw dot | cosine 名次 | cosine／normalized dot |
| --- | --- | --- | --- | --- | --- | --- |
| 42105046 | 222 | 71.8335 | 1 | 54.9806 | 1 | 0.335608 |
| 40580049 | 451 | 111.0742 | 2 | 44.7364 | 14 | 0.176603 |
| 41872986 | 225 | 79.9596 | 3 | 38.3367 | 7 | 0.210229 |
| 42518911 | 208 | 55.6540 | 10 | 29.9748 | 2 | 0.236161 |
| 42536519 | 235 | 56.5596 | 9 | 30.1075 | 3 | 0.233409 |

raw dot 沒有除以 norm，normalized dot 等於 cosine；兩者是不同 scoring，分數尺度不可直接比較。表中 token 數與 norm 顯示文件長度及權重組成不同；這個例子不能單獨分離字數與詞項分布的因果效果，也不把 raw dot 當作第六種 weighting 納入主要品質比較。

### RQ5 不同 weighting 對評估指標有何影響

本參考集合中，原始 TF 平均落後其餘四法；Log TF 改善平均表現但仍有查詢退步；IDF-only 即使不使用重複次數，P@10 仍與 Log TF-IDF 並列最高。TF-IDF 與 Log TF-IDF 皆讓每個查詢的第一名符合參考標籤，所以 MRR=1，而 nDCG@10 與 P@10 仍會因後續排名不同而有差異。

Log TF-IDF 平均 nDCG@10 比 TF-IDF 高約 0.0055，但 TF-IDF 在 Q03 較好，且來源敏感度對照的勝者會改變。本研究只有十個固定查詢，沒有顯著性檢定或獨立人工效度證據，故此差距僅作描述性結果。若使用情境重視前十名比例、第一個可用結果或整體前十排序，應分別看 P@10、MRR、nDCG；不能只選對某方法最有利的指標。這些適用性判斷限於本資料與規則代理任務。

## 8 偏差與限制

1. **詞彙共同訊號。** weak rule 與五種詞項檢索方法共享字詞訊號，容易偏好明列詞表的文件。標籤不讀排名可避免直接由排名反推答案，仍不能消除參考標準對詞彙搜尋的偏向。所有比較法都是詞彙向量法，結果不能推論到其他檢索家族。
2. **主題共現不等於資訊需求成立。** 背景提及、不同藥物與不同終點同時出現、研究計畫或次要討論都可能命中；系統沒有抽取關係或判定研究焦點。負面療效研究本身仍可能與查詢相關，不應將「沒有效果」一概當作不相關。Q03 的糖尿病標籤不保證第二型或血糖控制，Q04／Q05 的疾病與器官詞不證實保護效果。
3. **有限詞表造成漏判。** 同義詞、變形、縮寫與隱含概念未必涵蓋；完整邊界與 metadata 正規化也無法取代語義理解。缺少標引不代表不相關，weak 0 也不是人工負例。
4. **欄位來源不均。** MeSH、化學物質、補充概念與作者／供應者關鍵字的完整性與產生方式不同，不能把全部 metadata 一律稱為人工專家判讀。主題欄位 94.9% 的篇數涵蓋，不等於任一查詢有相同比例的有效相關性證據。
5. **混合來源與二元標籤。** 正例多數來自 weak 回退；兩類正例聯集可能增加指標，並不等於標籤更準確。二元 nDCG 不能反映高度與部分相關的差異，judged@10=1 也不是人工驗證。
6. **語料、查詢與摘要範圍。** 單一 GLP-1 主題、保留舊資料的非隨機擴充、十個固定查詢與摘要正文限制外推；不能視為完整 PubMed 或全文檢索表現。未讀取全文確認研究設計或療效。
7. **Recall 與人工驗證。** 全 30,000 組都執行過規則，只能證明規則覆蓋完整，不能證明真實相關集合完整。本報告沒有獨立人工驗證。人工候選池五方法各 Top 20 聯集仍可供未來查核，但未在本研究當作人工答案；若之後判讀候選池，須保留池外補查與 pooling bias 的說明。

## 9 重現與可靠性

### 9.1 本報告引用的實驗

| 用途 | 來源 | run_id | manifest SHA256 |
| --- | --- | --- | --- |
| 主要混合實驗 | pubmed_hybrid | 20261015T160809.127489Z-ec128a40 | 5eeced0470f603a048c84e8e346168b41a33a86b6a597ce50a6b7e05d185ec78 |
| 獨立重複 | pubmed_hybrid | 20261015T160952.886717Z-7af39e77 | 99a655036952b0fb8f5f396bb04c91dbe55563542a746e7107f1d30f17919664 |
| 同排名純 weak 對照 | weak_rules | 20261015T161051.047726Z-edba86a5 | 92672614984540ac17d63f21eb2a8dc1b93d6103bfe7979c44789155e1f2b470 |

主實驗與重複實驗的 15 個輸出逐位元一致。純 weak 對照與主實驗使用相同語料、查詢、程式、weighting、設定與完整排名，只有參考標籤不同。原 run 保持不變，文件更新不回寫其 manifest。每個 manifest 保存當時程式、規則、資料、環境與輸出 hash；資料指紋的 canonical JSON 與檔案位元組 SHA256 定義不同，不能混用。

| 內容 | 指紋定義 | SHA256 |
| --- | --- | --- |
| 語料 abstracts.jsonl | 檔案位元組 | 1166fc12efdabe5e9713e816d47e244b0b51ab19d7ba677f602d26c722f0f4c7 |
| 查詢 | canonical JSON | 9bd41035cfb0944ee65171f47575454433befb0a433866765b09dd12a5dd7c6d |
| 參考標籤及來源 | canonical JSON | 952a45a99409ea7dcbf169ff14f7e386ddb7157deb1866cb799414d9d7b9d2fe |
| 規則 | canonical JSON | d8cb0f4872c1ee9010b89ca1f7f058fed00f6ad74fb523f8dc772826ad010388 |
| 原始 metadata | canonical JSON | f33c7f063b0959d7125c597a88146be79a1c8710db62282116f2bbea5862d963 |

資料入口：[主實驗 manifest](pubmed_hybrid/runs/20261015T160809.127489Z-ec128a40/manifest.json)、[平均指標](pubmed_hybrid/runs/20261015T160809.127489Z-ec128a40/metrics_summary.csv)、[逐查詢指標](pubmed_hybrid/runs/20261015T160809.127489Z-ec128a40/metrics_per_query.csv)、[全部參考標籤與理由](pubmed_hybrid/runs/20261015T160809.127489Z-ec128a40/reference_labels.csv)、[來源涵蓋](pubmed_hybrid/runs/20261015T160809.127489Z-ec128a40/reference_coverage.csv)、[Top k 來源](pubmed_hybrid/runs/20261015T160809.127489Z-ec128a40/reference_topk_sources.csv)、[完整規則副本](pubmed_hybrid/runs/20261015T160809.127489Z-ec128a40/reference_rules.json)、[PubMed metadata](pubmed_hybrid/runs/20261015T160809.127489Z-ec128a40/pubmed_metadata.json)。

### 9.2 數值核對的範圍

保存的完整測試紀錄為 106 項通過，之後另補跑七項參考來源測試，包含六項重跑與一項新增 CSV 防護；不能把兩次數量相加。測試與可重現性驗證說明程式行為，不構成人工相關性證據。

獨立 NumPy 核對 3,000×10×5=150,000 個 cosine 分數，最大誤差為 1.1102230246251565×10^-16；五方法十查詢 L2 等價檢查通過。獨立數值核對範圍為 C＋標準 IDF，不宣稱 B／D、平滑 IDF 都已完整獨立驗證。HW2 93 個受保護檔案指紋核對未改變。

本報告再對保存排名與標籤獨立重算 50 組指標及五方法平均、核對所有輸出 hash，並以目前相同計分程式重算 Q01 Top 10、詞項及 raw dot 補充例子。衍生資料與核對結果位於本報告附件，這些檢查均未新增人工標籤。

### 9.3 操作與重現指令

```powershell
Set-Location -LiteralPath 'C:\成大專案\IR-HW3'
& '.\.venv\Scripts\python.exe' -B -X utf8 -m ir_hw3.cli verify
& '.\.venv\Scripts\python.exe' -B -X utf8 -m ir_hw3.cli verify --source
& '.\.venv\Scripts\python.exe' -B -X utf8 scripts\verify_hw3.py
& '.\.venv\Scripts\python.exe' -B -X utf8 -m ir_hw3.cli experiment --source pubmed
& '.\.venv\Scripts\python.exe' -B -X utf8 scripts\evaluate_pubmed_reference.py
# 從本報告固定的歷史 run 重建文字與附件；新位置避免覆寫本報告
& '.\.venv\Scripts\python.exe' -B -X utf8 scripts\build_hw3_report.py --report reports\reproduced\HW3_REPORT.md
```

PubMed 自動參考與 weak rule 實驗使用獨立 run 目錄，不覆寫 human 或歷史輸出。重跑 evaluate_pubmed_reference 會新增實驗，時間／run_id 可以不同；應核對語料、查詢、標籤、設定及輸出，不以新 run_id 當作結果改變。重建本報告的腳本固定引用上列歷史 run，並拒絕覆寫已存在的報告。

環境為 Python 3.12.14；主要依賴為 Streamlit 1.66.0、NumPy 2.5.4、pandas 3.0.6、NLTK 3.9.2、regex 2026.9.29、Altair 6.3.0、defusedxml 0.7.1，依實驗 manifest 記錄。HW3 使用自己的 .venv；不依賴 HW2 的執行環境。來源摘要可能有著作權，不宣稱全部是開放授權。

## 10 操作展示與結論

展示約六分鐘：先在語料與設定說明固定 3,000 篇、C、標準 IDF 與 TF／DF／CF；接著搜尋 Q01，查看 Top 10、原摘要與逐詞權重；在方法比較固定查詢切換 weighting，說明排名改變與 L2 等價。最後於效能評估選「PubMed 主題參考＋弱規則回退」、k=10，展示十查詢納入數、來源涵蓋、逐筆依據與並排 0～1 指標圖，再指向獨立 run、完整報告與來源敏感度對照。人工頁保留其實際進度，不為 demo 虛填人工等級。

此實驗顯示詞頻壓縮與 IDF 會改變排名及對自動參考集合的符合程度；標準 cosine 的顯式 L2 前後保持等價。Log TF-IDF 在混合參考下取得最高平均 nDCG@10，IDF-only 的 P@10 並列最高，TF-IDF 則在部分查詢與純 weak 對照中較好。結論應同時依查詢、指標與標籤來源解讀，不能將某次平均勝出視為普遍優越，更不能將此自動參考評估寫成已經人工驗證。

## 附錄 A 完整 metadata 別名與判據

共享 Gm 的完整別名：GLP-1、GLP1、glucagon-like peptide 1、glucagon-like peptide-1 receptor agonists、glucagon-like peptide-1 receptor、semaglutide、liraglutide、tirzepatide、exenatide、dulaglutide、lixisenatide、albiglutide、efpeglenatide。

| 查詢 | metadata 概念組一 | metadata 概念組二 任一詞 |
| --- | --- | --- |
| Q01 | semaglutide | obesity、obese、weight loss、weight reduction、weight management、anti-obesity agents |
| Q02 | liraglutide | obesity、obese、weight loss、weight reduction、anti-obesity agents |
| Q03 | tirzepatide | diabetes mellitus、type 2 diabetes、diabetes、diabetic、glycemic control、glycaemic control、blood glucose |
| Q04 | Gm | cardiovascular、heart failure、cardiac、major adverse cardiac events、myocardial infarction、stroke |
| Q05 | Gm | kidney、renal、nephropathy、nephropathies、diabetic nephropathies、albuminuria、glomerular filtration rate |
| Q06 | Gm | gastric emptying、gastrointestinal motility、gastric motility、gastroparesis |
| Q07 | Gm | nausea、vomiting、emesis |
| Q08 | Gm | insulin secretion、insulin release、insulin-secreting cells、beta cell、beta cells、beta-cell、beta-cells、β cell、β cells |
| Q09 | Gm | gastrointestinal microbiome、microbiota、microbiome |
| Q10 | Gm | neuroprotection、neuroprotective、alzheimer、alzheimer's、parkinson、parkinson's、neurodegenerative、neurodegeneration |

組內 OR、組間 AND；文字正規化、允許欄位與回退規則依第 4 節。下列固定 JSON 及原 run 的副本是可機器重現的規則來源，不採線上自動映射。

## 附錄 B 五方法十查詢完整指標

| 查詢 | 方法 | P@10 | 參考 Recall@10 | RR | nDCG@10 |
| --- | --- | --- | --- | --- | --- |
| Q01 | 原始 TF | 0.7000 | 0.0131 | 1.0000 | 0.7421 |
| Q01 | Log TF | 0.7000 | 0.0131 | 1.0000 | 0.7682 |
| Q01 | 僅 IDF | 1.0000 | 0.0188 | 1.0000 | 1.0000 |
| Q01 | TF × IDF | 0.9000 | 0.0169 | 1.0000 | 0.9216 |
| Q01 | Log TF × IDF | 1.0000 | 0.0188 | 1.0000 | 1.0000 |
| Q02 | 原始 TF | 0.4000 | 0.0234 | 1.0000 | 0.4780 |
| Q02 | Log TF | 0.8000 | 0.0468 | 1.0000 | 0.8630 |
| Q02 | 僅 IDF | 0.8000 | 0.0468 | 0.5000 | 0.7163 |
| Q02 | TF × IDF | 0.7000 | 0.0409 | 1.0000 | 0.7917 |
| Q02 | Log TF × IDF | 0.7000 | 0.0409 | 1.0000 | 0.7632 |
| Q03 | 原始 TF | 0.6000 | 0.0213 | 0.5000 | 0.5658 |
| Q03 | Log TF | 0.8000 | 0.0284 | 1.0000 | 0.8522 |
| Q03 | 僅 IDF | 0.9000 | 0.0319 | 1.0000 | 0.8900 |
| Q03 | TF × IDF | 1.0000 | 0.0355 | 1.0000 | 1.0000 |
| Q03 | Log TF × IDF | 0.8000 | 0.0284 | 1.0000 | 0.8630 |
| Q04 | 原始 TF | 1.0000 | 0.0130 | 1.0000 | 1.0000 |
| Q04 | Log TF | 1.0000 | 0.0130 | 1.0000 | 1.0000 |
| Q04 | 僅 IDF | 1.0000 | 0.0130 | 1.0000 | 1.0000 |
| Q04 | TF × IDF | 1.0000 | 0.0130 | 1.0000 | 1.0000 |
| Q04 | Log TF × IDF | 1.0000 | 0.0130 | 1.0000 | 1.0000 |
| Q05 | 原始 TF | 1.0000 | 0.0215 | 1.0000 | 1.0000 |
| Q05 | Log TF | 1.0000 | 0.0215 | 1.0000 | 1.0000 |
| Q05 | 僅 IDF | 1.0000 | 0.0215 | 1.0000 | 1.0000 |
| Q05 | TF × IDF | 1.0000 | 0.0215 | 1.0000 | 1.0000 |
| Q05 | Log TF × IDF | 1.0000 | 0.0215 | 1.0000 | 1.0000 |
| Q06 | 原始 TF | 0.9000 | 0.0841 | 1.0000 | 0.9216 |
| Q06 | Log TF | 0.9000 | 0.0841 | 1.0000 | 0.9216 |
| Q06 | 僅 IDF | 1.0000 | 0.0935 | 1.0000 | 1.0000 |
| Q06 | TF × IDF | 1.0000 | 0.0935 | 1.0000 | 1.0000 |
| Q06 | Log TF × IDF | 1.0000 | 0.0935 | 1.0000 | 1.0000 |
| Q07 | 原始 TF | 0.1000 | 0.0099 | 1.0000 | 0.2201 |
| Q07 | Log TF | 0.7000 | 0.0693 | 1.0000 | 0.7100 |
| Q07 | 僅 IDF | 1.0000 | 0.0990 | 1.0000 | 1.0000 |
| Q07 | TF × IDF | 1.0000 | 0.0990 | 1.0000 | 1.0000 |
| Q07 | Log TF × IDF | 1.0000 | 0.0990 | 1.0000 | 1.0000 |
| Q08 | 原始 TF | 0.8000 | 0.0615 | 1.0000 | 0.8365 |
| Q08 | Log TF | 0.7000 | 0.0538 | 1.0000 | 0.7313 |
| Q08 | 僅 IDF | 0.7000 | 0.0538 | 1.0000 | 0.8007 |
| Q08 | TF × IDF | 0.7000 | 0.0538 | 1.0000 | 0.7728 |
| Q08 | Log TF × IDF | 0.9000 | 0.0692 | 1.0000 | 0.9149 |
| Q09 | 原始 TF | 0.9000 | 0.0552 | 1.0000 | 0.9306 |
| Q09 | Log TF | 1.0000 | 0.0613 | 1.0000 | 1.0000 |
| Q09 | 僅 IDF | 1.0000 | 0.0613 | 1.0000 | 1.0000 |
| Q09 | TF × IDF | 1.0000 | 0.0613 | 1.0000 | 1.0000 |
| Q09 | Log TF × IDF | 1.0000 | 0.0613 | 1.0000 | 1.0000 |
| Q10 | 原始 TF | 0.3000 | 0.0190 | 0.2500 | 0.2583 |
| Q10 | Log TF | 0.5000 | 0.0316 | 0.5000 | 0.4807 |
| Q10 | 僅 IDF | 1.0000 | 0.0633 | 1.0000 | 1.0000 |
| Q10 | TF × IDF | 1.0000 | 0.0633 | 1.0000 | 1.0000 |
| Q10 | Log TF × IDF | 1.0000 | 0.0633 | 1.0000 | 1.0000 |

RR 是單一查詢的 reciprocal rank；前述 MRR 為這些 RR 的平均。參考標籤全覆蓋，因此各列 judged@10 皆為 1，沒有宣稱人工已完成。

## 附錄 C Q01 的 TF-IDF 前十名與標籤來源

| 名次 | PMID | cosine | 標題 |
| --- | --- | --- | --- |
| 1 | 42105046 | 0.335608 | Semaglutide and Cardiovascular Outcomes in People with Type 2 Diabetes: A SUSTAIN-6 Post Hoc Analysis by Weight Loss Category. |
| 2 | 42518911 | 0.236161 | Real-World Comparative Weight Loss of GLP-1 Receptor Agonists in the All of Us Research Program: A Retrospective Cohort Study. |
| 3 | 42536519 | 0.233409 | Effectiveness & safety of semaglutide in weight reduction in obese nondiabetic patients: A systematic review and meta-analysis. |
| 4 | 42824923 | 0.226379 | Predictors of treatment response to semaglutide for weight management. |
| 5 | 42507673 | 0.225993 | Impact of semaglutide withdrawal on cardiometabolic profile and physiology of energy balance: Recovery effects after semaglutide termination - The REST trial study protocol. |
| 6 | 42220241 | 0.220930 | Role of Physical Activity in Obesity Treatment and Cardiometabolic Health: A Scientific Statement From the American Heart Association. |
| 7 | 41872986 | 0.210229 | GLP-1 Receptor/Dual Agonists for Weight Loss: A Systematic Review and Network Meta-Analysis of RCTs. |
| 8 | 42023428 | 0.200258 | Efficacy, Safety and PK of Once-Daily Oral Semaglutide 25 mg for Obesity With and Without Type 2 Diabetes in Comparison With Subcutaneous Semaglutide 2.4 mg: A Model-Informed Drug Development Approach. |
| 9 | 41884974 | 0.197881 | SEMASEARCH Study Design: Real-World Evaluation of Semaglutide 2.4 mg in Adults With Severe Obesity Underrepresented in Clinical Trials. |
| 10 | 42225300 | 0.187895 | Semaglutide 25 mg Oral Versus Semaglutide 2.4 mg Injectable: An Indirect Treatment Comparison of Weight Loss Outcomes. |

逐筆參考來源與判定依據：

| PMID | 參考等級 | 來源 | 規則理由 |
| --- | --- | --- | --- |
| 42105046 | 1 | PubMed 主題依據 | PubMed 主題參考：組1 keyword=Semaglutide；組2 keyword=Weight loss |
| 42518911 | 1 | PubMed 主題依據 | PubMed 主題參考：組1 mesh=Semaglutide；組2 mesh=Weight Loss |
| 42536519 | 1 | PubMed 主題依據 | PubMed 主題參考：組1 mesh=Semaglutide；組2 mesh=Obesity |
| 42824923 | 1 | PubMed 主題依據 | PubMed 主題參考：組1 mesh=Semaglutide；組2 mesh=Obesity |
| 42507673 | 1 | PubMed 主題依據 | PubMed 主題參考：組1 mesh=Semaglutide；組2 mesh=Obesity |
| 42220241 | 0 | weak rule 回退 | PubMed 主題依據不足，回退摘要 weak rule；規則弱標籤：缺少概念組 1 |
| 41872986 | 1 | PubMed 主題依據 | PubMed 主題參考：組1 mesh=Semaglutide；組2 mesh=Weight Loss |
| 42023428 | 1 | PubMed 主題依據 | PubMed 主題參考：組1 mesh=Semaglutide；組2 mesh=Anti-Obesity Agents |
| 41884974 | 1 | PubMed 主題依據 | PubMed 主題參考：組1 mesh=Semaglutide；組2 mesh=Obesity, Morbid |
| 42225300 | 1 | PubMed 主題依據 | PubMed 主題參考：組1 mesh=Semaglutide；組2 mesh=Anti-Obesity Agents |

標題為閱讀資訊，未加入檢索向量；來源與理由來自自動規則保存紀錄，不是本報告作者對各篇內容的人工裁決。前十名以外的完整非零排名、全部 30,000 筆標籤、來源比例與原始 metadata 另附於主 run。

## 參考資料

1. [作業原題 Homework 3](../docs/Homework-3.pdf)，完整兩頁，任務五及 RQ1～RQ5。
2. NLM，[PubMed MeSH Terms](https://pubmed.ncbi.nlm.nih.gov/help/#mesh-terms-mh) 與 [Other Term](https://pubmed.ncbi.nlm.nih.gov/help/#other-term-ot)，欄位意義與限制；查閱日期 2026/10/16。
3. Manning, Raghavan, Schütze，[Information retrieval system evaluation](https://nlp.stanford.edu/IR-book/html/htmledition/information-retrieval-system-evaluation-1.html)，相關性依資訊需求判定。
4. 同書，[Evaluation of ranked retrieval results](https://nlp.stanford.edu/IR-book/html/htmledition/evaluation-of-ranked-retrieval-results-1.html)，排名評估指標。

附件：[詞項明細](HW3_REPORT_assets/rq1_term_example.csv)、[點積與長度對照](HW3_REPORT_assets/rq4_dot_example.csv)、[報告來源與核對紀錄](HW3_REPORT_assets/audit.json)。
