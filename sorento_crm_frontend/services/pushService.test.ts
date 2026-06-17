import { describe, it, expect } from 'vitest';
import { isPushSupported, getPushState, subscribeToPush, unsubscribeFromPush } from './pushService';

// jsdom has no serviceWorker/PushManager -> all guards return false, never throw.
describe('pushService (TCK-33) unsupported environment', () => {
  it('isPushSupported is false in jsdom', () => {
    expect(isPushSupported()).toBe(false);
  });
  it('getPushState returns false', async () => {
    expect(await getPushState()).toBe(false);
  });
  it('subscribeToPush returns false (no throw)', async () => {
    expect(await subscribeToPush()).toBe(false);
  });
  it('unsubscribeFromPush returns false (no throw)', async () => {
    expect(await unsubscribeFromPush()).toBe(false);
  });
});
