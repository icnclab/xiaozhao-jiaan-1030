"""Observation only: no retrieval, gate, policy or provider configuration changes."""
import hashlib
import inspect
import json
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def versions():
    from app.providers.llm import SYSTEM_PROMPT, build_user_prompt
    root = Path(__file__).resolve().parents[1]
    files = sorted((root / 'services').glob('*.py')) + sorted((root / 'providers').glob('*.py'))
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    prompt = hashlib.sha256((SYSTEM_PROMPT + '\n' + inspect.getsource(build_user_prompt)).encode()).hexdigest()
    return {'rag_version': 'source-sha256:' + digest.hexdigest(), 'prompt_version': 'sha256:' + prompt,
            'version_kind': 'derived_source_fingerprint'}


def capture(state):
    from app.providers.embedding import get_embedding_provider
    from app.services.retrieval import _expand_query
    policy = state['policy']
    checks = state.get('checks', {})
    ran_retrieval = 'retrieved' in state
    provider = get_embedding_provider()
    result = dict(versions(), normalized_query=state.get('question_masked'),
                  # The same deterministic expansion used by retrieve; no provider call.
                  expanded_query=_expand_query(state['question_masked'], state['today']) if ran_retrieval else None,
                  expanded_query_provenance='deterministic_reconstruction_at_qa_assembly; not instrumented SQL query',
                  retrieval_executed=ran_retrieval,
                  retrieval_candidates=[dict(asdict(c), lexical_score=c.coverage,
                                             vector_score=c.vector, rerank_score=None,
                                             ranking_score=c.combined) for c in state.get('retrieved', [])],
                  candidate_k=policy.candidate_k, top_k=policy.top_k,
                  adjacency_expansion={'evidence_focus':checks.get('evidence_focus'),
                                       'administrative_scope_context':checks.get('administrative_scope_context'),
                                       'evidence_selection':checks.get('evidence_selection')},
                  evidence_gate_result=checks.get('retrieval_gate'),
                  risk_gate_result={'executed':'risk_codes' in state,'codes':state.get('risk_codes')},
                  escalation_result={'outcome':state.get('outcome'),'reason':state.get('reason')},
                  embedding_provider=provider.name, embedding_model=provider.model,
                  qa_policy_version=policy.version,
                  safety_policy_version=policy.safety_version,
                  clarification_policy_version=policy.clarification_version,
                  clarification_result=checks.get('clarification'))
    return json.loads(json.dumps(result, default=str))


def historical(item):
    trace = (item.checks or {}).get('rag_trace')
    if trace is not None:
        return trace
    checks = item.checks or {}
    return dict(rag_version=None, prompt_version=None, qa_policy_version=item.qa_policy_version,
                normalized_query=item.question_masked, expanded_query=None,
                retrieval_candidates=checks.get('retrieval'), candidate_k=None, top_k=None,
                adjacency_expansion={'evidence_focus':checks.get('evidence_focus'),
                                     'administrative_scope_context':checks.get('administrative_scope_context')},
                evidence_gate_result=checks.get('retrieval_gate'),
                risk_gate_result={'codes':checks.get('risk_codes')},
                escalation_result={'outcome':item.outcome,'reason':item.escalation_reason},
                embedding_provider=item.embedding_provider, embedding_model=None,
                unavailable=['rag_version','prompt_version','expanded_query','candidate_k','top_k',
                             'embedding_model','complete_retrieval_scores','rerank_score'],
                provenance='historical_persisted_fields_only; no reconstruction or current-value backfill')
