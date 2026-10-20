"""Inventory source/runtime settings without calling embedding/LLM or changing DB."""
import hashlib
import inspect
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.config import get_settings
from app.providers import embedding, llm
from app.services import ingest, retrieval, retrieval_gate, query_understanding, qa_graph, qa_policy, evidence_selection, care_query, documents


def location(module, marker):
    path = Path(module.__file__)
    lines = path.read_text(encoding='utf-8').splitlines()
    return f'{path.relative_to(ROOT).as_posix()}:{next(i for i, line in enumerate(lines, 1) if marker in line)}'


def generate():
    s = get_settings()
    p = qa_policy.DEFAULT_POLICY
    ep = embedding.get_embedding_provider()  # construction only, never embed()
    rows = []
    def add(pid, layer, name, value, module, marker, classification='C', configurable=False, space=None, notes=''):
        metrics = {'ingest':['retrieval recall@k','evidence precision'],
                   'retrieval':['retrieval recall@k','false refusal rate','evidence precision'],
                   'gate':['false refusal rate','unsafe answer rate'],
                   'risk':['risk recall','risk false positive rate','unsafe answer rate'],
                   'answer':['answer correctness','citation correctness','escalation accuracy'],
                   'query':['retrieval recall@k','false refusal rate']}.get(layer, ['answer correctness'])
        rows.append(dict(parameter_id=pid,layer=layer,name=name,current_value=value,
                         code_location=location(module,marker),configurable=configurable,
                         possible_search_space=space if space is not None else
                             {'mode':'numeric_offline','values':[value],'expand_only_after_verified_dataset':True}
                             if classification=='A' else {'mode':'manual_design','baseline_only':value},
                         metric_affected=metrics,optimization_goal='提升證據與答案正確性，並受安全／轉人工限制；不以回答率最大化。',
                         change_risk='high' if classification in ('C','D') else 'medium',classification=classification,
                         notes=notes+' search space 是未來離線候選設計，並非目前允許的 production 修改。'))
    add('chunk.target','ingest','段落目標字數',ingest.TARGET_PARA_CHUNK,ingest,'TARGET_PARA_CHUNK =','A',False,[300,400,500],'字符而非 token；頁面／標題／條文可提前切塊；需離線重建索引。')
    add('chunk.max','ingest','長段落句界切分目標',ingest.MAX_CHUNK_CHARS,ingest,'MAX_CHUNK_CHARS =','A',False,[500,700,900],'不是嚴格上限：單一超長句仍可能超過，標題／條號也增加字數。')
    add('chunk.overlap','ingest','正文滑動 overlap',0,ingest,'def _split_long','B',False,[0],'沒有 sliding overlap；可能重複標題，不等於正文 overlap。')
    add('embedding.provider','embedding','實際 provider',ep.name,embedding,'def get_embedding_provider','D',True,{'allowed_now':[ep.name]})
    add('embedding.model','embedding','實際向量模型',ep.model,embedding,'self.model = f','D',True,{'allowed_now':[ep.model]},'hash provider 忽略設定中的 EMBEDDING_MODEL。')
    add('embedding.configured_model','embedding','設定中的 model',s.embedding_model,embedding,'settings.embedding_model','D',True,{'allowed_now':[s.embedding_model]})
    add('embedding.dimension','embedding','向量維度',s.embedding_dim,embedding,'self.dim = dim','D',True,{'allowed_now':[s.embedding_dim]},'DB vector(1024)；不可自動改。')
    for name in ['candidate_k','top_k','lexical_weight','min_top_coverage','min_combined','min_evidence_score','min_support','min_gate_vector','min_gate_body_topic','min_gate_title_topic','min_gate_rule_topic']:
        group='A' if name in ('candidate_k','top_k','lexical_weight','min_top_coverage','min_combined','min_evidence_score') else 'D'
        space={'candidate_k':[25,50,75,100],'top_k':[3,5,7],'lexical_weight':[0.45,0.55,0.65]}.get(name)
        layer='retrieval' if group=='A' else 'answer' if name=='min_support' else 'gate'
        add('policy.'+name,layer,name,getattr(p,name),qa_policy,name+':',group,False,space,
            'QaPolicy 可作離線實例覆寫；production 沒有環境變數旋鈕。candidate_k 是每個 lexical/vector 通道上限，合併標題及 adjacency 後候選總數可能超過。' if name=='candidate_k' else '共享門檻；禁止單題／全域盲目降低。')
    add('retrieval.vector_weight','retrieval','向量權重',1-p.lexical_weight,retrieval,'combined = policy.lexical_weight','A',False,{'derived_from':'1-policy.lexical_weight'},'不得與 lexical 權重独立搜尋。')
    add('retrieval.hybrid','retrieval','原始與正規化 scoring',{'raw':'lexical_weight*coverage+(1-lexical_weight)*max(vector,0)','normalized':'lexical_weight*normalized_coverage+(1-lexical_weight)*max(vector,0)','rank':'max(raw,normalized)+title_bonus+intent_bonus'},retrieval,'hybrid_score = combined','C',False,notes='不是 RRF；lexical coverage 使用 IDF 加權原問句 bigrams。')
    for name in ['ABSENT_TOKEN_FACTOR','EXACT_TITLE_BONUS','FUZZY_TITLE_BONUS_WEIGHT','FUZZY_TITLE_MIN_COVERAGE','PERMISSION_INTENT_BONUS']:
        add('ranking.'+name.lower(),'retrieval',name,getattr(retrieval,name),retrieval,name+' =','A')
    add('ranking.intent_conditions','retrieval','意圖 bonus 條件',inspect.getsource(retrieval._ranking_bonuses),retrieval,'def _ranking_bonuses','C')
    add('retrieval.title_candidates','retrieval','標題候選',{'minimum_overlap_bigrams':2,'minimum_title_coverage':0.35,'document_chunks':'all eligible chunks of matched document'},retrieval,'if overlap >= 2','C')
    add('retrieval.reranking','retrieval','reranking',{'model':None,'algorithm':'heuristic combined score; medication scope+drug flag first, then combined DESC'},retrieval,'results.sort','B',False,{'baseline':['heuristic_no_cross_encoder']},'無獨立 reranker model 或 rerank score；combined 是排序分。')
    add('adjacency.service_span','retrieval','代購表相鄰候選',{'anchor_to_seq_plus':4,'maximum_chunks':5,'stop':'next BA code','eligibility':'same eligible version; explicit purpose includes drugs; no injection'},retrieval,"'b': anchor.seq + 4",'C')
    add('adjacency.answer_focus','answer','同文件相鄰證據',{'distance':'ORDER BY ABS(seq-anchor.seq), seq','limit':'policy.top_k','exclude_intents':'permission/reporting/record','body_topic_threshold':p.min_gate_body_topic},qa_graph,'elif focus_same_document:','C')
    add('answer.focus_min','answer','同文件 focus 分數',0.45,qa_graph,'top.combined >= 0.45','A',False,[0.4,0.45,0.5])
    add('answer.focus_margin','answer','同文件 focus 分差',0.05,qa_graph,'>= 0.05','A',False,[0.03,0.05,0.08])
    add('gate.reporting_threshold','gate','通報 evidence 門檻',{'dedicated_numeric_threshold':None,'shared_procedure_topic_min':p.min_gate_rule_topic,'explicit_frontline_route':'care_reporting AND reporting_duty(body), prior to base numeric signal'},retrieval_gate,'elif care_duty:','D',notes='不能報成另有 reporting=0.8 門檻；一般通報用共享0.8，明確第一線責任為規則通道。')
    add('gate.intent_routes','gate','意圖專用 evidence matching',inspect.getsource(retrieval_gate.assess_evidence),retrieval_gate,'def assess_evidence','D')
    add('gate.rule_window','gate','同句規範證據視窗',{'stride_chars':160,'window_chars':320},retrieval_gate,'range(0, len(sentence), 160)','C')
    add('risk.medication_and_other','risk','risk gate 規則',[{'code':r.code,'pattern':r.pattern.pattern} for r in p.risk_rules],qa_policy,'RISK_RULES:','D',notes='risk input 與 output 均檢查；不許自動調整／繞過。')
    add('query.normalization','query','query normalization',inspect.getsource(query_understanding.normalize_colloquial),query_understanding,'def normalize_colloquial','C')
    add('query.context','query','administrative follow-up normalization',inspect.getsource(query_understanding.contextual_question),query_understanding,'def contextual_question','C')
    add('query.action_aliases','query','query aliases',query_understanding.ACTION_ALIASES,query_understanding,'ACTION_ALIASES =','C')
    add('query.expansion','query','候選 query expansion',inspect.getsource(retrieval._expand_query),retrieval,'def _expand_query','C')
    add('query.intent_aliases','query','局部 intent aliases',inspect.getsource(query_understanding.candidate_aliases),query_understanding,'def candidate_aliases','C')
    add('answer.evidence_selection','answer','answer evidence selection',inspect.getsource(evidence_selection.prioritize_admitted),evidence_selection,'def prioritize_admitted','C',notes='另有 frontline reporting／BA service scope 優先選取；不提高 top_k。')
    add('answer.validation','answer','answer validation',inspect.getsource(qa_graph.node_verify),qa_graph,'def node_verify','D')
    add('documents.eligibility','retrieval','文件版本及機構隔離',inspect.getsource(documents.current_versions),documents,'def current_versions','D')
    add('prompt.version','answer','正式 prompt version',None,llm,'SYSTEM_PROMPT =','D',notes='原程式沒有具名 prompt version；不可捏造。Phase1 trace 用內容 SHA256 派生 fingerprint，不代表既有歷史 QA 已有版本。')
    add('prompt.fingerprint','answer','目前 prompt fingerprint','sha256:'+hashlib.sha256((llm.SYSTEM_PROMPT+'\n'+inspect.getsource(llm.build_user_prompt)).encode()).hexdigest(),llm,'SYSTEM_PROMPT =','D',notes='system prompt + user prompt builder source；派生值。')
    add('policy.version','answer','qa_policy_version',p.version,qa_policy,'version: str =','D')
    add('llm.options','answer','實際生成設定',{'temperature':0,'num_ctx':6144,'num_predict':400,'think':False,'format':'ANSWER_SCHEMA'},llm,'"options": {"temperature"','B',False,{'baseline_only':{'temperature':0,'num_ctx':6144,'num_predict':400}},'未開始比較生成設定。')
    return dict(schema_version=1,generated_at=datetime.now(ZoneInfo('Asia/Taipei')).isoformat(),
                scope='aa source + resolved runtime settings; not a claim that an existing server has reloaded files',
                classification_legend={'A':'可數值搜尋（僅未來離線）','B':'可離散比較','C':'規則型，需要人工設計','D':'不建議自動調整'},parameters=rows)


if __name__ == '__main__':
    registry = generate()
    out = ROOT / 'quality_tests/optimization'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'parameters.json').write_text(json.dumps(registry,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# RAG Optimization Parameter Registry','',
           '從目前 aa 程式與已解析 runtime 設定盤點；未修改任何參數。機器可讀完整值、規則正文、search space 及備註見 `quality_tests/optimization/parameters.json`。',
           'A=未來離線數值搜尋；B=離散比較；C=人工規則設計；D=不建議自動調整。建議 search space 不是 production 現值。',
           '實際 hash embedding model 與設定 EMBEDDING_MODEL 不同；沒有 cross-encoder reranker 或獨立 rerank score。prompt 原本沒有具名版本，Phase1 只新增派生 fingerprint。', '',
           '| parameter_id | 層 | 現值／規則 | 分類 | 可設定 | 程式位置 |','|---|---|---|---|---|---|']
    for r in registry['parameters']:
        value=json.dumps(r['current_value'],ensure_ascii=False)
        value=(value[:140]+'…') if len(value)>140 else value
        lines.append(f'| {r["parameter_id"]} | {r["layer"]} | {value.replace(chr(124), "／").replace(chr(10), " ")} | {r["classification"]} | {r["configurable"]} | {r["code_location"]} |')
    lines += ['',f'共 {len(registry["parameters"])} 項。', '',
              '可搜尋項需先具備 verified dataset、固定 KB snapshot 與隔離實驗環境。醫療風險、引用支持門檻、機構隔離、版本及 injection 防護維持安全約束；不得為提高回答率盲目放寬。',
              'chunk 長度變更需要離線重新切塊／建立索引，不得在 production 就地覆寫；vector weight 從 lexical weight 派生，不能作獨立維度。']
    (ROOT / 'docs/rag_optimization_parameter_registry.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('parameters',len(registry['parameters']))
