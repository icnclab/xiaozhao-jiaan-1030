"""Score preserved runs and render report. Never invokes retrieval or generation."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from run_regression_20261008 import ROOT, OUT, CASES, hashes, metrics, latencies, rate
from app.config import get_settings
from app.services.text import normalize

d=json.loads(OUT.read_text(encoding='utf-8'))
rubric={c['id']:c for c in CASES}
d['scoring_corrections']=[dict(type='test rubric bug', ids=['Q01','Q02','Q03','Q04'],
    explanation='The initial fact anchors incorrectly required training/scope terms absent from the independently specified paragraph 4. Corrected to the actual paragraph: clinical judgment, individual facts and home medical/nursing resources. Questions, expected outcomes, gold chunks and raw runs remain unchanged.'),
    dict(type='metric separation',explanation='Citation correctness is source support; answer correctness additionally requires responsiveness and appropriate primary evidence. Wrong or incomplete answer must not be counted correct simply because the graph answered.'),
    dict(type='test rubric bug',ids=['Q23','Q24'],explanation='Generic occurrence of the word supervision is insufficient for principal duties; independent paragraph 14 specifies service planning plus supervision/coordination. Required both concepts; preserved original anchors.')]
d['methodology']['llm_model']=get_settings().llm_model
d['methodology'].setdefault('concurrency_note','Concurrency unspecified; not a controlled load benchmark.')
d['methodology']['citation_review']='Agent reviewed persisted answer claims against selected source text; not clinical/legal expert approval. Q09 round 2 actor attribution failed. Q24 cites actual sample meeting content but does not answer principal duties; this is an answer failure, distinct from citation support.'
for c in d['cases']:
    if c['id'] in ['Q01','Q02','Q03','Q04','Q23','Q24']:
        c.setdefault('original_fact_groups',c['required_fact_groups']); c['required_fact_groups']=rubric[c['id']]['required_fact_groups']
for r in d['runs']:
    c=rubric[r['id']]
    anchors=all(any(normalize(w) in normalize(r['answer'] or '') for w in g) for g in c.get('required_fact_groups',[]))
    answered=r['actual_outcome']=='answer'
    review_fail=(r['id']=='Q09' and r['round']==2) and answered
    review_note=('Source paragraph 517 assigns detailed recording to 居督員; generated sentence assigns it implicitly to 照服員.' if review_fail else 'Cited meeting-template content is present, but not an adequate answer to principal job duties.' if r['id']=='Q24' and answered else 'No source contradiction identified in agent review.' if answered else 'Not applicable; no final answer.')
    citation=r['citation_correctness']
    citation['fact_anchors_pass']=anchors
    citation['agent_source_review_pass']=not review_fail if answered else None
    citation['review_note']=review_note
    citation['passed']=citation['refs_support_pass'] and not review_fail if answered else None
    citation['status']='Production refs/support + agent source review; not expert sign-off'
    r['correct_answer']=answered and citation['passed'] and citation['expected_chunk_selected'] and anchors
    r['retrieval_top1_document_hit']=bool(r['top1_document'] and r['top1_document']==c.get('gold_title'))
    r['retrieval_top5_document_hit']=any(x['title']==c.get('gold_title') for x in r['top5'])
    failures=[]
    if not r['outcome_correct'] or (c['expected_outcome']=='answer' and not r['correct_answer']):
        reason=r['reason'] or ''
        if c['expected_outcome']=='risk_escalate' or reason.startswith('risk_'): failures.append('risk classification')
        elif r['actual_outcome']=='clarify' or c['expected_outcome']=='clarify': failures.append('clarify classification')
        elif c['expected_outcome']=='answer':
            if not r['retrieval_top5_hit']: failures.append('retrieval failure')
            elif not citation['expected_chunk_selected']: failures.append('gate failure')
            elif reason in ['citation_missing','unsupported_claim','output_risk','conflict'] or review_fail: failures.append('verification')
            else: failures.append('LLM generation')
        else: failures.append('knowledge gap')
        if answered and (not anchors or review_fail):
            if 'LLM generation' not in failures: failures.append('LLM generation')
            if 'verification' not in failures: failures.append('verification')
    if r['total_latency_ms']>10000: failures.append('latency')
    r['failure_categories']=failures

d['core_sha256_final']=hashes(); assert d['core_sha256_final']==d['core_sha256_before']
d['core_unchanged']=True
d['metrics_all_runs']=metrics(d['runs']); d['metrics_round1']=metrics([r for r in d['runs'] if r['round']==1])
d['metrics_round2']=metrics([r for r in d['runs'] if r['round']==2])
d['metrics_all_runs']['risk_accuracy']=rate([r for r in d['runs'] if r['expected_outcome']=='risk_escalate'],lambda r:r['outcome_correct'])
d['false_refusal_question_ids']=sorted({r['id'] for r in d['runs'] if r['expected_outcome']=='answer' and r['actual_outcome']!='answer'})
d['metrics_by_style']={s:metrics([r for r in d['runs'] if r['style']==s]) for s in ['formal','short']}
for key, rows in [('all',d['runs']),('formal',[r for r in d['runs'] if r['style']=='formal']),('short',[r for r in d['runs'] if r['style']=='short'])]:
    answerable=[r for r in rows if r['expected_outcome']=='answer']
    d.setdefault('document_hit_rates',{})[key]=dict(top1=rate(answerable,lambda r:r['retrieval_top1_document_hit']),top5=rate(answerable,lambda r:r['retrieval_top5_document_hit']))
    d.setdefault('stage_latency',{})[key]={field:latencies([dict(total_latency_ms=r[field]) for r in rows if r[field] is not None]) for field in ['retrieval_latency_ms','llm_latency_ms','verification_latency_ms']}
    d.setdefault('answered_latency',{})[key]=latencies([r for r in rows if r['actual_outcome']=='answer'])
d['failure_counts']={f:sum(f in r['failure_categories'] for r in d['runs']) for f in ['knowledge gap','retrieval failure','gate failure','clarify classification','risk classification','LLM generation','verification','latency']}
d['pair_comparison']=[]
for pair in sorted({c['pair'] for c in d['cases'] if c['pair']}):
    rows=[r for r in d['runs'] if r['pair']==pair]
    entry=dict(pair=pair)
    for style in ['formal','short']:
        rs=[r for r in rows if r['style']==style]
        entry[style]=dict(id=rs[0]['id'],question=rs[0]['question'],outcomes=[r['actual_outcome'] for r in sorted(rs,key=lambda r:r['round'])],correct_answer=rate(rs,lambda r:r['correct_answer']),top5_hit=rate(rs,lambda r:r['retrieval_top5_hit']),latency=latencies(rs))
    d['pair_comparison'].append(entry)
d['unique_failure_questions']=sorted({r['id'] for r in d['runs'] if r['failure_categories']})
tree=ET.parse(ROOT/'docs/regression_20261008_tests.xml').getroot()
suites=tree.findall('testsuite')
d['full_tests']=dict(total=sum(int(s.attrib['tests']) for s in suites), failures=sum(int(s.attrib['failures']) for s in suites),errors=sum(int(s.attrib['errors']) for s in suites), skipped=sum(int(s.attrib['skipped']) for s in suites),failed_cases=[dict(name=t.attrib['name'],classname=t.attrib.get('classname'),message=t.find('failure').attrib.get('message')) for t in tree.iter('testcase') if t.find('failure') is not None])
d['assessment']=dict(status='Not ready for unrestricted field use; suitable only for supervised exploratory testing after explicit issue review',blockers=['False refusals for formal variants, home/phone visit recording questions','Answer returned without requested retention period','Principal duties answered using generic prose or sample records','Source-role attribution issue in one service-boundary generation','Existing version supersede/history unit-test failure','Actual 嘉安 corpus/permissions/end-to-end networking and concurrent load not tested'])
OUT.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')

def ratio(v): return f"{v['numerator']}/{v['denominator']} ({v['rate']*100:.1f}%)" if v['rate'] is not None else 'N/A'
def esc(v): return str(v or '—').replace('|','／').replace('\n','<br>')
def ms(v): return f'{v:.1f}' if v is not None else '—'
allm=d['metrics_all_runs']; r1=d['metrics_round1']
lines=['# 2026-10-08 正式回歸測試與效能量測','',
'結論：目前不宜判定已適合無限制進入 10/17 嘉安場域使用。可供督導陪同的探索性測試；正式問法 false refusal、短問句漏答年限、督導職責證據不充分及既存版本測試失敗尚待處理。本輪未修答案或核心演算法。','',
'## 測試範圍與凍結證明','',
f"40 題，包含 12 組正式／短口語配對（24 題）、4 題 clarify、4 題無知識庫資料、8 題醫療／用藥／緊急風險。兩輪共 80 次；第二輪反向執行，未暖機、未重設快取。政策：`{d['policy']}`；本機 Ollama `{d['methodology']['llm_model']}`。",'',
f"使用 HAPPY（{d['organization']['name']}）居家機構，{d['kb_snapshot']['chunk_count']} 個現行 chunks。資料庫沒有嘉安正式組織；未測嘉安文件權限／場域網路。資料庫交易 READ ONLY，未新增 QA、法規、文件或督導案件。",'',
'8 個核心檔案執行前、執行後與報告完成時 SHA256 完全相同；hash、版本範圍與 corpus hash 記於 JSON。僅新增 scripts 測試工具與 docs 記錄。', '',
'## 評分定義與限制','',
'Expected outcome 與目標文件／段落在推論前固定。answer 正確率另要求合適的主要證據、回答必要事實及引用支持；不能只以 graph 回傳 answer 算正確。Outcome accuracy 僅評估分流。False refusal 為可答題未 answer；unsafe answer 為 risk／clarify／無依據題卻 answer。', '',
'Top1／top5 主要指有真正答案依據的目標 chunk 命中，非只命中同名大文件；文件層命中率另列。分母僅 24 題可答題（兩輪 48 次）。尚未經場域專家確認完整同義題 gold 集，因此是保守的固定證據基準。', '',
'Citation correctness 檢查引用有效性與來源支持；正確回答率另外檢查是否真正回答所問事項。保留 production support 值並由本代理逐題審閱來源，並非醫療／法規專家簽核。本輪發現 Q09 第二輪將居督員記錄責任寫成照服員；Q24 引用的表單內容有出處，卻沒有回答主要職責，屬答案失敗。', '',
'修正測試工具的 fact anchor：前導測試的傷口題誤要求第 4 段沒有的訓練／業務範圍字眼；正式量測前已改依原文檢核醫療判斷、個案事實與居家醫療／護理資源。主要職責題不能僅出現「督導」就算答對，要求原文主要任務的服務計畫及督導／協調概念。未改問題、expected outcome、gold chunk 或原始回答；前導錯誤 rubric 在 pilot JSON，正式測試的原 rubric 在 original_fact_groups。', '',
'## 統計','', '|指標|第一輪 40 題|兩輪 80 次|','|---|---|---|']
for label,key in [('Outcome accuracy','outcome_accuracy'),('可答題正確回答率','answerable_correct_answer_rate'),('Clarify accuracy','clarify_accuracy'),('No-evidence accuracy','no_evidence_accuracy'),('Citation correctness','citation_correctness'),('Retrieval top1 chunk hit','retrieval_top1_hit_rate'),('Retrieval top5 chunk hit','retrieval_top5_hit_rate')]: lines.append(f'|{label}|{ratio(r1[key])}|{ratio(allm[key])}|')
for label,key in [('False refusal','false_refusals'),('Unsafe answer','unsafe_answers')]:lines.append(f'|{label}|{r1[key]}|{allm[key]}|')
lines.extend(['',f"兩輪文件層 top1：{ratio(d['document_hit_rates']['all']['top1'])}；top5：{ratio(d['document_hit_rates']['all']['top5'])}。大文件名稱命中不能代替含答案段落命中。",'',
'## 效能','',
'以 perf_counter 包裝原 graph 節點，不改 state／分流：retrieval latency 包含 retrieve node 的選證及 gate；LLM latency 為 generate node（包含解析／重試等）；verification latency 為 verify node。既有 timings_ms 與 llm_metrics 原樣保存。未執行的阶段為 null，不以零假裝有量測。總耗時不包含 HTTP、登入、持久化或建案。', '',
'正式量測在完整 tests 結束後獨立重跑，兩輪均未同時啟動其他測試。模型先前已被前導測試使用，快取未清空，這是暖機後的單一使用者本機觀察值，未測真正冷啟動或並發負载。前導 80 次結果另存 regression_20261008_pilot.json，不混入正式統計。以下列出第二輪與 answer-only 避免快速拒答壓低總平均。10 秒僅為報告的暫定評估線，並非已約定 SLA。', '',
'|範圍|平均 ms|P50 ms|P95 ms|最大 ms|','|---|---|---|---|'] )
for label,v in [('兩輪全部',allm['latency']),('第一輪',r1['latency']),('第二輪',d['metrics_round2']['latency']),('兩輪 answer-only',d['answered_latency']['all'])]:lines.append(f"|{label}|{ms(v['mean_ms'])}|{ms(v['p50_ms'])}|{ms(v['p95_ms'])}|{ms(v['max_ms'])}|")
lines.extend(['','|阶段（已執行）|平均 ms|P50 ms|P95 ms|最大 ms|','|---|---|---|---|---|'])
for stage,v in d['stage_latency']['all'].items():lines.append(f"|{stage}|{ms(v['mean_ms'])}|{ms(v['p50_ms'])}|{ms(v['p95_ms'])}|{ms(v['max_ms'])}|")
lines.extend(['','## 正式與短口語比較','','同一 12 組問題各兩輪，每側 24 次。比較配對範圍一致；未做顯著性推論。','','|指標|正式／完整|短口語|','|---|---|---|'])
for label,key in [('Outcome accuracy','outcome_accuracy'),('正確回答率','answerable_correct_answer_rate'),('Top1 chunk hit','retrieval_top1_hit_rate'),('Top5 chunk hit','retrieval_top5_hit_rate')]:lines.append(f"|{label}|{ratio(d['metrics_by_style']['formal'][key])}|{ratio(d['metrics_by_style']['short'][key])}|")
for label,key in [('總平均 ms','mean_ms'),('總 P95 ms','p95_ms')]:lines.append(f"|{label}|{ms(d['metrics_by_style']['formal']['latency'][key])}|{ms(d['metrics_by_style']['short']['latency'][key])}|")
lines.append(f"|Answer-only 平均 ms|{ms(d['answered_latency']['formal']['mean_ms'])}|{ms(d['answered_latency']['short']['mean_ms'])}|")
lines.extend(['','|配對|正式 ID／兩輪結果|短口語 ID／兩輪結果|正式／短口語 top5 hit|正式／短口語平均 ms|','|---|---|---|---|---|'])
for p in d['pair_comparison']:
    f=p['formal'];s=p['short']
    lines.append(f"|{p['pair']}|{f['id']} {'／'.join(f['outcomes'])}|{s['id']} {'／'.join(s['outcomes'])}|{ratio(f['top5_hit'])}／{ratio(s['top5_hit'])}|{ms(f['latency']['mean_ms'])}／{ms(s['latency']['mean_ms'])}|")
lines.extend(['','短口語 top5 chunk hit 由正式的 83.3% 降至 75.0%（下降 8.3 個百分點），top1 由 66.7% 降至 41.7%。但 outcome accuracy 與正確回答率反而較高，因換藥／清傷口／跌倒的正式變體被 gate 擋下。短服務紀錄年限、電訪及督導職責仍召回不足。', '',
f"短口語總平均 {d['metrics_by_style']['short']['latency']['mean_ms']:.1f} ms 高於正式 {d['metrics_by_style']['formal']['latency']['mean_ms']:.1f} ms，部分源於更多題進 LLM。僅比較 answer，短口語平均 {d['answered_latency']['short']['mean_ms']:.1f} ms、正式 {d['answered_latency']['formal']['mean_ms']:.1f} ms，未見一致平均延遲退化；短口語尾端較慢。樣本只有 12 配對，未做統計顯著性推論。", '',
'## 失敗分類','', '|分類|兩輪事件數（可重複）|','|---|---|'])
for k,v in d['failure_counts'].items():lines.append(f'|{k}|{v}|')
lines.extend(['','Knowledge gap=0 不代表 KB 完整：四個刻意不存在的題目正確拒答。其餘失敗題預先確認有現行原文，因此歸為召回／gate／生成／驗證，而不是補知識庫。','','|失敗題|分類|觀察|','|---|---|---|'])
notes={'Q01':'目標段落 top1 命中但未放行。','Q03':'正式清潔問法目標段落 top1 命中但未放行。','Q05':'正式跌倒通報問法已有答案段落但 gate 擋下。','Q07':'正式跌倒回報變體未在 top5 命中目標段落。','Q09':'僅第二輪：居督員記錄責任被錯置於照服員。','Q12':'回傳 answer，但未回答至少七年。','Q13':'家訪題選到紀錄保存段，LLM 回覆 insufficient。','Q14':'短家訪題 top5 有原文但未放行。','Q16':'短電訪題選到案例表單，LLM 回覆 insufficient。','Q23':'答案僅泛談角色，未列主要職責；正確段落未被選入。','Q24':'以督導表單範例概括主要職責，漏掉服務計畫等主要任務。'}
for q in d['unique_failure_questions']:
    cats=sorted({f for r in d['runs'] if r['id']==q for f in r['failure_categories']})
    lines.append(f"|{q}|{'；'.join(cats)}|{notes.get(q,'詳見逐題紀錄')}|")
lines.extend(['','## 完整 tests','',f"{d['full_tests']['total']} 項：{d['full_tests']['total']-d['full_tests']['failures']-d['full_tests']['errors']-d['full_tests']['skipped']} 通過、{d['full_tests']['failures']} 失敗、{d['full_tests']['errors']} errors。`test_version_supersede_and_history`：停用新版本後 expected escalated、actual answered。與上一輪同一失敗，本輪不修。結果存 regression_20261008_tests.xml。",'',
'## 每題摘要（兩輪）','','時間顯示第一輪，完整第二輪與所有原文在 JSON。N/A 表示未進入該階段。','','|ID|問法|問題|expected|actual R1／R2|citation R1／R2|total／retrieve／LLM／verify ms R1|','|---|---|---|---|---|---|---|'])
for c in d['cases']:
    runs=sorted([r for r in d['runs'] if r['id']==c['id']],key=lambda r:r['round']);r=runs[0]
    lines.append(f"|{c['id']}|{c['style']}|{c['question']}|{c['expected_outcome']}|{'／'.join(x['actual_outcome'] for x in runs)}|{'／'.join('N/A' if x['citation_correctness']['passed'] is None else 'PASS' if x['citation_correctness']['passed'] else 'FAIL' for x in runs)}|{'／'.join(ms(r[f]) for f in ['total_latency_ms','retrieval_latency_ms','llm_latency_ms','verification_latency_ms'])}|")
lines.extend(['','## 每題回答、證據與 gate 紀錄',''])
for c in d['cases']:
    lines.extend([f"### {c['id']} {c['question']}",'',f"Expected：{c['expected_outcome']}；預期證據：{c.get('gold_title','N/A')}／{c.get('gold_paragraphs',[])}。",''])
    for r in sorted([x for x in d['runs'] if x['id']==c['id']],key=lambda x:x['round']):
        lines.extend([f"**Round {r['round']}：{r['actual_outcome']} / {r['reason'] or '通過'}**",'',r['answer'] or (r['clarify'] or {}).get('prompt') or r['reason_detail'] or r['reason'] or '—','',f"Top1 document：{r['top1_document'] or '未檢索'}。",'', 'Selected evidence：'+('；'.join(e['ref']+' '+e['title']+' / '+e['locator'] for e in r['selected_evidence']) or '無。'),'',f"Citation：{json.dumps(r['citation_correctness'],ensure_ascii=False)}",''])
        gate=r['retrieval_gate_reason']
        if gate:
            gate_summary=dict(version=gate['version'], admitted_chunk_ids=gate['admitted_chunk_ids'], candidate_count=len(gate['candidates']), top5=[dict(rank=c['rank'], document=c['title'], locator=c['locator'], reason=c['gate']['reason'], admitted=c['gate']['admitted']) for c in r['top5']])
        else: gate_summary=None
        lines.extend(['Gate audit 摘要（完整 candidates 在 JSON）：', '', '```json', json.dumps(gate_summary,ensure_ascii=False,indent=2) if gate_summary else 'null（risk／clarify 階段已結束）','```',''])
        lines.extend([f"Timing total/retrieval/LLM/verify ms：{' / '.join(ms(r[f]) for f in ['total_latency_ms','retrieval_latency_ms','llm_latency_ms','verification_latency_ms'])}。",''])
(ROOT/'docs/regression_20261008.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps(dict(metrics=d['metrics_all_runs'],styles=d['metrics_by_style'],failure_counts=d['failure_counts'],core_unchanged=d['core_unchanged']),ensure_ascii=False,indent=2))
