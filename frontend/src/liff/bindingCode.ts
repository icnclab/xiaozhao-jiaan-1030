/** Formatting only: never guess or remove invalid visible characters. */
export function normalizeBindingCode(value: string): string {
  return value.normalize("NFKC").replace(/[\s\u200B-\u200D\u2060\uFEFF]/gu, "").toUpperCase();
}
export function validBindingCode(value: string): boolean {
  return /^[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{8}$/.test(value);
}
