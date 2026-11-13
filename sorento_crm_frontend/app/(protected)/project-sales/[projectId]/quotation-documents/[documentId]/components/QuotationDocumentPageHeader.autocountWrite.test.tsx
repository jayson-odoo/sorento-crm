/**
 * AC-QTSO-CRM Phase 2 (red): Create / Update in AutoCount on the quotation page header.
 *
 * UAC U2, U15, U17, U18, ruling R5. The document detail gains `in_autocount`,
 * `autocount_doc_no`, `latest_issue_accepted` and `autocount_needs_update`.
 *
 *   Create: switch on + permission + kind quotation + latest issue accepted + not in AutoCount.
 *   Update: same, but in AutoCount and the latest accepted issue was not sent yet.
 *   Before acceptance: Create is shown greyed with "The customer has not accepted this quotation yet".
 *   A proposal shows nothing. Switch off or no permission: nothing renders at all.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.fn();
let permissions = new Set<string>();
let switchOn = true;
let bookNamed: string | null = 'db3';
let documentData: Record<string, unknown> = {};

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/quotation-documents/d1',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, apiFetch: (...args: unknown[]) => apiFetch(...args) };
});

vi.mock('@/hooks/usePermissions', () => ({
  usePermissions: () => ({ permissions: [...permissions], permissionSet: permissions }),
  useHasPermission: (slug: string) => permissions.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((slug) => permissions.has(slug)),
}));

vi.mock('../../../../_shared/hooks/useQuotationDocuments', () => ({
  useQuotationDocument: () => ({ data: documentData }),
}));

import { QuotationDocumentPageHeader } from './QuotationDocumentPageHeader';

const WRITE = 'projects.autocount.write';
const NOT_ACCEPTED = 'The customer has not accepted this quotation yet';

function json(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body, headers: new Headers() } as Response;
}

function doc(overrides: Record<string, unknown> = {}) {
  return {
    document_no: 'SRT/Q/2026/0141',
    kind: 'quotation',
    in_autocount: false,
    autocount_doc_no: null,
    latest_issue_accepted: true,
    autocount_needs_update: false,
    ...overrides,
  };
}

function renderHeader(data: Record<string, unknown>) {
  documentData = data;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(
    <QueryClientProvider client={client}>
      <QuotationDocumentPageHeader projectId="p1" documentId="d1" />
    </QueryClientProvider>,
  );
}

function appConfigReads() {
  return apiFetch.mock.calls.filter(([url]) => String(url).includes('settings/app-config')).length;
}

async function settled() {
  await waitFor(() => expect(appConfigReads()).toBeGreaterThan(0));
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
}

const none = () => {
  expect(screen.queryByRole('button', { name: /Create in AutoCount/ })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Update in AutoCount/ })).not.toBeInTheDocument();
  expect(screen.queryByText(/in AutoCount/)).not.toBeInTheDocument();
};

beforeEach(() => {
  vi.clearAllMocks();
  permissions = new Set([WRITE]);
  switchOn = true;
  bookNamed = 'db3';
  apiFetch.mockImplementation(async (url: string) => {
    const path = String(url);
    if (path.includes('settings/app-config')) {
      return json({ project_autocount_write_enabled: switchOn });
    }
    if (path.includes('autocount-write/capabilities')) {
      const open = { enabled: true, reason: null };
      const ops = { create_doc: open, edit_doc: open, add_line: open };
      return json({ enabled: switchOn, sales_orders: ops, quotations: ops, book: bookNamed });
    }
    return json({});
  });
});

describe('Quotation page header, AutoCount write actions', () => {
  it.each([null, '', '   '])('greys Create with "Waiting for AutoCount" while SS names no book (%j)', async (named) => {
    bookNamed = named;
    renderHeader(doc());

    const create = await screen.findByRole('button', { name: /Create in AutoCount/ });
    await settled();
    expect(create).toBeDisabled();
    expect(create).toHaveAttribute('title', 'Waiting for AutoCount');
  });

  it('greys Update with "Waiting for AutoCount" while SS names no book (R8)', async () => {
    bookNamed = null;
    renderHeader(doc({ in_autocount: true, autocount_doc_no: 'QT000777', autocount_needs_update: true }));

    const update = await screen.findByRole('button', { name: /Update in AutoCount/ });
    await settled();
    expect(update).toBeDisabled();
    expect(update).toHaveAttribute('title', 'Waiting for AutoCount');
  });

  it('offers Create in AutoCount on an accepted quotation not yet in AutoCount', async () => {
    renderHeader(doc());

    const create = await screen.findByRole('button', { name: /Create in AutoCount/ });
    // Greyed until SS names the book (R9), then enabled.
    await waitFor(() => expect(create).toBeEnabled());
    expect(screen.queryByRole('button', { name: /Update in AutoCount/ })).not.toBeInTheDocument();
  });

  it('offers Update in AutoCount when it is in AutoCount and a later accepted issue is unsent', async () => {
    renderHeader(doc({ in_autocount: true, autocount_doc_no: 'QT000777', autocount_needs_update: true }));

    const update = await screen.findByRole('button', { name: /Update in AutoCount/ });
    await waitFor(() => expect(update).toBeEnabled());
    expect(screen.queryByRole('button', { name: /Create in AutoCount/ })).not.toBeInTheDocument();
  });

  it('offers neither once the latest accepted issue is already in AutoCount', async () => {
    renderHeader(doc({ in_autocount: true, autocount_doc_no: 'QT000777', autocount_needs_update: false }));
    await settled();

    expect(screen.queryByRole('button', { name: /Create in AutoCount/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Update in AutoCount/ })).not.toBeInTheDocument();
  });

  it('greys Create with the acceptance sentence before the customer accepted', async () => {
    renderHeader(doc({ latest_issue_accepted: false }));

    const create = await screen.findByRole('button', { name: /Create in AutoCount/ });
    expect(create).toBeDisabled();
    expect(document.body.innerHTML).toContain(NOT_ACCEPTED);
  });

  it('shows nothing on a proposal', async () => {
    renderHeader(doc({ kind: 'proposal', latest_issue_accepted: true }));
    await settled();

    none();
  });

  it('renders nothing at all when the switch is off', async () => {
    switchOn = false;
    renderHeader(doc());
    await settled();

    none();
  });

  it('renders nothing at all without projects.autocount.write', async () => {
    permissions = new Set();
    renderHeader(doc());
    await settled();

    none();
  });

  it('renders nothing for an unaccepted quotation when the switch is off (no greyed ghost either)', async () => {
    switchOn = false;
    renderHeader(doc({ latest_issue_accepted: false }));
    await settled();

    none();
    expect(document.body.innerHTML).not.toContain(NOT_ACCEPTED);
  });
});
