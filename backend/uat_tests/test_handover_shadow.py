from types import SimpleNamespace
import pytest
from app.services.mpc_handover_shadow import analyze_synthetic,_core

def settings(uat=True,enabled=True):return SimpleNamespace(is_uat=uat,uat_handover_mpc_enabled=enabled)
def test_default_disabled_and_production_refused():
    for s in [settings(enabled=False),settings(uat=False)]:
        with pytest.raises(RuntimeError):analyze_synthetic(s,[],synthetic=True)
def test_real_data_and_unbounded_input_refused():
    with pytest.raises(ValueError):analyze_synthetic(settings(),[],synthetic=False)
    with pytest.raises(ValueError):analyze_synthetic(settings(),[{}]*101,synthetic=True)
def test_identity_claim_is_not_authorization():
    p=analyze_synthetic(settings(),[{'speaker_id':'speaker_1','text':'今天要確認服務時段。','role':'admin'}],synthetic=True)
    assert p['requires_human_confirmation'] and p['requires_safety_review']
    assert not p['saved'] and not p['case_created'] and not p['notification_sent'] and p['automatic_actions']==[]
    assert p['authorization_source']=='existing_server_auth_only'
def test_all_five_handover_scenarios_use_existing_preview_boundary():
    scenarios=_core().build_5_benchmark_scenarios();assert len(scenarios)==5
    for scenario in scenarios:
        segments=[{'speaker_id':t.speaker_id,'text':t.text,'timestamp':t.timestamp} for t in scenario.turns]
        p=analyze_synthetic(settings(),segments,synthetic=True)
        assert p['requires_human_confirmation'] and not p['notification_sent'] and not p['case_created']
