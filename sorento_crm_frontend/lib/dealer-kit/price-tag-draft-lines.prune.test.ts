/** A: a click-time message leaves its line as soon as its problem no longer holds. */
import { describe, expect, it } from 'vitest';

import { EMPTY_LINE, MISSING_TAG_TEMPLATE, pruneGuardError } from './price-tag-draft-lines';

describe('pruneGuardError', () => {
  const all = ['No combo list price.', 'Kitchen tap: pick 1 more.', 'SRTKT1 is discontinued.', 'No tag template yet.'];

  it('keeps the messages whose problem still holds', () => {
    expect(pruneGuardError(all.join('\n'), all)).toBe(all.join('\n'));
  });

  it('drops the ones that no longer hold, and clears the line when none is left', () => {
    expect(pruneGuardError(all.join('\n'), ['No combo list price.'])).toBe('No combo list price.');
    expect(pruneGuardError('No combo list price.', [])).toBeNull();
    expect(pruneGuardError(`${EMPTY_LINE}\n${MISSING_TAG_TEMPLATE}`, [MISSING_TAG_TEMPLATE])).toBe(MISSING_TAG_TEMPLATE);
  });

  it('never adds a message, and leaves a refusal the server wrote alone', () => {
    expect(pruneGuardError('X is already on this request.', [])).toBe('X is already on this request.');
    expect(pruneGuardError(null, all)).toBeNull();
  });
});
