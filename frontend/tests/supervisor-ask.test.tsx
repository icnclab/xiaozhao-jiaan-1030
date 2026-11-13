import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { LiffContext } from '../src/liff/LiffApp';
import { SupervisorAskPage } from '../src/liff/pages/SupervisorAskPage';

afterEach(cleanup);

function mountAs(role: string) {
  const user = { id: 'u1', username: 'u1', display_name: '測試居督', role,
    org: { id: 'org1', name: '測試機構', facility_type: 'home' } };
  const config = { line_mode: 'mock', liff_id: '', dev_features: true, modes: { line: 'mock' },
    bot_name: '小照', wake_words: ['小照'],
    limits: { question_max_sec: 60, conversation_max_sec: 600, max_upload_mb: 30 } };
  const router = createMemoryRouter([{ path: '/', element: (
    <LiffContext.Provider value={{ config: config as never, user: user as never, dev: false, logout: () => {} }}>
      <SupervisorAskPage />
    </LiffContext.Provider>
  ) }]);
  return render(<RouterProvider router={router} />);
}

describe('SupervisorAskPage', () => {
  it('blocks caregiver role with a clear message, not the AI form', () => {
    mountAs('caregiver');
    expect(screen.getByText(/僅提供督導、主任或管理員使用/)).toBeTruthy();
    expect(screen.queryByText('督導 AI 助手')).toBeNull();
  });

  it('allows supervisor and defaults to voice mode (not the text textarea)', () => {
    mountAs('supervisor');
    expect(screen.getByText('督導 AI 助手')).toBeTruthy();
    expect(screen.getByText(/返回督導工作台/)).toBeTruthy();
    expect(screen.queryByLabelText('輸入想查詢的規範或案件處置問題')).toBeNull();
    expect(screen.queryByText(/STT=/)).toBeNull();
  });

  it('allows director, and switching to text mode shows the textarea', () => {
    mountAs('director');
    expect(screen.getByText('主任 AI 助手')).toBeTruthy();
    fireEvent.click(screen.getByText('⌨️ 文字輸入'));
    expect(screen.getByLabelText('輸入想查詢的規範或案件處置問題')).toBeTruthy();
  });

  it('allows admin with the shared UI while showing the admin-specific title', () => {
    mountAs('admin');
    expect(screen.getByText('管理員 AI 助手')).toBeTruthy();
    expect(screen.queryByLabelText('輸入想查詢的規範或案件處置問題')).toBeNull();
  });
});
