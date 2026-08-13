import { describe, it, expect } from 'vitest';

import type { FormRevisionEntry } from '@/components/common/RevisionTimeline';
import {
  hasRevisionLineage,
  revisionDocumentNumber,
  revisionExportFilename,
  revisionFileMarker,
  revisionInfoRows,
  revisionSheetName,
  revisionSubmittedLine,
  revisionsNewestFirst,
  sanitizeSheetName,
  uniqueSheetName,
} from './revision-export';

function entry(overrides: Partial<FormRevisionEntry> = {}): FormRevisionEntry {
  return {
    id: 'rev-1',
    version_no: 1,
    revision_no: 1,
    kind: 'revision',
    label: 'Revision 1',
    reason: 'Wrong quantity',
    submitted_at: '2026-08-12T02:00:00',
    submitted_by: 'Alice Tan',
    snapshot: {},
    attachments: [],
    changes: [],
    ...overrides,
  };
}

describe('revision document number', () => {
  it('reads the version its OWN snapshot stored, suffixed', () => {
    expect(
      revisionDocumentNumber(
        entry({ revision_no: 2, snapshot: { inquiry_number: 'SI-26-0184' } }),
        'inquiry_number',
      ),
    ).toBe('SI-26-0184-R2');
  });

  it('falls back to the live number only when the snapshot never stored one', () => {
    expect(revisionDocumentNumber(entry({ revision_no: 1 }), 'inquiry_number', 'SI-26-0184')).toBe(
      'SI-26-0184-R1',
    );
    expect(revisionDocumentNumber(entry({ revision_no: 0, kind: 'original' }), 'inquiry_number', 'SI-26-0184')).toBe(
      'SI-26-0184',
    );
  });
});

describe('revision file marker', () => {
  it('marks every stored version, one word, never stacked', () => {
    expect(revisionFileMarker(entry({ revision_no: 2 }))).toBe('as-submitted');
    expect(revisionFileMarker(entry({ kind: 'original', revision_no: 0 }))).toBe('original');
    expect(
      revisionFileMarker(entry({ kind: 'resubmission', version_no: 3, revision_no: 1 })),
    ).toBe('resubmitted-v3');
  });
});

describe('revision export filename', () => {
  it('names the file after THAT version, never the record plus a second marker', () => {
    expect(
      revisionExportFilename('Stock_Inquiry', entry({ revision_no: 1 }), 'SI-26-0184-R1'),
    ).toBe('Stock_Inquiry_SI-26-0184-R1-as-submitted.xlsx');
  });

  it('never collides with the live record export of the same revision', () => {
    // The record sits at R2 and its own export is `Stock_Inquiry_SI-26-0184-R2`.
    // That document carries live office fields the snapshot cannot, so the two
    // must not land in a downloads folder under one name.
    expect(
      revisionExportFilename('Stock_Inquiry', entry({ revision_no: 2 }), 'SI-26-0184-R2'),
    ).toBe('Stock_Inquiry_SI-26-0184-R2-as-submitted.xlsx');
  });

  it('keeps version 0 apart from the current form of an unrevised record', () => {
    expect(
      revisionExportFilename(
        'Purchase_Request',
        entry({ kind: 'original', revision_no: 0 }),
        'PR-26-0007',
      ),
    ).toBe('Purchase_Request_PR-26-0007-original.xlsx');
  });

  it('drops the characters a filename must not carry, and copes with no number', () => {
    expect(revisionExportFilename('Stock_Inquiry', entry(), 'SI/26 0184-R1')).toBe(
      'Stock_Inquiry_SI260184-R1-as-submitted.xlsx',
    );
    expect(revisionExportFilename('Stock_Inquiry', entry(), null)).toBe(
      'Stock_Inquiry-as-submitted.xlsx',
    );
  });
});

describe('sheet names', () => {
  it('drops the characters Excel rejects and caps at 31', () => {
    expect(sanitizeSheetName('Revision 1 [draft]: a/b\\c*?')).toBe('Revision 1 draft a b c');
    expect(sanitizeSheetName('x'.repeat(40))).toHaveLength(31);
    expect(sanitizeSheetName('   ')).toBe('Revision');
  });

  it('never repeats a name inside one workbook', () => {
    const taken = new Set<string>();
    expect(uniqueSheetName('Revision 1', taken)).toBe('Revision 1');
    expect(uniqueSheetName('Revision 1', taken)).toBe('Revision 1 (2)');
  });

  it('names a sheet after the entry label', () => {
    expect(revisionSheetName(entry({ label: 'Revision 2' }), new Set())).toBe('Revision 2');
  });
});

describe('revision identification rows', () => {
  it('says which version, why, and when it was sent', () => {
    expect(revisionInfoRows(entry())).toEqual([
      ['Revision:', 'Revision 1'],
      ['Reason:', 'Wrong quantity'],
      ['Submitted:', '12/08/2026 by Alice Tan'],
    ]);
  });

  it('shouts the labels when the sheet it joins does', () => {
    expect(revisionInfoRows(entry(), { uppercase: true })[0]).toEqual([
      'REVISION:',
      'Revision 1',
    ]);
  });

  it('omits the reason row when there is none, exactly as the PDF does', () => {
    const rows = revisionInfoRows(entry({ kind: 'original', label: 'Original', reason: null }));
    expect(rows.map((row) => row[0])).toEqual(['Revision:', 'Submitted:']);
  });

  it('reads the submitted line with whichever half it has', () => {
    expect(revisionSubmittedLine(entry({ submitted_by: null }))).toBe('12/08/2026');
    expect(revisionSubmittedLine(entry({ submitted_at: null }))).toBe('Alice Tan');
  });
});

describe('lineage', () => {
  it('is nothing when the record is only its original submission', () => {
    expect(hasRevisionLineage([])).toBe(false);
    expect(hasRevisionLineage([entry({ kind: 'original', revision_no: 0 })])).toBe(false);
  });

  it('counts a second entry even at revision 0 (a resubmit after rejection)', () => {
    expect(
      hasRevisionLineage([
        entry({ id: 'a', revision_no: 0 }),
        entry({ id: 'b', revision_no: 0 }),
      ]),
    ).toBe(true);
  });

  it('prints newest first', () => {
    const oldest = entry({ id: 'a', revision_no: 0 });
    const newest = entry({ id: 'b', revision_no: 1 });
    expect(revisionsNewestFirst([oldest, newest]).map((e) => e.id)).toEqual(['b', 'a']);
  });
});
