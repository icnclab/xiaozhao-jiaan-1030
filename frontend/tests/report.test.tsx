import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ReportPage } from '../src/liff/pages/ReportPage';
import candidatePacket from '../../docs/report_template_candidates_20261017.json';
vi.mock('../src/api', () => ({ api: vi.fn(), post: vi.fn(), newRequestId: () => 'isolated-request', errorMessage: () => '連線中斷' }));
vi.mock('../src/liff/components', () => ({ ErrorBox: () => null }));
import { api, post } from '../src/api';
const categories = [
  { id: 'a', name: '分類甲', templates: [{ id: 't-a', text: '測試用問題甲' }] },
  { id: 'b', name: '分類乙', templates: [{ id: 't-b', text: '測試用問題乙' }] },
  { id: 'c', name: '分類丙', templates: [] },
];
afterEach(() => { cleanup(); vi.resetAllMocks(); });
async function open() {
  vi.mocked(api).mockResolvedValue(categories);
  render(<MemoryRouter><ReportPage /></MemoryRouter>);
  await screen.findByRole('button', {name: '分類甲'});
}
function next() { fireEvent.click(screen.getByRole('button', {name: '下一步'})); }
function submit() { fireEvent.click(screen.getByRole('button', {name: '確認送交督導確認'})); }
it('renders only existing questions for the selected category', async () => {
  await open(); fireEvent.click(screen.getByText('分類乙'));
  expect(screen.getByText('測試用問題乙')).toBeTruthy();
  expect(screen.queryByText('測試用問題甲')).toBeNull();
  expect(api).toHaveBeenCalledWith('/api/categories');
  expect(post).not.toHaveBeenCalled();
});
it('shows an explicit empty state and accepts supplemental text', async () => {
  await open(); fireEvent.click(screen.getByText('分類丙'));
  expect(screen.getByText('此分類目前沒有常見問題')).toBeTruthy();
  next();
  expect((screen.getByRole('button', {name: '確認送交督導確認'}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(screen.getByRole('textbox'), {target: {value: '隔離測試文字'}});
  vi.mocked(post).mockRejectedValue(new Error('offline'));
  submit();
  await waitFor(() => expect(post).toHaveBeenCalledWith('/api/cases', expect.objectContaining({category_id: 'c', template_id: null, text: '隔離測試文字'})));
  await screen.findByText(/未能確認送出結果/);
});
it('clears a previous category template when switching categories', async () => {
  await open(); fireEvent.click(screen.getByText('分類甲')); fireEvent.click(screen.getByText('測試用問題甲'));
  fireEvent.click(screen.getByText('上一步')); fireEvent.click(screen.getByText('分類乙')); next();
  expect((screen.getByRole('button', {name: '確認送交督導確認'}) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.queryByText('測試用問題甲')).toBeNull();
});
it('shows the returned case number and real status without claiming supervisor receipt', async () => {
  await open(); fireEvent.click(screen.getByText('分類甲')); fireEvent.click(screen.getByText('測試用問題甲')); next();
  vi.mocked(post).mockResolvedValue({id: 'case-a', number: 'C-test', status_label: '處理中', assignee: null});
  submit(); await screen.findByText('案件已建立');
  expect(screen.getByText(/C-test，處理中/)).toBeTruthy();
  expect(screen.getByText(/不代表督導已讀取或回覆/)).toBeTruthy();
  expect(screen.getByRole('link', {name: '查看案件'}).getAttribute('href')).toBe('/liff/cases/case-a');
  expect(post).toHaveBeenCalledTimes(1);
});
it('does not show success on failure and retries with the same idempotency key', async () => {
  await open(); fireEvent.click(screen.getByText('分類甲')); fireEvent.click(screen.getByText('測試用問題甲')); next();
  vi.mocked(post).mockRejectedValue(new Error('offline'));
  submit(); await screen.findByText(/未能確認送出結果/);
  expect(screen.queryByText('案件已建立')).toBeNull();
  submit(); await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
  expect(vi.mocked(post).mock.calls[0][1]).toEqual(vi.mocked(post).mock.calls[1][1]);
  await screen.findByText(/未能確認送出結果/);
});
it('shows an empty category list explicitly', async () => {
  vi.mocked(api).mockResolvedValue([]);
  render(<MemoryRouter><ReportPage /></MemoryRouter>);
  await screen.findByText('目前沒有可用分類，請聯絡機構督導。');
  expect(post).not.toHaveBeenCalled();
});
it.each([
  [0, '分類與常見問題載入失敗'],
  [500, '分類與常見問題載入失敗'],
  [403, '權限不足'],
  [401, '登入已失效'],
])('distinguishes load failure %s from empty data and allows retry', async (status, message) => {
  vi.mocked(api).mockRejectedValueOnce({status}).mockResolvedValueOnce(categories);
  render(<MemoryRouter><ReportPage /></MemoryRouter>);
  await screen.findByRole('alert');
  expect(screen.getByText(new RegExp(message))).toBeTruthy();
  expect(screen.queryByText(/沒有可用分類|沒有常見問題/)).toBeNull();
  expect(post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', {name: '重新載入'}));
  await screen.findByRole('button', {name: '分類乙'});
  expect(screen.queryByRole('alert')).toBeNull();
});
const candidateCategories = candidatePacket.groups.map((group, i) => ({
  id: `isolated-category-${i}`, name: group.candidate_group, description: null,
  templates: group.questions.map((text, j) => ({ id: `isolated-template-${i}-${j}`, text })),
}));
it.each(candidateCategories.flatMap((category) => category.templates.map((template) => ({ category, template }))))(
  'allows supplementary text with candidate $template.id', async ({ category, template }) => {
    vi.mocked(api).mockResolvedValue(candidateCategories);
    vi.mocked(post).mockResolvedValue({ id: 'isolated-case', number: 'C-isolated', status_label: '待處理', assignee: null });
    render(<MemoryRouter><ReportPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole('button', { name: category.name }));
    fireEvent.click(screen.getByRole('button', { name: template.text }));
    next();
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '隔離測試補充說明' } });
    submit();
    await screen.findByText('案件已建立');
    expect(post).toHaveBeenCalledExactlyOnceWith('/api/cases', expect.objectContaining({
      category_id: category.id, template_id: template.id, text: '隔離測試補充說明',
    }));
  },
);
