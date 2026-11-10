import { describe, expect, it } from 'vitest';
import { quotationSaveBlockedReason } from './quotationSaveBlocked';

// UIUX-QUICK-WINS item 5: a disabled Save says why, in plain words, under the button.
describe('quotationSaveBlockedReason', () => {
  const ready = {
    viewOnly: false,
    discarding: false,
    failed: false,
    loading: false,
    letterReady: true,
    columnsBusy: false,
  };

  it('nothing blocks: no reason', () => {
    expect(quotationSaveBlockedReason(ready)).toBeNull();
  });

  it.each([
    ['viewOnly', 'This draft is open somewhere else. Reload to edit it here.'],
    ['discarding', 'This draft is being discarded.'],
    ['failed', 'This quotation could not be loaded.'],
    ['loading', 'Still loading the quotation.'],
    ['columnsBusy', 'Waiting for the column change to finish.'],
  ] as const)('%s', (key, reason) => {
    expect(quotationSaveBlockedReason({ ...ready, [key]: true })).toBe(reason);
  });

  it('the cover letter still loading', () => {
    expect(quotationSaveBlockedReason({ ...ready, letterReady: false })).toBe(
      'Still loading the cover letter.',
    );
  });

  it('the first reason wins: open elsewhere before anything else', () => {
    expect(quotationSaveBlockedReason({ ...ready, viewOnly: true, loading: true })).toBe(
      'This draft is open somewhere else. Reload to edit it here.',
    );
  });
});
