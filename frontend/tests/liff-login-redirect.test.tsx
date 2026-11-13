import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { PublicConfig } from '../src/api';

// XZ_LIFF_REDIRECT_PATH_V1 regression: login() must send the user back to the page
// they were actually on (e.g. /liff/ask), not always to the bare /liff home tab.
const sdk = vi.hoisted(() => ({
  init: vi.fn(async () => undefined),
  isLoggedIn: vi.fn(() => false),
  getIDToken: vi.fn(() => 'test-line-id-token'),
  login: vi.fn(),
}));
vi.mock('@line/liff', () => ({ default: sdk }));

const config = {
  line_mode: 'real', liff_id: 'test-liff-id', dev_features: false, modes: { line: 'real' },
  bot_name: '小照', wake_words: ['小照'],
  limits: { question_max_sec: 60, conversation_max_sec: 600, max_upload_mb: 30 },
} as unknown as PublicConfig;

describe('loginWithLiff redirect path', () => {
  beforeEach(() => {
    sdk.isLoggedIn.mockReturnValue(false);
    sdk.login.mockClear();
    vi.useFakeTimers();
  });

  it('preserves the current deep path (e.g. /liff/ask), not just /liff', async () => {
    window.history.pushState({}, '', '/liff/ask?x=1');
    const { loginWithLiff } = await import('../src/liff/auth');
    const pending = loginWithLiff(config);
    await vi.waitFor(() => expect(sdk.login).toHaveBeenCalled());
    expect(sdk.login).toHaveBeenCalledWith({ redirectUri: `${window.location.origin}/liff/ask?x=1` });
    vi.advanceTimersByTime(12000);
    await expect(pending).rejects.toMatchObject({ code: 'liff_redirect_timeout' });
    vi.useRealTimers();
  });
});
