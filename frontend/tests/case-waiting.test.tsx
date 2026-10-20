import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { CaseDetailPage } from '../src/liff/pages/CaseDetailPage';
vi.mock('../src/api', () => ({ api: vi.fn(), post: vi.fn(), newRequestId: () => 'isolated-request', formatTime: () => '' }));
vi.mock('../src/liff/components', () => ({ ErrorBox: () => null }));
import { api, post } from '../src/api';
afterEach(() => { cleanup(); vi.resetAllMocks(); });
it.each([
  ['caregiver', null, true],
  ['supervisor', null, false],
  ['admin', null, false],
  ['caregiver', '2026-10-17T00:00:00Z', false],
])('shows waiting according to reply evidence (%s, %s)', async (author_role, first_replied_at, waiting) => {
  vi.mocked(api).mockResolvedValue({ id: 'existing', number: 'C-isolated', status: 'pending', status_label: '待處理',
    source_label: '分類回報', summary_masked: '', reason: '', first_replied_at,
    messages: [{id: 'm', author_role, author_name: '測試代稱', body: '隔離內容'}] });
  render(<MemoryRouter initialEntries={['/liff/cases/existing']}><Routes>
    <Route path='/liff/cases/:id' element={<CaseDetailPage />} />
  </Routes></MemoryRouter>);
  await screen.findByText('C-isolated');
  expect(!!screen.queryByText('督導尚未回覆，請等待處理。')).toBe(waiting);
  expect(api).toHaveBeenCalledWith('/api/cases/existing');
  expect(post).not.toHaveBeenCalled();
});
