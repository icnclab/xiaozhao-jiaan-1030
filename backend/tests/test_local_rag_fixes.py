import uuid
from types import SimpleNamespace
from app.services.query_understanding import topic_token_groups, _legacy_topic_token_groups, clarification_reason
from app.services.evidence_selection import prioritize_admitted, field_support, answers_requested_value
from app.services.role_consistency import check_roles
from app.services.qa_graph import node_verify
from app.services.qa_policy import DEFAULT_POLICY
from app.providers.llm import CandidateAnswer

def c(text):
    return SimpleNamespace(chunk_id=uuid.uuid4(), text=text)

def test_functional_permission_variants_share_topic():
    base=topic_token_groups('照服員可以清潔傷口嗎？')
    for frame in ['是否可','是否可以','可否','能否','能不能']:
        assert topic_token_groups('照服員'+frame+'執行清潔傷口？')==base

def test_unknown_topic_and_conditions_preserved():
    assert topic_token_groups('是否可執行火星護盾校準？')
    assert topic_token_groups('可以清潔感染傷口嗎？')!=topic_token_groups('可以清潔傷口嗎？')

def test_clarify_uses_legacy_topics():
    assert clarification_reason('這個傷口我可以自己處理嗎？')=='unspecified_action'
    assert _legacy_topic_token_groups('這個是否可？')
    assert clarification_reason('這個是否可？') is None

def test_admitted_value_gets_slot_without_increasing_top_k():
    wrong=c('服務紀錄應依相關法規留存。')
    correct=c('服務紀錄應保存至少七年。')
    unadmitted=c('服務紀錄保存十年。')
    chosen, facts=prioritize_admitted('服務紀錄要留幾年？',[wrong,correct],[wrong,unadmitted],1)
    assert chosen==[correct] and facts==[str(correct.chunk_id)]

def test_adjacent_cannot_displace_admitted_fact():
    top=c('家訪紀錄应保存七年。')
    correct=c('家訪紀錄評估重點如下：1. 身心狀況 2. 家庭支持。')
    neighbor=c('一般表單。')
    selected,_=prioritize_admitted('家訪要記哪些重點？',[top,correct],[top,neighbor],2)
    assert selected==[correct,top]

def test_questions_without_field_keep_existing_selection():
    top=c('督導應追蹤服務。'); other=c('其他流程。')
    selected,_=prioritize_admitted('督導怎麼追蹤服務？',[top,other],[top],5)
    assert selected==[top]

def test_unrelated_number_not_field_support():
    assert not field_support('服務紀錄要留幾年？','每月督導一次。服務紀錄應留存。')
    assert not answers_requested_value('服務紀錄要留幾年？','服務紀錄應依規定留存。',['服務紀錄應保存七年。'])
    assert answers_requested_value('服務紀錄要留幾年？','服務紀錄應保存七年。',['服務紀錄應保存七年。'])
    assert answers_requested_value('服務紀錄要留幾年？','服務紀錄應保存7年。',['服務紀錄應保存七年。'])
    assert not answers_requested_value('服務紀錄要留幾年？','保存10年。',['服務紀錄應保存七年。表單案例發生於10年後。'])

def test_frequency_value_selection():
    assert field_support('督導會議多久一次？','督導會議每月至少一次。')

def test_retention_requires_time_unit_not_person_count():
    text='相關服務紀錄應依規定留存，學習照顧者應為同一人。'
    assert not field_support('服務紀錄要留幾年？',text)
    assert not answers_requested_value('服務紀錄要留幾年？','服務紀錄保存一人。',[text])

def test_role_aliases_and_recipient_not_subject():
    assert check_roles('照顧服務員應維持角色界線。',['照服員應維持角色界線。'])['passed']
    assert check_roles('督導應詳實記錄溝通過程。',['請居家服務督導員詳實記錄溝通過程。'])['passed']
    assert check_roles('照服員應建議家屬向機構反應額外需求。',['照服員應建議家屬向機構反應額外需求。'])['passed']
    source='照服員應維持角色界線。在尊重家屬需求與保護自身權益之下取得平衡，應委婉拒絕，建議家屬向機構反應額外需求，另購服務項目。請居督員詳實記錄發生時間與溝通過程。'
    assert check_roles('照服員應維持角色界線，並委婉拒絕，建議家屬向機構反應額外需求，另購服務項目。',[source])['passed']
    assert not check_roles('照服員應委婉拒絕，同時應詳實記錄發生時間與溝通過程。',[source])['passed']

def test_inherited_actor_mismatch_even_both_roles_present():
    source='照服員應維持角色界線。請居督員詳實記錄發生時間與溝通過程。'
    claim='照服員應維持角色界線，同時應詳實記錄發生時間與溝通過程。'
    assert not check_roles(claim,[source])['passed']
    assert check_roles('照服員應維持角色界線。督導應詳實記錄發生時間與溝通過程。',[source])['passed']
    assert not check_roles('照服員負責記錄發生時間與溝通過程。',[source])['passed']
    assert not check_roles('照服員記錄發生時間與溝通過程。',[source])['passed']

def test_real_role_mismatch_is_blocked_by_verify():
    source='照服員應維持角色界線。請居督員詳實記錄發生時間與溝通過程。'
    evidence=SimpleNamespace(text=source,title='服務界線',locator='第1段')
    candidate=CandidateAnswer(claims=[dict(text='照服員應維持角色界線，同時應詳實記錄發生時間與溝通過程。',citation_refs=['E1'])])
    result=node_verify(dict(policy=DEFAULT_POLICY,candidate=candidate,evidence_map={'E1':evidence},question_masked='服務界線規定？',checks={}))
    assert result['outcome']=='escalate'
    assert result['checks']['claims'][0]['reject_reason']=='role_mismatch'
