/**
 * SPEC-SHEET-PARITY-B2 v3 fix round, review S3: "Every page" carries the new style flags. Written
 * test-FIRST.
 */
import { describe, expect, it } from 'vitest';

import type { TagLayerProps } from '@/lib/dealer-kit/tag-template-types';
import { applicableChanges } from './selectionTools';

describe('Every page carries ALL CAPS and Header row (review S3)', () => {
  it('ALL CAPS (uppercase) goes to every page', () => {
    expect(applicableChanges(null, { uppercase: true } as Partial<TagLayerProps>)).toEqual({ props: { uppercase: true } });
  });

  it('Header row (headerRow) goes to every page', () => {
    expect(applicableChanges(null, { headerRow: false } as Partial<TagLayerProps>)).toEqual({ props: { headerRow: false } });
  });

  it('a whole table change sends only its style flags, never its cells', () => {
    const sent = applicableChanges(null, {
      kind: 'table',
      headerRow: true,
      cells: [[{ text: 'x' }]],
    } as unknown as Partial<TagLayerProps>);
    expect(sent).toEqual({ props: { headerRow: true } });
  });
});
