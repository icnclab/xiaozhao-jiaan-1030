import { describe, it, expect } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { publicLabel, publicMessage, publicDisplayText, SYSTEM_FAILURE } from '../src/publicText';
import { TraceSummary } from '../src/quality/FeedbackReviewContext';
import { errorMessage } from '../src/api';

describe('plain Chinese and safe fallback for every role', () => {
  it.each(['risk_fall_head_impact', 'risk_environmental_safety', 'respiratory_abnormality',
    'consciousness_abnormality', 'sudden_neurologic_abnormality', 'medication_selection',
    'no_evidence', 'clarification', 'RISK_RULES', 'CLARIFICATION_RULES', 'Gold',
    'regression', 'proxy', 'retrieval', 'evidence admission', 'unknown_rule_id'])('translates %s', code => {
    expect(publicLabel(code)).not.toContain(code);
    expect(publicDisplayText(`結果：${code}`)).not.toContain(code);
  });
  it.each(['Traceback Python exception', '資料庫錯誤 psycopg', 'DB error code internal_rule_id', 'Internal Server Error'])('hides %s', text => {
    expect(publicMessage(text)).toBe(SYSTEM_FAILURE);
    expect(errorMessage(new Error(text))).toBe(SYSTEM_FAILURE);
  });
  it.each(['caregiver', 'supervisor', 'admin'])('hides internal diagnostics from %s', role => {
    render(<TraceSummary role={role} snapshot={{ sources: [], runtime: {
      risk_gate_result: { codes: ['fall_head_impact', 'environmental_safety'] },
      escalation_result: { outcome: 'escalate', reason: 'no_evidence' }, traceback: 'secret',
    } }} />);
    expect(screen.getByText('命中：跌倒或頭部碰撞風險、環境安全風險')).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/risk_|no_evidence|secret|traceback/);
    cleanup();
  });
  it('retains useful Chinese validation', () => {
    expect(publicMessage('請輸入問題')).toBe('請輸入問題');
  });
});
