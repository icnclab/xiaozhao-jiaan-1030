"""UAT synthetic-only adapter for the 2026-11-07 handover; no live routing.
Reuses the existing reviewer preview boundary. Speaker labels are suggestions,
never authenticated roles. No DB, RAG, notifications or automatic case creation.
"""
from pathlib import Path
import importlib.util,math,re,sys
from app.services.mpc_handover import build_preview

def _core():
    name='xiaozhao_reviewed_handover_20261107'
    if name not in sys.modules:
        source=Path(__file__).resolve().parents[3]/'tools/approved_sync/handover_review/mpc_core.py'
        spec=importlib.util.spec_from_file_location(name,source)
        module=importlib.util.module_from_spec(spec);sys.modules[name]=module
        try:spec.loader.exec_module(module)
        except Exception:sys.modules.pop(name,None);raise
    return sys.modules[name]

def analyze_synthetic(settings,segments,*,synthetic=False):
    if not settings.is_uat or not settings.uat_handover_mpc_enabled:
        raise RuntimeError('UAT_HANDOVER_MPC_DISABLED')
    if synthetic is not True:raise ValueError('SYNTHETIC_REVIEW_ONLY')
    if not isinstance(segments,list) or not 1<=len(segments)<=100:raise ValueError('INVALID_SEGMENTS')
    rows=[]
    for i,row in enumerate(segments,1):
        if not isinstance(row,dict):raise ValueError('INVALID_SEGMENT')
        text=row.get('text');speaker=row.get('speaker_id');timestamp=row.get('timestamp',i)
        if not isinstance(text,str) or not text.strip() or len(text)>2000:raise ValueError('INVALID_TEXT')
        if not isinstance(speaker,str) or not re.fullmatch(r'speaker_[0-9]{1,3}',speaker):raise ValueError('PSEUDONYMOUS_SPEAKER_REQUIRED')
        if type(timestamp) not in (float,int) or not math.isfinite(timestamp) or timestamp<0:raise ValueError('INVALID_TIMESTAMP')
        rows.append((i,float(timestamp),speaker,text))
    core=_core();session=core.DialogueSessionState(session_id='SYNTHETIC_UAT',case_id='SYNTHETIC_ONLY')
    session.turns=[core.UtteranceTurn(turn_id=i,timestamp=t,speaker_id=speaker,inferred_role='unknown',text=text) for i,t,speaker,text in rows]
    result=core.XiaoZhaoMPCEngine().analyze_session(session)
    p0=any('P0' in str(x) for x in result.get('detected_intents',[])) or str(result.get('route_target','')).startswith('0E_')
    selected=result['selected_turn_indices']
    if not selected:raise ValueError('EMPTY_PREVIEW_SELECTION')
    role_map={'caregiver':'CAREGIVER','caregiver_照服員':'CAREGIVER','supervisor_居督':'SUPERVISOR','family':'FAMILY','elder':'ELDER'}
    payload={'client_event_id':result['client_event_id'],'fsm_state':'SOS_1_Alerting_All_Supervisors' if p0 else 'Waiting_LINE_Confirm',
        'segments':[{'idx':i,'masked_text':text,'predicted_role':'UNKNOWN','safety_flag':'TIER1_SOS' if p0 else 'UNKNOWN'} for i,t,speaker,text in rows],
        'selected_idx':selected,'summary':' '.join(text for i,t,speaker,text in rows if i in selected)[:3000],
        'slot_state':result.get('dst_slots',{}),'active_intents':['P0_Emergency_SOS'] if p0 else ['QA_RAG_Query'],
        'roles':{speaker:role_map.get(role,'UNKNOWN') for speaker,role in result.get('speaker_roles',{}).items()},'work_summary_draft':{}}
    preview=build_preview(payload)
    preview.update(review_only=True,requires_safety_review=True,automatic_actions=[],authorization_source='existing_server_auth_only',
        shadow_route_suggestion=result.get('route_target'),shadow_intent_suggestions=result.get('detected_intents',[]))
    return preview
