# PubMed 主題參考與 weak rule 回退

使用者於 2026/10/15 指定的自動參考來源為 `pubmed_hybrid`。只用現有 3,000 篇快照的 XML，不重新下載、不改摘要、不寫人工標註。這不是 PubMed 官方的 Q01–Q10 相關性答案，與 `human`、純摘要 `weak_rules` 分流。

## 固定程序

1. 依每篇保存的 `raw_path` 讀取其 XML，核對語料、所選 PMID 與 XML SHA256，不任選其他取得版本的重複 PMID。
2. 抽取 MeSH DescriptorName、ChemicalList/NameOfSubstance、SupplMeshName、Keyword。保留 UI、MajorTopicYN、MeSH qualifier、文章類型、標引狀態及 XML 來源。文章類型只供描述，不當作主題證據。
3. 每查詢有兩組概念，各組至少一詞出現在同篇任一允許的 metadata 欄位，給 `grade=1, label_source=pubmed_metadata`。
4. 欄位缺失或不足以支持全部概念組時，獨立執行原 `data/queries.json` 的摘要 weak rule：全部概念組皆命中為 1，否則為 0，來源為 `weak_rules_fallback`。不把部分 metadata 與部分摘要命中拼成正例。
5. 每篇每查詢均產生二元 0／1 **規則參考**結果，沒有自動等級 2。0 是規則未找到足夠共現證據，不是人工判為不相關。標籤不讀排名、分數、TF、DF、weighting 或前處理；五方法共享同一份標籤。

「沒有標籤時回退」明確定義為「沒有足夠支持此查詢全部概念組的主題證據」。有欄位但概念未涵蓋也回退，避免把未標引當成真實負例。`fallback_reason` 分別記 `no_topic_metadata`、`incomplete_metadata_concepts`。

## 十查詢判據

完整固定別名表在 `data/reference_rules/pubmed-v1.json`，每次 run 另存副本與 hash。下表是摘要，不取代 JSON。

| 查詢 | 概念組一 | 概念組二 |
|---|---|---|
| Q01 | semaglutide | 肥胖、減重或體重管理 |
| Q02 | liraglutide | 肥胖或減重 |
| Q03 | tirzepatide | 糖尿病、血糖或血糖控制 |
| Q04 | GLP-1／受體／致效劑 | 心血管、心衰竭、心肌梗塞或中風 |
| Q05 | GLP-1／受體／致效劑 | 腎臟、腎病、白蛋白尿或腎絲球過濾率 |
| Q06 | GLP-1／受體／致效劑 | 胃排空、腸胃蠕動或胃輕癱 |
| Q07 | GLP-1／受體／致效劑 | 噁心或嘔吐 |
| Q08 | GLP-1／受體／致效劑 | 胰島素分泌或胰島 β 細胞 |
| Q09 | GLP-1／受體／致效劑 | 腸道菌相／微生物群 |
| Q10 | GLP-1／受體／致效劑 | 神經保護、阿茲海默、帕金森或神經退化 |

GLP-1 共享組明列 GLP-1、GLP1、glucagon-like peptide 1、其受體／致效劑，以及 semaglutide、liraglutide、tirzepatide、exenatide、dulaglutide、lixisenatide、albiglutide、efpeglenatide。單獨 glucagon、GLP-2 不算 GLP-1。Q03 的糖尿病標籤不證實必為第二型或量測血糖控制；Q04/Q05 的疾病／器官標籤也不證實改善結果，這些屬概念代理的限制。

metadata 採 Unicode NFKC、casefold、標點／連字號改空白後的完整詞序列邊界，不用子字串前綴、MeSH 樹狀展開或線上自動翻譯。回退完整沿用原弱規則，包括其已明列前綴 neuroprotect*／neurodegenerat*，不改舊詞表。人體、動物、細胞均可依查詢意圖納入，沒有另加臨床限制。

## 指標與敏感度對照

固定 3,000 篇、十查詢、C、log10 的標準 IDF 與 Log TF、cosine 及原同分規則，比較五種 weighting。P@10 分母固定 10；MRR 用完整非零排名；nDCG@10 為二元 gain；Recall@10 分母為此規則定義的正例集合，**不是完整真實相關集合 Recall**。平均只納入有參考正例的查詢，照常列實際母數和排除原因。

另跑相同程式／語料／設定的純 `weak_rules` 基準，並列指標及來源影響。這是更換標籤來源的敏感度對照，不是只改 weighting 的受控比較；不為讓指定方法勝出而改規則。逐查詢及 Top k 同時揭露 metadata 與 weak 回退比例。

## 限制

- 共同主題不保證研究關係、主要終點、療效或臨床效度；不辨識否定、藥物與終點的關係。
- MeSH 可能由自動標引產生，不能一律稱為人工專家判讀。關鍵字來源與完整性也不同。
- 缺少欄位不等於不相關；回退 0 仍可能漏掉同義詞或隱含概念。
- metadata 和關鍵字仍共享詞面訊號；weak 回退的詞彙偏差更直接。兩類正例聯集可能使指標升高，不代表更接近人工真值。
- binary proxy labels 不能等同人工 0／1／2；MeSH major topic 不自動映射高度相關。
- 全語料跑過規則只代表規則涵蓋完整，不代表真實相關性被完整判讀。仍受單一主題、非隨機取樣及摘要範圍限制。
- 獨立人工抽查屬未來可補的效度證據，目前不宣稱已完成。

## 保存與重現

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m ir_hw3.cli experiment --source pubmed
.\.venv\Scripts\python.exe -B -X utf8 -m ir_hw3.cli history --source pubmed_hybrid
.\.venv\Scripts\python.exe -B -X utf8 scripts\evaluate_pubmed_reference.py
```

獨立保存於 `reports/pubmed_hybrid/runs/<run_id>/`。除原排名、指標、查詢、標籤、RQ 與 manifest 外，另有：

`evaluate_pubmed_reference.py` 從 XML 重新產生兩次標籤並比對，另保存兩次混合實驗與一次純 weak 基準，在 `reports/pubmed_hybrid/analysis/<id>/` 產生中文報告、來源敏感度表與驗證指紋。

- `reference_rules.json`：完整規則。
- `pubmed_metadata.json`：每篇欄位、UI／major／qualifier、XML hash、涵蓋數、抽取指紋。
- `reference_labels.csv`：30,000 筆查詢–文件標籤、理由、metadata 證據、回退來源與純弱規則結果。
- `reference_coverage.csv`：逐查詢 metadata 正例、兩類回退、回退正例、參考集合數量。
- `reference_topk_sources.csv`：每方法每查詢 Top k 的 metadata 正例、回退正例、回退負例。

程式、規則、語料、XML、查詢、metadata、標籤及輸出 hash 隨 run 保存。版本更換另建 run，不覆寫。人工 JSON/CSV 仍只接受 human；舊 weak_rules 與 1,000 篇結果保留。

欄位意義依 NLM 官方 [MeSH Terms](https://pubmed.ncbi.nlm.nih.gov/help/#mesh-terms-mh)、[Other Term／關鍵字](https://pubmed.ncbi.nlm.nih.gov/help/#other-term-ot)、[文章類型](https://pubmed.ncbi.nlm.nih.gov/help/#publication-type-pt)。參考詞組與相關性映射是本專案規則，不是 NLM 的查詢相關性裁決。
