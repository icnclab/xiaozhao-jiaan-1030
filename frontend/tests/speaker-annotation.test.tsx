import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { TranscriptPage } from '../src/liff/pages/TranscriptPage';
import { setToken } from '../src/api';

const draftTranscript = () => ({
  id: 't1', status: 'draft', mode: 'conversation', channel: 'liff',
  audio_duration_ms: 6000, error_code: null, error_message: null,
  draft_expires_at: '2026-11-03T00:00:00Z', audio_deleted: true, roles: {},
  summary_masked: null, stt_provider: 'mock', stt_ms: 10,
  segments: [
    { idx: 0, start_ms: 0, end_ms: 2000, speaker: 'unknown', text: '阿嬤說她今天不想洗澡', uncertain: false, masked: false },
    { idx: 1, start_ms: 2000, end_ms: 4000, speaker: 'unknown', text: '家屬要我們多餵一餐', uncertain: true, masked: false },
    { idx: 2, start_ms: 4000, end_ms: 6000, speaker: 'unknown', text: '我先記下來再問督導', uncertain: false, masked: false },
  ],
});
const confirmed = (body: unknown) => ({ ...draftTranscript(), status: 'confirmed', ...(body as object) });
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockImplementation(async (path: string) => {
    if (path === '/api/transcripts/t1') return response(draftTranscript());
    throw new Error(`Unexpected request blocked: ${path}`);
  });
  vi.stubGlobal('fetch', fetchMock);
  setToken('isolated-test-only');
});
afterEach(() => { cleanup(); setToken(null); vi.unstubAllGlobals(); vi.clearAllMocks(); });

function open() {
  render(<MemoryRouter initialEntries={['/liff/record/t1']}><Routes>
    <Route path="/liff/record/:id" element={<TranscriptPage />} />
  </Routes></MemoryRouter>);
}
const confirmPosts = () => fetchMock.mock.calls.filter(([p, init]) => p === '/api/transcripts/t1/confirm' && init?.method === 'POST');

// Role mapping is a manual button grid (btn role-btn, aria-pressed), not a
// <select> -- no automatic voiceprint/speaker-ID is ever involved. Locates
// the role-grid for a given speaker label (e.g. "說話者 1") by its sibling
// <span>, scoped with `within` so multiple speakers' grids never collide.
async function roleGridFor(speakerLabel: string) {
  // The same text (e.g. "說話者 1") also appears as an <option> in each
  // segment's speaker <select>; scope to the role-mapping section's own
  // <span class="small"> so the query is unambiguous.
  const label = await screen.findByText(speakerLabel, { selector: 'span.small' });
  return within(label.parentElement!.querySelector('.role-grid')!);
}

it('supports tagging segments across all eight speakers plus unknown', async () => {
  open();
  await screen.findAllByText(/阿嬤說她今天不想洗澡/);
  const selects = screen.getAllByRole('combobox');
  const options = Array.from(selects[0].querySelectorAll('option')).map(o => (o as HTMLOptionElement).value);
  expect(options).toEqual(['unknown', 'speaker_1', 'speaker_2', 'speaker_3', 'speaker_4', 'speaker_5', 'speaker_6', 'speaker_7', 'speaker_8']);
});

it('offers unidentified/caregiver/supervisor/elder/family/other as role choices', async () => {
  // Role mapping is a manual button grid (btn role-btn), by design -- the
  // system never guesses a speaker's role from voice/audio; the choices are
  // still exactly the six roles below, offered as buttons instead of a
  // dropdown.
  open();
  await screen.findAllByText(/阿嬤說她今天不想洗澡/);
  const speakerSelect = screen.getAllByRole('combobox')[0];
  fireEvent.change(speakerSelect, { target: { value: 'speaker_1' } });
  const roleGrid = await roleGridFor('說話者 1');
  const labels = roleGrid.getAllByRole('button').map((b) => b.textContent);
  expect(labels).toEqual(['照服員', '居督', '長輩', '家屬', '其他', '未辨識']);
});

it('does not auto-submit on load and never claims saved before explicit confirm', async () => {
  open();
  await screen.findAllByText(/阿嬤說她今天不想洗澡/);
  expect(confirmPosts()).toHaveLength(0);
  const speakerSelect = screen.getAllByRole('combobox')[0];
  fireEvent.change(speakerSelect, { target: { value: 'speaker_1' } });
  expect(screen.getByRole('alert').textContent).toMatch(/修改尚未儲存/);
  expect(confirmPosts()).toHaveLength(0);
});

it('warns that unsaved speaker/role edits are not yet synced to the backend', async () => {
  open();
  await screen.findAllByText(/阿嬤說她今天不想洗澡/);
  expect(screen.queryByRole('alert')).toBeNull();
  fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'speaker_1' } });
  expect(screen.getByRole('alert').textContent).toMatch(/離開或重新整理會遺失/);
});

it('shows the mapped role inline next to a tagged segment before confirming', async () => {
  open();
  await screen.findAllByText(/阿嬤說她今天不想洗澡/);
  fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'speaker_1' } });
  const roleGrid = await roleGridFor('說話者 1');
  fireEvent.click(roleGrid.getByRole('button', { name: '居督' }));
  expect(await screen.findByText('（居督）')).toBeTruthy();
});

it('sends explicit segment text/speaker edits and role map only after the confirm button is clicked', async () => {
  fetchMock.mockImplementation(async (path: string, init?: RequestInit) => {
    if (path === '/api/transcripts/t1' && (!init || init.method === undefined)) return response(draftTranscript());
    if (path === '/api/transcripts/t1/confirm' && init?.method === 'POST') {
      return response(confirmed(JSON.parse(String(init.body))));
    }
    throw new Error(`Unexpected request blocked: ${path}`);
  });
  open();
  await screen.findAllByText(/阿嬤說她今天不想洗澡/);
  fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'speaker_1' } });
  const textbox = screen.getAllByRole('textbox')[0];
  fireEvent.change(textbox, { target: { value: '阿嬤說她今天想洗澡' } });
  const roleGrid = await roleGridFor('說話者 1');
  fireEvent.click(roleGrid.getByRole('button', { name: '居督' }));
  expect(confirmPosts()).toHaveLength(0);
  fireEvent.click(screen.getByRole('button', { name: /確認送出/ }));
  await waitFor(() => expect(confirmPosts()).toHaveLength(1));
  const body = JSON.parse(String(confirmPosts()[0][1]?.body));
  expect(body.roles).toEqual({ speaker_1: 'supervisor' });
  expect(body.segments).toEqual([{ idx: 0, speaker: 'speaker_1', text: '阿嬤說她今天想洗澡' }]);
});
