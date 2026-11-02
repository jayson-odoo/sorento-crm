/**
 * QUOTE-COVER-DESIGN red tests (UAC A1 to A4): the Terms | Cover page tabs on the Quotation
 * Templates page and the cover page design editor. Only the network seam (`apiFetch`) is faked, so
 * the real hooks, services and components run. Fake data only.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

type Call = { url: string; method: string; body: Record<string, unknown> | null };
const calls: Call[] = [];

const KEYS = [
  'reference', 'date', 'attn', 'company', 'contact', 'address', 'email',
  'purpose', 'terms', 'payment_terms', 'validity', 'prepared_by',
];
const LABELS = [
  'Reference No.', 'Date', 'Attn', 'Company', 'Contact', 'Add', 'Email',
  'Quotation Purpose', 'Terms & Conditions', 'Payment Terms', 'Validity', 'Prepared By',
];
const savedDesign = {
  show_letterhead: true,
  title: 'QUOTATION',
  rows: KEYS.map((key, i) => ({ key, shown: true, label: LABELS[i] })),
  closing_html: '',
};

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
}

function handle(url: string, init?: RequestInit): Response {
  const method = (init?.method ?? 'GET').toUpperCase();
  const body = init?.body ? JSON.parse(String(init.body)) : null;
  calls.push({ url, method, body });
  if (url.includes('/quotation-templates/merge-fields')) {
    return json({
      data: [{ token: 'project_title', placeholder: '{{project_title}}', label: 'Project title', example: 'X' }],
      pagination: { total: 1, page: 1, limit: 1 },
      empty: false,
    });
  }
  if (url.includes('/quotation-templates/cover-preview')) {
    return json({
      cover_title: (body?.design as { title?: string } | undefined)?.title ?? 'QUOTATION',
      cover_show_letterhead: true,
      cover_rows: [{ key: 'reference', label: 'Sample label', text: 'SAMPLE-REF-R1' }],
      cover_intro_html: '<p>sample intro</p>',
      cover_closing_html: '',
      sender_name: 'Sorento Sdn Bhd',
      sender_logo_url: null,
    });
  }
  if (method === 'GET' && url.includes('/quotation-templates')) {
    const cover = url.includes('kind=cover_page');
    const rows = cover
      ? [
          { id: 'c1', kind: 'cover_page', name: 'Standard cover', body_html: '<p>hi</p>', is_active: true, design: savedDesign },
          { id: 'c2', kind: 'cover_page', name: 'Showroom cover', body_html: '', is_active: false, design: savedDesign },
        ]
      : [{ id: 't1', kind: 'terms', name: 'Standard 2026', body_html: '<p>x</p>', is_active: true }];
    return json({ data: rows, pagination: { total: rows.length, page: 1, limit: 15 }, empty: false });
  }
  if (method === 'POST' || method === 'PUT') {
    return json({ id: 'new', kind: 'cover_page', name: 'n', body_html: '', is_active: false, design: savedDesign }, 201);
  }
  return json({});
}

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, apiFetch: async (url: string, init?: RequestInit) => handle(String(url), init) };
});

vi.mock('@/lib/toast', () => ({
  toast: { custom: vi.fn(), error: vi.fn(), success: vi.fn(), warning: vi.fn(), dismiss: vi.fn() },
}));
vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/quotation-templates',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  useHasAnyPermission: () => true,
}));
vi.mock('@/components/ui/rich-text-editor', () => ({
  RichTextEditor: ({
    value,
    onChange,
    placeholder,
  }: {
    value: string;
    onChange: (html: string) => void;
    placeholder?: string;
  }) => <textarea aria-label={placeholder} value={value} onChange={(e) => onChange(e.target.value)} />,
}));

import { QuotationTemplatesClient } from './QuotationTemplatesClient';

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <QuotationTemplatesClient />
    </QueryClientProvider>,
  );
}

async function openCoverTab() {
  const tab = await screen.findByRole('tab', { name: 'Cover page' });
  fireEvent.mouseDown(tab, { button: 0 });
  fireEvent.click(tab);
  await screen.findByText('Standard cover');
}

async function openAddDesign() {
  await openCoverTab();
  fireEvent.click(screen.getByRole('button', { name: /^Add/ }));
  return screen.findByLabelText('Title');
}

const previewCalls = () => calls.filter((c) => c.url.includes('/quotation-templates/cover-preview'));

beforeEach(() => {
  calls.length = 0;
});

describe('Quotation Templates: Terms and Cover page tabs (A1, A2)', () => {
  it('opens on Terms and offers a Cover page tab', async () => {
    renderPage();
    expect(await screen.findByText('Standard 2026')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Terms' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Cover page' })).toBeInTheDocument();
  });

  it('the Cover page tab lists the cover_page designs with Active and Activate', async () => {
    renderPage();
    await openCoverTab();
    expect(calls.some((c) => c.method === 'GET' && c.url.includes('kind=cover_page'))).toBe(true);
    expect(screen.getByText('Showroom cover')).toBeInTheDocument();
    expect(screen.queryByText('Standard 2026')).toBeNull();
    expect(screen.getAllByRole('button', { name: 'Activate' })).toHaveLength(1);
    expect(screen.getByText('Active')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Activate' }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/quotation-templates/c2/activate'))).toBe(true),
    );
  });
});

describe('Cover page design editor (A3, A4)', () => {
  it('shows Name, Title QUOTATION, the letterhead switch on, and the 12 rows with the default labels', async () => {
    renderPage();
    const title = await openAddDesign();
    expect(title).toHaveValue('QUOTATION');
    expect(screen.getByLabelText('Name')).toHaveValue('');
    expect(screen.getByRole('switch', { name: 'Show company letterhead' })).toBeChecked();
    expect(screen.getAllByRole('checkbox')).toHaveLength(12);
    expect(screen.getAllByRole('button', { name: /drag/i })).toHaveLength(12);
    LABELS.forEach((label) => expect(screen.getByDisplayValue(label)).toBeInTheDocument());
    expect(screen.getByLabelText('Intro text')).toBeInTheDocument();
    expect(screen.getByLabelText('Closing text')).toBeInTheDocument();
  });

  it('has no way to add a custom row', async () => {
    renderPage();
    await openAddDesign();
    expect(screen.queryByRole('button', { name: /add (a )?(row|field line|custom)/i })).toBeNull();
  });

  it('caps the title and every label at 60 characters', async () => {
    renderPage();
    const title = await openAddDesign();
    expect(title).toHaveAttribute('maxlength', '60');
    expect(screen.getByDisplayValue('Reference No.')).toHaveAttribute('maxlength', '60');
  });

  it('Insert field lists the merge fields served by the backend and inserts one into the intro', async () => {
    renderPage();
    await openAddDesign();
    expect(calls.some((c) => c.method === 'GET' && c.url.endsWith('/quotation-templates/merge-fields'))).toBe(true);
    fireEvent.click(screen.getAllByRole('button', { name: /insert field/i })[0]);
    fireEvent.click(await screen.findByText('Project title'));
    expect(screen.getByLabelText('Intro text')).toHaveValue('{{project_title}}');
  });

  it('shows the preview and refetches it when the title changes', async () => {
    renderPage();
    const title = await openAddDesign();
    expect(await screen.findByText('SAMPLE-REF-R1')).toBeInTheDocument();
    expect(screen.getByText('Sample label')).toBeInTheDocument();
    fireEvent.change(title, { target: { value: 'OFFER' } });
    await waitFor(() => expect(previewCalls().at(-1)?.body).toMatchObject({ design: { title: 'OFFER' } }), {
      timeout: 4000,
    });
  });

  it('unticking a row and renaming a label reach the preview request', async () => {
    renderPage();
    await openAddDesign();
    fireEvent.click(screen.getAllByRole('checkbox')[2]);
    fireEvent.change(screen.getByDisplayValue('Reference No.'), { target: { value: 'Our Ref' } });
    await waitFor(
      () => {
        const design = previewCalls().at(-1)?.body?.design as typeof savedDesign;
        expect(design.rows.find((r) => r.key === 'attn')?.shown).toBe(false);
        expect(design.rows.find((r) => r.key === 'reference')?.label).toBe('Our Ref');
      },
      { timeout: 4000 },
    );
  });

  it('the letterhead switch reaches the preview request', async () => {
    renderPage();
    await openAddDesign();
    fireEvent.click(screen.getByRole('switch', { name: 'Show company letterhead' }));
    await waitFor(
      () => expect(previewCalls().at(-1)?.body).toMatchObject({ design: { show_letterhead: false } }),
      { timeout: 4000 },
    );
  });

  it('a handle moves a row down by keyboard and the save body carries the new order', async () => {
    const rect = (top: number) => ({
      top, bottom: top + 40, left: 0, right: 300, width: 300, height: 40, x: 0, y: top, toJSON() {},
    });
    const spy = vi
      .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockImplementation(function (this: HTMLElement) {
        const handles = screen.queryAllByRole('button', { name: /drag/i });
        const row = handles.map((h) => h.closest('li,tr,[data-row],div')).findIndex((r) => r && r.contains(this));
        return rect(row >= 0 ? row * 40 : 0) as DOMRect;
      });
    try {
      renderPage();
      await openAddDesign();
      const handles = screen.getAllByRole('button', { name: /drag/i });
      handles[0].focus();
      fireEvent.keyDown(handles[0], { key: ' ', code: 'Space' });
      await new Promise((r) => setTimeout(r, 30));
      fireEvent.keyDown(document, { key: 'ArrowDown', code: 'ArrowDown' });
      await new Promise((r) => setTimeout(r, 30));
      fireEvent.keyDown(document, { key: ' ', code: 'Space' });
      await waitFor(
        () => {
          const keys = (previewCalls().at(-1)?.body?.design as typeof savedDesign).rows.map((r) => r.key);
          expect(keys.slice(0, 2)).toEqual(['date', 'reference']);
        },
        { timeout: 4000 },
      );
      fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Reordered' } });
      fireEvent.click(screen.getAllByRole('button', { name: /^(Add|Save|Create)/ }).at(-1)!);
      await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.body?.kind === 'cover_page')).toBe(true));
      const sent = calls.find((c) => c.method === 'POST' && c.body?.kind === 'cover_page')!.body!;
      expect((sent.design as typeof savedDesign).rows.slice(0, 2).map((r) => r.key)).toEqual(['date', 'reference']);
    } finally {
      spy.mockRestore();
    }
  });

  it('save sends the design and the intro as body_html, and needs a name', async () => {
    renderPage();
    await openAddDesign();
    const save = () => screen.getAllByRole('button', { name: /^(Add|Save|Create)/ }).at(-1)!;
    expect(save()).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Showroom 2026' } });
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'OFFER' } });
    fireEvent.change(screen.getByLabelText('Intro text'), { target: { value: '<p>Dear {{project_title}}</p>' } });
    fireEvent.change(screen.getByLabelText('Closing text'), { target: { value: '<p>Thanks</p>' } });
    fireEvent.click(screen.getByRole('switch', { name: 'Show company letterhead' }));
    fireEvent.click(save());
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.body?.kind === 'cover_page')).toBe(true));
    const sent = calls.find((c) => c.method === 'POST' && c.body?.kind === 'cover_page')!.body!;
    expect(sent).toMatchObject({
      name: 'Showroom 2026',
      body_html: '<p>Dear {{project_title}}</p>',
      design: { title: 'OFFER', show_letterhead: false, closing_html: '<p>Thanks</p>' },
    });
    expect((sent.design as typeof savedDesign).rows).toHaveLength(12);
  });

  it('editing an existing design opens with its saved values', async () => {
    renderPage();
    await openCoverTab();
    fireEvent.click(screen.getByText('Standard cover'));
    expect(await screen.findByLabelText('Title')).toHaveValue('QUOTATION');
    expect(screen.getByLabelText('Name')).toHaveValue('Standard cover');
    expect(within(document.body).getAllByRole('checkbox')).toHaveLength(12);
  });
});

describe('Deactivate a cover design (fix round 1)', () => {
  it('the active cover design shows Deactivate, inactive rows keep Activate, and Deactivate posts', async () => {
    renderPage();
    await openCoverTab();
    expect(screen.getAllByRole('button', { name: 'Deactivate' })).toHaveLength(1);
    expect(screen.getAllByRole('button', { name: 'Activate' })).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'Deactivate' }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/quotation-templates/c1/deactivate'))).toBe(true),
    );
  });

  it('terms rows are unchanged: no Deactivate action', async () => {
    renderPage();
    await screen.findByText('Standard 2026');
    expect(screen.queryByRole('button', { name: 'Deactivate' })).toBeNull();
  });
});
