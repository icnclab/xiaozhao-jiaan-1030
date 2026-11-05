import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { DynamicForm } from '../src/liff/components/DynamicForm';
import type { Jiaan1030FormSection } from '../src/api';

afterEach(() => { cleanup(); });

// 鏡射 backend/app/services/jiaan1030_ga09_sc09_fields.py 的 ga09_sc09_v2_fields()。
// 依 docs/jiaan1030_forms/678412_0.jpg、678413_0.jpg 紙本原件修復的欄位結構。
// 必填、字數上限等細節未確認，一律保守預設（required=false），不自行編造。
const GA09_SC09_V2_SECTIONS: Jiaan1030FormSection[] = [
  {
    key: 'basic', label: '基本資訊', fields: [
      { key: 'district', label: '區別（里別／轄區，必填條件待確認）', type: 'text', required: false, max_length: 50 },
      { key: 'ltc_level', label: '長照等級（必填條件待確認）', type: 'radio', required: false, options: ['1', '2', '3', '4', '5', '6', '7', '8'] },
      { key: 'welfare_status', label: '福利身分（必填條件待確認）', type: 'radio', required: false, options: ['一般', '中低收入', '低收入'] },
      { key: 'service_type', label: '服務類型（必填條件待確認）', type: 'select', required: false, options: ['GA09', 'SC09'], option_labels: ['GA09－居家喘息服務', 'SC09－居家短照服務'] },
      { key: 'service_date', label: '服務日期（必填條件待確認）', type: 'date', required: false },
      { key: 'start_time', label: '開始時間（24小時制，必填條件待確認）', type: 'time', required: false },
      { key: 'end_time', label: '結束時間（24小時制，必填條件待確認）', type: 'time', required: false },
    ],
  },
  {
    key: 'service_content', label: '服務內容（依紙本13項勾選，必填條件待確認）', fields: [
      {
        key: 'service_items', label: '服務項目（可複選）', type: 'checkbox_group', required: false,
        options: ['協助如廁', '協助沐浴', '穿換衣服', '口腔清潔', '協助進食', '協助服藥', '翻身、拍背',
          '協助上下床', '陪同運動', '簡單被動式肢體關節活動', '協助使用日常生活輔助器具',
          '護理照護（限日照／機構）', '活動安排'],
      },
      { key: 'other_service_note', label: '其他服務（補充文字，字數上限待確認，暫訂保守值）', type: 'textarea', required: false, max_length: 500 },
    ],
  },
  {
    key: 'signature', label: '簽章', fields: [
      { key: 'signature', label: '簽章欄位（紙本為案主/親屬、照顧服務員、居服督導員三方簽章；電子化簽署方式待嘉安確認，本系統暫不收集簽章資料）', type: 'signature_placeholder', required: false },
    ],
  },
];

function renderForm(payload: Record<string, unknown> = {}, onChange = vi.fn()) {
  render(<DynamicForm sections={GA09_SC09_V2_SECTIONS} payload={payload} onChange={onChange} />);
  return onChange;
}

it('renders all 10 v2 GA09/SC09 fields with the correct input types', () => {
  renderForm();
  expect(screen.getByText(/服務類型/)).toBeTruthy();
  const options = screen.getAllByRole('option').map((o) => o.textContent);
  expect(options).toContain('GA09－居家喘息服務');
  expect(options).toContain('SC09－居家短照服務');

  expect(screen.getByText(/服務日期/)).toBeTruthy();
  expect(document.querySelector('input[type="date"]')).toBeTruthy();

  expect(screen.getByText(/開始時間/)).toBeTruthy();
  expect(screen.getByText(/結束時間/)).toBeTruthy();
  expect(document.querySelectorAll('input[type="time"]').length).toBe(2);

  expect(screen.getByText(/區別/)).toBeTruthy();
  expect(screen.getByText(/長照等級/)).toBeTruthy();
  expect(screen.getByText(/福利身分/)).toBeTruthy();

  // 13 項服務內容勾選 + 8 級長照等級 + 3 種福利身分，皆以大面積按鈕呈現
  expect(screen.getByText('協助如廁')).toBeTruthy();
  expect(screen.getByText('陪同運動')).toBeTruthy();
  expect(screen.getByText(/其他服務/)).toBeTruthy();
  expect(document.querySelector('textarea')).toBeTruthy();

  // 簽章欄位：目前僅佔位提示，不應出現任何輸入控件收集簽章資料
  expect(screen.getByText(/簽章欄位尚未實作/)).toBeTruthy();
});

it('does not mark any field as required (未確認必填條件時一律保守預設)', () => {
  renderForm();
  expect(screen.queryByText('必填')).toBeNull();
});

it('toggles checkbox_group items without losing other selections', () => {
  const onChange = renderForm({ service_items: ['協助如廁'] });
  fireEvent.click(screen.getByText('陪同運動'));
  expect(onChange).toHaveBeenCalledWith({ service_items: ['協助如廁', '陪同運動'] });
});

it('selects a radio-button field by clicking a large tap target', () => {
  const onChange = renderForm({});
  fireEvent.click(screen.getByText('5'));
  expect(onChange).toHaveBeenCalledWith({ ltc_level: '5' });
});

it('calls onChange with the field key when a value changes, without losing other fields', () => {
  const onChange = renderForm({ service_type: 'GA09' });
  fireEvent.change(document.querySelector('input[type="date"]')!, { target: { value: '2026-11-01' } });
  expect(onChange).toHaveBeenCalledWith({ service_type: 'GA09', service_date: '2026-11-01' });
});

it('disables inputs when the draft is already submitted', () => {
  render(<DynamicForm sections={GA09_SC09_V2_SECTIONS} payload={{}} onChange={vi.fn()} disabled />);
  expect((document.querySelector('input[type="date"]') as HTMLInputElement).disabled).toBe(true);
  expect((document.querySelector('textarea') as HTMLTextAreaElement).disabled).toBe(true);
  expect((screen.getByText('協助如廁') as HTMLButtonElement).disabled).toBe(true);
});
