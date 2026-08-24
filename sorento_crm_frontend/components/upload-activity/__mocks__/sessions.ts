/**
 * Phase 1 mock fixtures for Upload Activity drawer.
 *
 * Seeded session data covering every state the FE must render.
 * Removed in Phase 2 when the real `/api/v1/resources/upload-activity`
 * endpoint replaces these via React Query.
 *
 * Test note (Phase 2): re-export these from a shared `__mocks__/`
 * folder so vitest can reuse them in component tests.
 */

import type { UploadActivityFile, UploadActivitySession } from '../types';

const now = () => new Date().toISOString();
const minutesAgo = (n: number) =>
  new Date(Date.now() - n * 60_000).toISOString();
const hoursAgo = (n: number) =>
  new Date(Date.now() - n * 3_600_000).toISOString();

export const MOCK_SESSIONS: UploadActivitySession[] = [
  // 1. In-flight single upload (POST done, n8n pending)
  {
    session_id: 'mock-session-single-inflight',
    session_type: 'single',
    title: 'receipt-2026-06-02.pdf',
    started_at: minutesAgo(1),
    finished_at: null,
    status: 'processing',
    aggregate: {
      total: 1,
      uploading: 0,
      processing: 1,
      linked: 0,
      unlinked: 0,
      failed: 0,
    },
    needs_action: false,
    import_job_id: null,
    files: [
      {
        client_id: 'mock-file-1',
        attachment_id: 'mock-att-1',
        filename: 'receipt-2026-06-02.pdf',
        status: 'processing',
        summary: '',
        linked: [],
        unlinked_reasons: [],
        error_code: null,
        error_message: null,
        integration_log_id: 'mock-log-1',
        last_updated_at: minutesAgo(1),
      },
    ],
  },

  // 2. Multi-file modal upload - mixed outcomes (3 linked, 1 unlinked, 1 failed)
  {
    session_id: 'mock-session-multi-mixed',
    session_type: 'multi',
    title: '5 files',
    started_at: minutesAgo(15),
    finished_at: minutesAgo(13),
    status: 'partial',
    aggregate: {
      total: 5,
      uploading: 0,
      processing: 0,
      linked: 3,
      unlinked: 1,
      failed: 1,
    },
    needs_action: true,
    import_job_id: null,
    files: [
      {
        client_id: 'mock-file-2a',
        attachment_id: 'mock-att-2a',
        filename: 'CBFAL5570_1.jpg',
        status: 'linked',
        summary: '',
        linked: [
          {
            entity_type: 'product',
            entity_id: 'p1',
            display_name: 'CBMC5570',
            matched_by: 'filename_token:CBMC5570',
          },
        ],
        unlinked_reasons: [],
        error_code: null,
        error_message: null,
        integration_log_id: 'mock-log-2a',
        last_updated_at: minutesAgo(13),
      },
      {
        client_id: 'mock-file-2b',
        attachment_id: 'mock-att-2b',
        filename: 'CBFAL5570_2.jpg',
        status: 'linked',
        summary: '',
        linked: [
          {
            entity_type: 'product',
            entity_id: 'p1',
            display_name: 'CBMC5570',
            matched_by: 'filename_token:CBMC5570',
          },
          {
            entity_type: 'product',
            entity_id: 'p2',
            display_name: 'CBFAL5570',
            matched_by: 'filename_token:CBFAL5570',
          },
        ],
        unlinked_reasons: [],
        error_code: null,
        error_message: null,
        integration_log_id: 'mock-log-2b',
        last_updated_at: minutesAgo(13),
      },
      {
        client_id: 'mock-file-2c',
        attachment_id: 'mock-att-2c',
        filename: 'CBFAL5569_15.jpg',
        status: 'linked',
        summary: '',
        linked: [
          {
            entity_type: 'product',
            entity_id: 'p3',
            display_name: 'CBFAL5569',
            matched_by: 'filename_token:CBFAL5569',
          },
        ],
        unlinked_reasons: [],
        error_code: null,
        error_message: null,
        integration_log_id: 'mock-log-2c',
        last_updated_at: minutesAgo(14),
      },
      {
        client_id: 'mock-file-2d',
        attachment_id: 'mock-att-2d',
        filename: 'random-photo.jpg',
        status: 'unlinked',
        summary: '',
        linked: [],
        unlinked_reasons: [
          { reason: "No SKU matched filename token 'random-photo'" },
        ],
        error_code: null,
        error_message: null,
        integration_log_id: 'mock-log-2d',
        last_updated_at: minutesAgo(14),
      },
      {
        client_id: 'mock-file-2e',
        attachment_id: 'mock-att-2e',
        filename: 'broken.jpg',
        status: 'failed',
        summary: '',
        linked: [],
        unlinked_reasons: [],
        error_code: 'N8N_CALLBACK_TIMEOUT',
        error_message: null,
        integration_log_id: 'mock-log-2e',
        last_updated_at: minutesAgo(13),
      },
    ],
  },

  // 3. Bulk ZIP - 50 files, mostly linked, 3 in needs-attention
  {
    session_id: 'mock-session-bulk-zip',
    session_type: 'bulk_zip',
    title: 'brand_2026.zip',
    started_at: hoursAgo(1),
    finished_at: hoursAgo(1),
    status: 'partial',
    aggregate: {
      total: 50,
      uploading: 0,
      processing: 0,
      linked: 47,
      unlinked: 2,
      failed: 1,
    },
    needs_action: true,
    import_job_id: 'mock-job-zip-1',
    files: [
      // representative subset - Phase 2 will paginate via virtual scroll
      ...Array.from({ length: 47 }, (_, i) => ({
        client_id: `mock-file-zip-linked-${i}`,
        attachment_id: `mock-att-zip-l-${i}`,
        filename: `CBFAL${5500 + i}.jpg`,
        status: 'linked' as const,
        summary: '',
        linked: [
          {
            entity_type: 'product',
            entity_id: `pz${i}`,
            display_name: `CBMC${5500 + i}`,
            matched_by: `filename_token:CBMC${5500 + i}`,
          },
        ],
        unlinked_reasons: [],
        error_code: null,
        error_message: null,
        integration_log_id: `mock-log-zip-l-${i}`,
        last_updated_at: hoursAgo(1),
      })),
      {
        client_id: 'mock-file-zip-u-1',
        attachment_id: 'mock-att-zip-u-1',
        filename: 'orphan-photo-1.jpg',
        status: 'unlinked',
        summary: '',
        linked: [],
        unlinked_reasons: [{ reason: 'No SKU matched filename' }],
        error_code: null,
        error_message: null,
        integration_log_id: 'mock-log-zip-u-1',
        last_updated_at: hoursAgo(1),
      },
      {
        client_id: 'mock-file-zip-u-2',
        attachment_id: 'mock-att-zip-u-2',
        filename: 'orphan-photo-2.jpg',
        status: 'unlinked',
        summary: '',
        linked: [],
        unlinked_reasons: [{ reason: 'No SKU matched filename' }],
        error_code: null,
        error_message: null,
        integration_log_id: 'mock-log-zip-u-2',
        last_updated_at: hoursAgo(1),
      },
      {
        client_id: 'mock-file-zip-f-1',
        attachment_id: 'mock-att-zip-f-1',
        filename: 'corrupt.jpg',
        status: 'failed',
        summary: '',
        linked: [],
        unlinked_reasons: [],
        error_code: 'HTTP_5XX',
        error_message: 'n8n returned 502 Bad Gateway',
        integration_log_id: 'mock-log-zip-f-1',
        last_updated_at: hoursAgo(1),
      },
    ],
  },

  // 4. Past successful single upload (no badge contribution)
  {
    session_id: 'mock-session-past-success',
    session_type: 'single',
    title: 'product-spec.pdf',
    started_at: hoursAgo(20),
    finished_at: hoursAgo(20),
    status: 'linked',
    aggregate: {
      total: 1,
      uploading: 0,
      processing: 0,
      linked: 1,
      unlinked: 0,
      failed: 0,
    },
    needs_action: false,
    import_job_id: null,
    files: [
      {
        client_id: 'mock-file-4',
        attachment_id: 'mock-att-4',
        filename: 'product-spec.pdf',
        status: 'linked',
        summary: '',
        linked: [
          {
            entity_type: 'product',
            entity_id: 'p4',
            display_name: 'CBMC1234',
            matched_by: 'manual',
          },
        ],
        unlinked_reasons: [],
        error_code: null,
        error_message: null,
        integration_log_id: 'mock-log-4',
        last_updated_at: hoursAgo(20),
      },
    ],
  },

  // 5. POST-failed single (FE-only state, retry available)
  {
    session_id: 'mock-session-post-failed',
    session_type: 'single',
    title: 'too-big.zip',
    started_at: minutesAgo(2),
    finished_at: minutesAgo(2),
    status: 'failed',
    aggregate: {
      total: 1,
      uploading: 0,
      processing: 0,
      linked: 0,
      unlinked: 0,
      failed: 1,
    },
    needs_action: true,
    import_job_id: null,
    files: [
      {
        client_id: 'mock-file-5',
        attachment_id: null,
        filename: 'too-big.zip',
        status: 'post_failed',
        summary: '',
        linked: [],
        unlinked_reasons: [],
        error_code: 'FILE_TOO_LARGE',
        error_message: '25 MB exceeds 20 MB limit',
        integration_log_id: null,
        last_updated_at: minutesAgo(2),
      },
    ],
  },
];

/**
 * Mock log payload returned by getMockIntegrationLogForAttachment.
 * Used by AttachmentDetailModal Integration card during Phase 1.
 */
export function getMockIntegrationLogForAttachment(
  attachmentId: string,
): UploadActivitySession['files'][number] | null {
  for (const session of MOCK_SESSIONS) {
    const match = session.files.find(
      (f: UploadActivityFile) => f.attachment_id === attachmentId,
    );
    if (match) return match;
  }
  return null;
}
