/**
 * A random RFC 4122 v4 id for client-side use (React keys, batch ids, row ids).
 *
 * `crypto.randomUUID` exists only in a SECURE context (https or localhost); on a
 * plain-http origin, the owner's tailnet test URLs among them, it is undefined and
 * calling it throws. `crypto.getRandomValues` has no such restriction, so the
 * fallback builds the same v4 shape from it. Math.random is a last resort for a
 * runtime with no Web Crypto at all; none of these ids is a secret.
 */
export function randomId(): string {
  const c = typeof crypto !== 'undefined' ? crypto : undefined;
  if (c && typeof c.randomUUID === 'function') return c.randomUUID();

  const bytes = new Uint8Array(16);
  if (c && typeof c.getRandomValues === 'function') {
    c.getRandomValues(bytes);
  } else {
    for (let i = 0; i < 16; i += 1) bytes[i] = Math.floor(Math.random() * 256);
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant 10xx
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
