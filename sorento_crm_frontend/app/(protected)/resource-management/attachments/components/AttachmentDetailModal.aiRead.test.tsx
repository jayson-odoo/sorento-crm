/**
 * AttachmentDetailModal - the "Read by AI" row (AGENTIC-KNOWLEDGE P1, AC-K11, AC-K20, D1, D3).
 *
 * Resources > Files opens this modal, so the row must live here too, not only on the detail page.
 * The assertions are those of AttachmentDetail.aiRead.test.tsx, run against the modal.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { UploadManagerProvider } from '@/components/upload-activity';

vi.mock('@/hooks/usePermissions', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/hooks/usePermissions')>()),
  useHasPermission: () => true,
}));

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/resource-management/attachments',
}));

const net = vi.hoisted(() => ({
  getAttachmentMetadata: vi.fn(),
  apiFetch: vi.fn(),
}));

vi.mock('../services/attachmentService', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../services/attachmentService')>()),
  getAttachmentMetadata: (...args: unknown[]) => net.getAttachmentMetadata(...args),
}));

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiFetch: (...args: unknown[]) => net.apiFetch(...args),
}));

vi.mock('../hooks/useAttachments', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useAttachments')>();
  const idle = () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false });
  return {
    ...actual,
    useDownloadAttachment: idle,
    useResubmitAttachmentWebhook: idle,
    useRestoreAttachment: idle,
    useUpdateAttachment: idle,
    useDeleteAttachment: idle,
    useArchiveAttachment: idle,
  };
});

vi.mock(
  '@/app/(protected)/master-data-management/product-attachments/hooks/useProductAttachments',
  () => {
    const idle = () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false });
    return { useCreateProductAttachment: idle, useDeleteProductAttachment: idle };
  },
);

vi.mock(
  '@/app/(protected)/marketing-management/promotion-attachments/hooks/usePromotionAttachments',
  () => {
    const idle = () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false });
    return { useCreatePromotionAttachment: idle, useDeletePromotionAttachment: idle };
  },
);

vi.mock('@/app/(protected)/forms-management/forms/hooks/useForms', () => ({
  useForms: () => ({ data: { data: [] }, isLoading: false }),
  useUpdateForm: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock('@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes', () => ({
  useContactAccessTypes: () => ({ data: [{ code: 'dealer', name: 'Dealer' }] }),
}));

import AttachmentDetailModal from './AttachmentDetailModal';

function attachment(over: Record<string, unknown> = {}) {
  return {
    id: 'att-1',
    original_filename: 'Employee Handbook 2026.pdf',
    stored_filename: 'Employee Handbook 2026.pdf',
    file_path: 'https://cdn.example/handbook.pdf',
    file_size_bytes: 1024,
    mime_type: 'application/pdf',
    entity_type: null,
    entity_id: null,
    uploaded_at: '2026-08-27T02:48:00',
    created_at: '2026-08-27T02:48:00',
    is_deleted: false,
    access_levels: ['dealer'],
    linked_products: [],
    linked_promotions: [],
    linked_form: null,
    linked_packing_lists: [],
    linked_certificates: [],
    company_id: 'company-1',
    company_name: 'Sorento',
    ai_read_status: null,
    ai_read_pages: null,
    ai_read_ocr_pages: null,
    ai_read_cost_usd: null,
    ai_read_error: null,
    ai_read_at: null,
    ...over,
  };
}

function renderDetail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <UploadManagerProvider>
        <AttachmentDetailModal open attachmentId="att-1" onOpenChange={vi.fn()} />
      </UploadManagerProvider>
    </QueryClientProvider>,
  );
}

/** The text of the row that carries the "Read by AI" label (the nearest ancestor that also holds a value). */
function rowText(): string {
  let node: HTMLElement | null = screen.getByText('Read by AI');
  for (let i = 0; i < 6 && node; i += 1) {
    const text = node.textContent ?? '';
    if (text.replace('Read by AI', '').trim().length > 0) return text;
    node = node.parentElement;
  }
  throw new Error('the Read by AI row holds no value');
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  net.getAttachmentMetadata.mockResolvedValue(attachment());
  net.apiFetch.mockResolvedValue({
    ok: true,
    status: 202,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => ({}),
    text: async () => '{}',
  });
});

const DONE = { ai_read_status: 'done', ai_read_pages: 42, ai_read_ocr_pages: 3, ai_read_cost_usd: '0.0120' };

describe('AttachmentDetailModal - Read by AI', () => {
  it('shows nothing when the AI does not read this file (status null)', async () => {
    renderDetail();
    expect(await screen.findByText('Uploaded')).toBeInTheDocument();

    expect(screen.queryByText('Read by AI')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Read again/i })).not.toBeInTheDocument();
  });

  it('a done file shows status, pages, OCR pages and the estimated cost', async () => {
    net.getAttachmentMetadata.mockResolvedValue(attachment(DONE));
    renderDetail();
    expect(await screen.findByText('Read by AI')).toBeInTheDocument();

    const text = rowText();
    expect(text).toMatch(/Done/i);
    expect(text).toMatch(/42\s*pages?/i);
    expect(text).toMatch(/3\b[^\d]*OCR/i);
    expect(text).toMatch(/est\./i);
    expect(text).toMatch(/0\.01/);
  });

  it('a done file offers Read again', async () => {
    net.getAttachmentMetadata.mockResolvedValue(attachment(DONE));
    renderDetail();
    await screen.findByText('Read by AI');

    expect(screen.getByRole('button', { name: /Read again/i })).toBeInTheDocument();
  });

  it('a failed file shows the error text and offers Read again', async () => {
    net.getAttachmentMetadata.mockResolvedValue(
      attachment({
        ai_read_status: 'failed',
        ai_read_pages: null,
        ai_read_error: 'The file could not be read.',
      }),
    );
    renderDetail();
    await screen.findByText('Read by AI');

    expect(rowText()).toMatch(/Failed/i);
    expect(screen.getByText(/The file could not be read\./)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Read again/i })).toBeInTheDocument();
  });

  it.each(['queued', 'processing'])('a %s file shows its status and no Read again', async (status) => {
    net.getAttachmentMetadata.mockResolvedValue(attachment({ ai_read_status: status }));
    renderDetail();
    await screen.findByText('Read by AI');

    expect(rowText()).toMatch(new RegExp(status, 'i'));
    expect(screen.queryByRole('button', { name: /Read again/i })).not.toBeInTheDocument();
  });

  it('Read again POSTs the ai-read route for this file', async () => {
    net.getAttachmentMetadata.mockResolvedValue(attachment(DONE));
    renderDetail();
    await screen.findByText('Read by AI');

    fireEvent.click(screen.getByRole('button', { name: /Read again/i }));

    await waitFor(() => {
      const hit = net.apiFetch.mock.calls.find(
        ([url, init]) =>
          typeof url === 'string' &&
          url.endsWith('/api/v1/resource-management/attachments/att-1/ai-read') &&
          (init as RequestInit | undefined)?.method === 'POST',
      );
      expect(hit).toBeTruthy();
    });
  });

  it('shows no raw id in the row (AC-K20)', async () => {
    net.getAttachmentMetadata.mockResolvedValue(attachment(DONE));
    renderDetail();
    await screen.findByText('Read by AI');

    expect(rowText()).not.toMatch(/att-1|[0-9a-f]{8}-[0-9a-f]{4}-/i);
  });

  it('shows three decimals when the estimated cost is under 0.01', async () => {
    net.getAttachmentMetadata.mockResolvedValue(
      attachment({ ...DONE, ai_read_pages: 5, ai_read_ocr_pages: 2, ai_read_cost_usd: '0.0040' }),
    );
    renderDetail();
    await screen.findByText('Read by AI');

    expect(rowText()).toMatch(/0\.004/);
  });
});
