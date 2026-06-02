import { describe, it, expect } from 'vitest';

import {
  ERROR_CODE_FRIENDLY,
  summariseFile,
  summariseSession,
} from './translation';
import type {
  SessionAggregate,
  UploadActivityFile,
  UploadActivitySession,
} from './types';

function makeFile(p: Partial<UploadActivityFile>): UploadActivityFile {
  return {
    client_id: 'c1',
    attachment_id: 'a1',
    filename: 'f.jpg',
    status: 'processing',
    summary: '',
    linked: [],
    unlinked_reasons: [],
    error_code: null,
    error_message: null,
    integration_log_id: 'log-1',
    last_updated_at: new Date().toISOString(),
    ...p,
  };
}

function makeSession(
  files: UploadActivityFile[],
  agg: Partial<SessionAggregate> = {},
): UploadActivitySession {
  return {
    session_id: 's1',
    session_type: files.length > 1 ? 'multi' : 'single',
    title: files.length > 1 ? `${files.length} files` : files[0]?.filename ?? 's',
    started_at: new Date().toISOString(),
    finished_at: null,
    status: 'processing',
    aggregate: {
      total: files.length,
      uploading: 0,
      processing: 0,
      linked: 0,
      unlinked: 0,
      failed: 0,
      ...agg,
    },
    files,
    import_job_id: null,
    needs_action: false,
  };
}

describe('translation.ERROR_CODE_FRIENDLY', () => {
  it('covers every error_code surfaced by the backend sweeper / Phase 2 wiring', () => {
    const required = [
      'N8N_CALLBACK_TIMEOUT',
      'MAX_RETRIES_EXCEEDED',
      'HTTP_5XX',
      'HTTP_4XX',
      'WEBHOOK_DISABLED',
      'POST_FAILED',
      'FILE_TOO_LARGE',
    ];
    for (const code of required) {
      expect(ERROR_CODE_FRIENDLY[code], `missing friendly text for ${code}`).toBeTruthy();
    }
  });
});

describe('summariseFile', () => {
  it('describes a linked file with entity name + count', () => {
    const f = makeFile({
      status: 'linked',
      linked: [
        { entity_type: 'product', entity_id: 'p1', display_name: 'CBMC5570', matched_by: 'token' },
        { entity_type: 'product', entity_id: 'p2', display_name: 'CBMC5571', matched_by: 'token' },
      ],
    });
    expect(summariseFile(f)).toMatch(/Linked to 2 products/);
    expect(summariseFile(f)).toMatch(/CBMC5570/);
  });

  it('uses the unlinked reason when available', () => {
    const f = makeFile({
      status: 'unlinked',
      unlinked_reasons: [{ reason: 'No SKU matched' }],
    });
    expect(summariseFile(f)).toBe('No SKU matched');
  });

  it('maps known error codes to friendly text', () => {
    const f = makeFile({ status: 'failed', error_code: 'N8N_CALLBACK_TIMEOUT' });
    expect(summariseFile(f)).toBe(ERROR_CODE_FRIENDLY.N8N_CALLBACK_TIMEOUT);
  });

  it('falls back to error_message when error_code is unknown', () => {
    const f = makeFile({
      status: 'failed',
      error_code: 'WHATEVER_UNKNOWN',
      error_message: 'Server says no',
    });
    expect(summariseFile(f)).toBe('Server says no');
  });

  it('shows "Uploading…" / "Linking…" placeholders for in-flight', () => {
    expect(summariseFile(makeFile({ status: 'uploading' }))).toBe('Uploading…');
    expect(summariseFile(makeFile({ status: 'processing' }))).toBe('Linking…');
  });
});

describe('summariseSession', () => {
  it('delegates to summariseFile when only one file', () => {
    const session = makeSession([
      makeFile({ status: 'linked', linked: [{ entity_type: 'product', entity_id: 'p1', display_name: 'CBMC5570', matched_by: 't' }] }),
    ]);
    expect(summariseSession(session)).toMatch(/Linked to 1 product/);
  });

  it('aggregates counts across multi-file sessions', () => {
    const session = makeSession(
      [
        makeFile({ status: 'linked' }),
        makeFile({ status: 'linked' }),
        makeFile({ status: 'unlinked' }),
        makeFile({ status: 'failed' }),
      ],
      { linked: 2, unlinked: 1, failed: 1 },
    );
    const out = summariseSession(session);
    expect(out).toMatch(/4 files/);
    expect(out).toMatch(/2 linked/);
    expect(out).toMatch(/1 unlinked/);
    expect(out).toMatch(/1 failed/);
  });

  it('shows progress fraction while in-flight', () => {
    const session = makeSession(
      [
        makeFile({ status: 'linked' }),
        makeFile({ status: 'processing' }),
        makeFile({ status: 'processing' }),
      ],
      { linked: 1, processing: 2 },
    );
    expect(summariseSession(session)).toMatch(/1 \/ 3/);
  });
});
