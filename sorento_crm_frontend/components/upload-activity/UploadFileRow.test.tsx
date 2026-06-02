import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { UploadManagerProvider } from './UploadManagerContext';
import { UploadFileRow } from './UploadFileRow';
import type { UploadActivityFile } from './types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

function makeFile(p: Partial<UploadActivityFile> = {}): UploadActivityFile {
  return {
    client_id: 'c1',
    attachment_id: 'a1',
    filename: 'photo.jpg',
    status: 'processing',
    summary: '',
    linked: [],
    unlinked_reasons: [],
    error_code: null,
    error_message: null,
    integration_log_id: 'l1',
    last_updated_at: new Date().toISOString(),
    ...p,
  };
}

function renderRow(file: UploadActivityFile) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <UploadManagerProvider>
        <UploadFileRow sessionId="s1" file={file} />
      </UploadManagerProvider>
    </QueryClientProvider>,
  );
}

describe('UploadFileRow', () => {
  it('renders filename + friendly summary for linked files', () => {
    renderRow(
      makeFile({
        status: 'linked',
        linked: [
          {
            entity_type: 'product',
            entity_id: 'p1',
            display_name: 'CBMC5570',
            matched_by: 'token',
          },
        ],
      }),
    );
    expect(screen.getByText('photo.jpg')).toBeTruthy();
    expect(screen.getByText(/Linked to 1 product/)).toBeTruthy();
    expect(screen.getByText(/CBMC5570/)).toBeTruthy();
  });

  it('shows a Retry button when status=post_failed', () => {
    renderRow(makeFile({ status: 'post_failed', error_code: 'POST_FAILED' }));
    expect(screen.getByRole('button', { name: /retry/i })).toBeTruthy();
  });

  it('does not show Retry for terminal "linked" rows', () => {
    renderRow(makeFile({ status: 'linked' }));
    expect(screen.queryByRole('button', { name: /retry/i })).toBeNull();
  });

  it('shows the unlinked reason when status=unlinked', () => {
    renderRow(
      makeFile({
        status: 'unlinked',
        unlinked_reasons: [{ reason: 'No SKU matched filename' }],
      }),
    );
    expect(screen.getByText(/No SKU matched filename/)).toBeTruthy();
  });
});
