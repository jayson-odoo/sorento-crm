/**
 * QUOTE-COVER-DESIGN red tests (UAC A1 to A4), moved to the QUOTE-COVER-FIELDS sections shape: the Terms | Cover page tabs on the Quotation
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

// QUOTE-COVER-FIELDS: rows pick a source field and sit in sections with any number of columns.
const SOURCES = [
  'document_no', 'date', 'attn', 'to_name', 'to_tel', 'to_address', 'to_email',
  'terms', 'payment_terms', 'validity', 'salesperson_name',
];
const LABELS = [
  'Reference No.', 'Date', 'Attn', 'Company', 'Contact', 'Add', 'Email',
  'Terms & Conditions', 'Payment Terms', 'Validity', 'Prepared By',
];
const CAPTIONS: Record<string, string> = {
  document_no: 'Document number', date: 'Date', attn: 'Attn', to_name: 'To: company name',
  to_tel: 'To: tel', to_address: 'To: address', to_email: 'To: email', terms: 'Terms text',
  payment_terms: 'Payment terms', validity: 'Validity', salesperson_name: 'Salesperson: name',
  salesperson_email: 'Salesperson: email', project_title: 'Project title',
};
const DEFAULT_LABELS: Record<string, string> = {
  salesperson_email: 'Email', project_title: 'Project Title', salesperson_name: 'Sales',
  validity: 'Validity', date: 'Date',
};
type Design = {
  show_letterhead: boolean;
  title: string;
  closing_html: string;
  sections: {
    style: string;
    label: string;
    columns: number;
    rows: { source: string; shown: boolean; label: string; column: number }[];
  }[];
};
const savedDesign: Design = {
  show_letterhead: true,
  title: 'QUOTATION',
  sections: [
    {
      style: 'fields',
      label: '',
      columns: 1,
      rows: SOURCES.map((source, i) => ({ source, shown: true, label: LABELS[i], column: 0 })),
    },
  ],
  closing_html: '',
};
const rowsOf = (design: unknown, section = 0) => (design as Design).sections[section].rows;
let previewSections: unknown = null;

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
}

let defaultOverrideLabel: string | null = null;

function handle(url: string, init?: RequestInit): Response {
  const method = (init?.method ?? 'GET').toUpperCase();
  const body = init?.body ? JSON.parse(String(init.body)) : null;
  calls.push({ url, method, body });
  if (url.includes('/quotation-templates/cover-default')) {
    const rows = rowsOf(savedDesign).map((r, i) =>
      i === 0 && defaultOverrideLabel ? { ...r, label: defaultOverrideLabel } : r,
    );
    return json({ ...savedDesign, sections: [{ ...savedDesign.sections[0], rows }] });
  }
  if (url.includes('/quotation-templates/cover-sources')) {
    return json({
      data: Object.entries(CAPTIONS).map(([key, caption]) => ({
        key,
        caption,
        group: 'Fields',
        default_label: DEFAULT_LABELS[key] ?? caption,
      })),
      pagination: { total: 1, page: 1, limit: 1 },
      empty: false,
    });
  }
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
      cover_rows: [{ key: 'document_no', label: 'Sample label', text: 'SAMPLE-REF-R1' }],
      cover_sections: previewSections,
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
// SearchableSelect as a native select (the pattern of SalesTeamModal.test.tsx).
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    value: string;
    onChange: (value: string) => void;
    options?: { value: string; label: string }[];
    'aria-label'?: string;
    placeholder?: React.ReactNode;
  }) => (
    <select
      aria-label={props['aria-label']}
      value={props.value}
      onChange={(event) => props.onChange(event.target.value)}
    >
      <option value="">{typeof props.placeholder === 'string' ? props.placeholder : ''}</option>
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));
vi.mock('@/components/ui/rich-text-editor', () => ({
  RichTextEditor: ({
    value,
    onChange,
    placeholder,
    id,
    'aria-labelledby': labelledBy,
  }: {
    value: string;
    onChange: (html: string) => void;
    placeholder?: string;
    id?: string;
    'aria-labelledby'?: string;
  }) => (
    <textarea
      id={id}
      aria-labelledby={labelledBy}
      aria-label={labelledBy ? undefined : placeholder}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  ),
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
  defaultOverrideLabel = null;
  previewSections = null;
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
  it('shows Name, Title QUOTATION, the letterhead switch on, and the 11 default rows with their labels and sources', async () => {
    renderPage();
    const title = await openAddDesign();
    expect(title).toHaveValue('QUOTATION');
    expect(screen.getByLabelText('Name')).toHaveValue('');
    expect(screen.getByRole('switch', { name: 'Show company letterhead' })).toBeChecked();
    expect(screen.getAllByRole('checkbox')).toHaveLength(11);
    expect(screen.getAllByRole('button', { name: /drag/i })).toHaveLength(11);
    LABELS.forEach((label) => expect(screen.getAllByDisplayValue(label).length).toBeGreaterThan(0));
    expect(screen.getByRole('combobox', { name: 'Source field for Document number' })).toHaveValue(
      'document_no',
    );
    expect(screen.queryByDisplayValue(/Purpose/)).toBeNull();
    expect(screen.getByLabelText('Intro text')).toBeInTheDocument();
    expect(screen.getByLabelText('Closing text')).toBeInTheDocument();
  });

  it('Add a row: picking a field adds a ticked row with that field and its default label', async () => {
    renderPage();
    await openAddDesign();
    fireEvent.change(screen.getByRole('combobox', { name: 'Add a row to Section 1' }), {
      target: { value: 'salesperson_email' },
    });
    expect(screen.getAllByRole('checkbox')).toHaveLength(12);
    await waitFor(
      () => {
        const last = rowsOf(previewCalls().at(-1)?.body?.design).at(-1);
        expect(last).toEqual({ source: 'salesperson_email', label: 'Email', shown: true, column: 0 });
      },
      { timeout: 4000 },
    );
  });

  it('changing a row source keeps a typed label but follows the field when the label was the default', async () => {
    renderPage();
    await openAddDesign();
    // "Validity" is still the validity field's default label: it follows the new field.
    fireEvent.change(screen.getByRole('combobox', { name: 'Source field for Validity' }), {
      target: { value: 'project_title' },
    });
    // "Reference No." was typed (the field default here is "Document number"): it stays.
    fireEvent.change(screen.getByRole('combobox', { name: 'Source field for Document number' }), {
      target: { value: 'date' },
    });
    await waitFor(
      () => {
        const rows = rowsOf(previewCalls().at(-1)?.body?.design);
        expect(rows[9]).toMatchObject({ source: 'project_title', label: 'Project Title' });
        expect(rows[0]).toMatchObject({ source: 'date', label: 'Reference No.' });
      },
      { timeout: 4000 },
    );
  });

  it('a section takes any column count and each row picks its column', async () => {
    renderPage();
    await openAddDesign();
    expect(screen.queryByRole('combobox', { name: 'Column for Date' })).toBeNull();
    fireEvent.change(screen.getByRole('combobox', { name: 'Columns of Section 1' }), {
      target: { value: '3' },
    });
    fireEvent.change(screen.getByRole('combobox', { name: 'Column for Date' }), {
      target: { value: '3' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: 'Band label of Section 1' }), {
      target: { value: 'Propose to:' },
    });
    await waitFor(
      () => {
        const section = (previewCalls().at(-1)?.body?.design as Design).sections[0];
        expect(section).toMatchObject({ columns: 3, label: 'Propose to:' });
        expect(section.rows[1]).toMatchObject({ source: 'date', column: 2 });
      },
      { timeout: 4000 },
    );
    // Fewer columns: a row in a column that is gone moves to the last one.
    fireEvent.change(screen.getByRole('combobox', { name: 'Columns of Propose to:' }), {
      target: { value: '2' },
    });
    await waitFor(
      () => expect(rowsOf(previewCalls().at(-1)?.body?.design)[1].column).toBe(1),
      { timeout: 4000 },
    );
  });

  it('adds, styles, moves and removes sections; a row is removed at once', async () => {
    renderPage();
    await openAddDesign();
    expect(screen.getByRole('button', { name: 'Remove Section 1' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Add a section' }));
    fireEvent.change(screen.getByRole('combobox', { name: 'Style of Section 2' }), {
      target: { value: 'title' },
    });
    fireEvent.change(screen.getByRole('combobox', { name: 'Add a row to Section 2' }), {
      target: { value: 'project_title' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Move Section 2 up' }));
    fireEvent.click(screen.getByRole('button', { name: 'Remove Attn' }));
    await waitFor(
      () => {
        const design = previewCalls().at(-1)?.body?.design as Design;
        expect(design.sections.map((x) => x.style)).toEqual(['title', 'fields']);
        expect(design.sections[0].rows).toEqual([
          { source: 'project_title', label: 'Project Title', shown: true, column: 0 },
        ]);
        expect(design.sections[1].rows.some((r) => r.source === 'attn')).toBe(false);
      },
      { timeout: 4000 },
    );
  });

  it('the preview draws the sections the server returns, with their band labels and columns', async () => {
    previewSections = [
      {
        style: 'fields',
        label: 'Propose to:',
        columns: 2,
        cells: [
          [{ source: 'to_name', label: 'Company', text: 'SAMPLE BUILDERS' }],
          [{ source: 'document_no', label: 'Reference No', text: 'SAMPLE-REF-R1' }],
        ],
      },
      { style: 'title', label: 'Project Title:', columns: 1, cells: [[{ source: 'project_title', label: '', text: 'SAMPLE TITLE' }]] },
    ];
    renderPage();
    await openAddDesign();
    expect(await screen.findByText('Propose to:')).toBeInTheDocument();
    expect(screen.getByText('Project Title:')).toBeInTheDocument();
    expect(screen.getByText('SAMPLE BUILDERS')).toBeInTheDocument();
    expect(screen.getByText('SAMPLE TITLE')).toBeInTheDocument();
    expect(screen.queryByText('Sample label')).toBeNull();
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
    fireEvent.click(await screen.findByRole('button', { name: 'Project title' }));
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
        const rows = rowsOf(previewCalls().at(-1)?.body?.design);
        expect(rows.find((r) => r.source === 'attn')?.shown).toBe(false);
        expect(rows.find((r) => r.source === 'document_no')?.label).toBe('Our Ref');
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
          const keys = rowsOf(previewCalls().at(-1)?.body?.design).map((r) => r.source);
          expect(keys.slice(0, 2)).toEqual(['date', 'document_no']);
        },
        { timeout: 4000 },
      );
      fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Reordered' } });
      fireEvent.click(screen.getAllByRole('button', { name: /^(Add|Save|Create)/ }).at(-1)!);
      await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.body?.kind === 'cover_page')).toBe(true));
      const sent = calls.find((c) => c.method === 'POST' && c.body?.kind === 'cover_page')!.body!;
      expect(rowsOf(sent.design).slice(0, 2).map((r) => r.source)).toEqual(['date', 'document_no']);
    } finally {
      spy.mockRestore();
    }
  });

  it('B1: while a row is dragged its overlay copy renders outside the dialog', async () => {
    renderPage();
    await openAddDesign();
    const handle = screen.getByRole('button', { name: 'Drag Validity to reorder' });
    handle.focus();
    fireEvent.keyDown(handle, { key: ' ', code: 'Space' });
    await new Promise((r) => setTimeout(r, 50));
    const copies = await screen.findAllByLabelText('Drag Validity to reorder');
    expect(copies).toHaveLength(2);
    const original = copies.find((c) => c.closest('[data-slot="sortable"]'))!;
    const overlay = copies.find((c) => !c.closest('[data-slot="sortable"]'))!;
    expect(original.closest('[role="dialog"]')).not.toBeNull();
    expect(overlay.closest('[role="dialog"]')).toBeNull();
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
    expect(rowsOf(sent.design)).toHaveLength(11);
    expect(JSON.stringify(sent.design)).not.toContain('"id"');
  });

  it('editing an existing design opens with its saved values', async () => {
    renderPage();
    await openCoverTab();
    fireEvent.click(screen.getByText('Standard cover'));
    expect(await screen.findByLabelText('Title')).toHaveValue('QUOTATION');
    expect(screen.getByLabelText('Name')).toHaveValue('Standard cover');
    expect(within(document.body).getAllByRole('checkbox')).toHaveLength(11);
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


describe('QUOTE-COVER-DESIGN round 2 (designer)', () => {
  it('Intro text and Closing text have a visible label linked to the editor, not the placeholder', async () => {
    renderPage();
    await openAddDesign();
    fireEvent.change(screen.getByLabelText('Intro text'), { target: { value: '<p>seeded intro</p>' } });
    expect(screen.getByRole('textbox', { name: 'Intro text' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Closing text' })).toBeInTheDocument();
    expect(screen.getByText('Intro text').tagName).not.toBe('TEXTAREA');
  });

  it('the Add form fills its rows from the cover-default endpoint', async () => {
    defaultOverrideLabel = 'Zz Default Label';
    renderPage();
    await openAddDesign();
    expect(calls.some((c) => c.method === 'GET' && c.url.endsWith('/quotation-templates/cover-default'))).toBe(true);
    expect(await screen.findByDisplayValue('Zz Default Label')).toBeInTheDocument();
  });
});
