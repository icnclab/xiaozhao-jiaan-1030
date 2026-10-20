import { afterEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AdminCasesPage } from '../src/admin/pages/AdminCasesPage';

vi.mock('../src/api', () => ({ api: vi.fn(), formatTime: (value: string) => value }));
import { api } from '../src/api';

afterEach(() => { cleanup(); vi.clearAllMocks(); });

it('defaults to formal cases and toggles test cases with a visible label', async () => {
  const row = (id: string, is_test: boolean) => ({id, number: id, is_test, status: 'pending',
    status_label: '待處理', source_label: '分類回報', category: null, reason: '', summary_masked: '',
    created_at: '', assignee: null, creator: '同名照服員'});
  vi.mocked(api).mockImplementation(async (path) => {
    const params = new URL(path, 'http://test').searchParams;
    return [row('formal-case', false), ...(params.get('include_test') === 'true' ? [row('test-case', true)] : [])] as never;
  });
  render(<MemoryRouter><AdminCasesPage /></MemoryRouter>);
  await screen.findByText('formal-case');
  const toggle = screen.getByRole('checkbox', {name: '顯示測試案件'}) as HTMLInputElement;
  expect(toggle.checked).toBe(false);
  expect(screen.queryByText('test-case')).toBeNull();
  fireEvent.click(toggle);
  await screen.findByText('test-case');
  expect(screen.getByText('內部測試')).toBeTruthy();
  expect(screen.getByText('formal-case')).toBeTruthy();
  expect(vi.mocked(api).mock.calls.at(-1)?.[0]).toContain('include_test=true');
  fireEvent.click(screen.getByRole('checkbox', {name: '只看指派給我'}));
  await waitFor(() => expect(vi.mocked(api).mock.calls.at(-1)?.[0]).toContain('mine=true'));
  fireEvent.click(toggle);
  await waitFor(() => expect(screen.queryByText('test-case')).toBeNull());
  expect(vi.mocked(api).mock.calls.at(-1)?.[0]).toContain('include_test=false');
  fireEvent.click(screen.getByRole('button', {name: '重新整理'}));
  await screen.findByText('formal-case');
  expect(vi.mocked(api).mock.calls.at(-1)?.[0]).toContain('include_test=false');
  expect(vi.mocked(api).mock.calls.at(-1)?.[1]?.cache).toBe('no-store');
});

it('ignores an older test-inclusive reply arriving after the checkbox is cleared', async () => {
  const pending: Array<(rows: unknown[]) => void> = [];
  vi.mocked(api).mockImplementation(() => new Promise(resolve => pending.push(resolve as (rows: unknown[]) => void)));
  render(<MemoryRouter><AdminCasesPage /></MemoryRouter>);
  await act(async () => pending[0]([]));
  const toggle = screen.getByRole('checkbox', {name: '顯示測試案件'});
  fireEvent.click(toggle);
  fireEvent.click(toggle);
  expect(vi.mocked(api).mock.calls.at(-1)?.[0]).toContain('include_test=false');
  await act(async () => pending[2]([]));
  await act(async () => pending[1]([{id: 'late-test', number: 'late-test', is_test: true, status: 'replied'}]));
  expect(screen.queryByText('late-test')).toBeNull();
});
