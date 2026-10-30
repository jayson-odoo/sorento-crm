/**
 * QUOTE-DRAWING-ESCALATE: the Drawing cell of a quotation line, one case per state of the mock
 * (documentation/plans/project-sales/mockups/quote-drawing-escalate-29oct-mock.html, v3).
 *
 * Written BEFORE the component: every escalation case is red until `DrawingEscalation`, the
 * `pdf` state and `technical_drawing.escalation` exist. The network edge is `apiFetch` from
 * `@/lib/api` (what `projectService` calls), so the test pins the endpoint the click reaches
 * without naming the service function or the hook.
 *
 * Masked data only: PRD-xxx-nn codes.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  QuotationLine,
  QuotationLineDrawing,
} from '../../_shared/types/project.types';
import { QuotationLineFileCell } from './QuotationLineFileCell';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: {
    success: (...a: unknown[]) => toastSuccess(...a),
    error: (...a: unknown[]) => toastError(...a),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));

const HOUR = 3_600_000;
// Midday UTC keeps the printed day stable in every timezone a CI box can have.
const OPENED = '2026-10-29T06:00:00.000Z';
const RESPONDED = '2026-10-29T09:03:00.000Z';

function drawing(overrides: Record<string, unknown> = {}): QuotationLineDrawing {
  return {
    state: 'no_drawings',
    url: null,
    preview_url: null,
    attachment_id: null,
    filename: null,
    candidate_count: 0,
    candidates: [],
    escalation: null,
    ...overrides,
  } as unknown as QuotationLineDrawing;
}

function escalation(overrides: Record<string, unknown> = {}) {
  return {
    tracking_id: 'trk-1',
    opened_at: OPENED,
    responded_at: null,
    due_at: new Date(Date.now() + 10 * HOUR).toISOString(),
    requester_count: 2,
    last_resolved_at: null,
    ...overrides,
  };
}

function line(technical_drawing: QuotationLineDrawing, overrides: Partial<QuotationLine> = {}) {
  return {
    id: 'line-1',
    version_id: 'version-1',
    product_id: 'product-1',
    product_code: 'PRD-CCC-03',
    unit_price: '250.00',
    quantity: '4',
    line_total: '1000.00',
    is_non_standard: false,
    is_below_floor: false,
    sort_order: 0,
    technical_drawing,
    ...overrides,
  } as QuotationLine;
}

function renderCell(l: QuotationLine | null) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <QuotationLineFileCell
        kind="drawing"
        line={l}
        label="PRD-CCC-03"
        pickedId=""
        editable={false}
        onPick={() => {}}
        onPreview={() => {}}
      />
    </QueryClientProvider>,
  );
}

/** Class names of an element and the few ancestors inside the cell, so the colour rule is read
 * wherever the component chooses to put it (the tile or its label). */
function classesAround(el: HTMLElement): string {
  const names: string[] = [];
  let node: HTMLElement | null = el;
  for (let depth = 0; node && depth < 4; depth += 1) {
    names.push(node.className?.toString() ?? '');
    node = node.parentElement;
  }
  return names.join(' ');
}

const escalateButton = () =>
  screen.queryByRole('button', { name: /Escalate missing drawing for PRD-CCC-03/i });

beforeEach(() => {
  apiFetch.mockReset();
  toastSuccess.mockReset();
  toastError.mockReset();
});

describe('QuotationLineFileCell, drawing cell: what is on file', () => {
  it('state 1: a drawing image shows the thumbnail and no Escalate', () => {
    renderCell(
      line(
        drawing({
          state: 'default',
          url: 'https://cdn.test/signed/ts-0001.png',
          preview_url: 'https://cdn.test/signed/ts-0001.png',
          attachment_id: 'att-1',
          filename: 'TS-0001.png',
          candidate_count: 1,
        }),
      ),
    );

    expect(screen.getByRole('img')).toHaveAttribute('src', 'https://cdn.test/signed/ts-0001.png');
    expect(escalateButton()).not.toBeInTheDocument();
    expect(screen.queryByText(/Escalated/)).not.toBeInTheDocument();
  });

  it('state 2: a PDF-only drawing is a tile that opens the file in a new tab, no Escalate', () => {
    renderCell(
      line(
        drawing({
          state: 'pdf',
          url: 'https://cdn.test/signed/ts-0002.pdf',
          filename: 'TS-0002.pdf',
          attachment_id: 'att-2',
        }),
      ),
    );

    const tile = screen.getByRole('link', { name: /PDF/i });
    expect(tile).toHaveAttribute('href', 'https://cdn.test/signed/ts-0002.pdf');
    expect(tile).toHaveAttribute('target', '_blank');
    expect(tile.getAttribute('rel') ?? '').toMatch(/noopener/);
    expect(tile).toHaveAttribute('title', expect.stringContaining('TS-0002.pdf'));
    expect(escalateButton()).not.toBeInTheDocument();
    // A PDF is not an image: nothing may be drawn as a thumbnail.
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });
});

describe('QuotationLineFileCell, drawing cell: no drawing, escalate', () => {
  it('state 3: a saved catalogue line with no drawing offers Escalate, hover names the product', () => {
    renderCell(line(drawing()));

    const button = escalateButton();
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent('Escalate');
    expect(button).toHaveAttribute('title', 'Ask for a drawing of PRD-CCC-03');
    expect(button).toBeEnabled();
    // The old dead-end label is gone: Escalate replaces it.
    expect(screen.queryByText('no drawing')).not.toBeInTheDocument();
  });

  it('a SET line (no product id of its own, a driver in its parts) offers Escalate too', () => {
    renderCell(
      line(drawing(), {
        product_id: null,
        product_set_id: 'set-1',
        product_code: 'PRD-SET-01',
        set_parts: [
          { product_id: 'p-driver', product_code: 'PRD-CCC-03', quantity: '1', is_driver: true },
        ],
      }),
    );

    expect(screen.getByRole('button', { name: /Escalate missing drawing for/i })).toBeInTheDocument();
  });

  it('one click posts the drawing kind to the line media-escalation endpoint, with no dialog in between', async () => {
    apiFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ joined: false, escalation: escalation() }),
    });
    renderCell(line(drawing()));

    fireEvent.click(escalateButton() as HTMLElement);

    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
    const [url, init] = apiFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(
      /\/quotation-versions\/version-1\/lines\/line-1\/media-escalation$/,
    );
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ kind: 'drawing' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
  });

  it('state 4: while the request is in flight the tile is disabled and busy', async () => {
    let release: (value: unknown) => void = () => {};
    apiFetch.mockReturnValue(
      new Promise((resolve) => {
        release = resolve;
      }),
    );
    renderCell(line(drawing()));

    fireEvent.click(escalateButton() as HTMLElement);

    await waitFor(() => expect(escalateButton()).toBeDisabled());
    expect(escalateButton()).toHaveAttribute('aria-busy', 'true');
    // A second click while busy must not fire a second request.
    fireEvent.click(escalateButton() as HTMLElement);
    expect(apiFetch).toHaveBeenCalledTimes(1);
    release({ ok: true, status: 200, json: async () => ({ joined: false, escalation: escalation() }) });
  });

  it('a refused escalate toasts the server message and returns to state 3', async () => {
    apiFetch.mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: 'The marketing product team is not set up for this company',
          code: 'marketing_team_not_set_up',
        }),
        { status: 409, headers: { 'content-type': 'application/json' } },
      ),
    );
    renderCell(line(drawing()));

    fireEvent.click(escalateButton() as HTMLElement);

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(String(toastError.mock.calls[0][0])).toContain('The marketing product team is not set up for this company');
    await waitFor(() => expect(escalateButton()).toBeEnabled());
  });

  it('state 10: resolved without a drawing reads Escalate again, hover says when', () => {
    renderCell(
      line(
        drawing({
          escalation: escalation({
            tracking_id: null,
            opened_at: null,
            responded_at: null,
            due_at: null,
            requester_count: 0,
            last_resolved_at: '2026-10-30T06:00:00.000Z',
          }),
        }),
      ),
    );

    const button = escalateButton();
    expect(button).toBeInTheDocument();
    expect(button).toBeEnabled();
    expect(button?.getAttribute('title') ?? '').toMatch(/Last request resolved 30 Oct/);
    expect(button?.getAttribute('title') ?? '').toMatch(/no drawing on file/);
  });
});

describe('QuotationLineFileCell, drawing cell: already escalated', () => {
  it('state 5: shows "Escalated <date>", names the people and the due date, as a Join button', () => {
    renderCell(line(drawing({ escalation: escalation() })));

    const label = screen.getByText(/Escalated/);
    expect(label.textContent).toMatch(/29 Oct/);
    expect(escalateButton()).not.toBeInTheDocument();
    const hover = screen.getByTitle(/Escalated/);
    expect(hover.getAttribute('title')).toMatch(/by 2 people/);
    expect(hover.getAttribute('title')).toMatch(/Due /);
    // The tile itself is the Join control: one button, no link.
    expect(screen.getAllByRole('button')).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Join the drawing request for PRD-CCC-03' })).toBeEnabled();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('clicking the Escalated tile joins: it posts the media-escalation route, disabled while in flight', async () => {
    let release: (value: unknown) => void = () => {};
    apiFetch.mockReturnValue(new Promise((resolve) => { release = resolve; }));
    renderCell(line(drawing({ escalation: escalation() })));
    const tile = () => screen.getByRole('button', { name: 'Join the drawing request for PRD-CCC-03' });

    fireEvent.click(tile());

    await waitFor(() => expect(tile()).toBeDisabled());
    expect(tile()).toHaveAttribute('aria-busy', 'true');
    fireEvent.click(tile());
    expect(apiFetch).toHaveBeenCalledTimes(1);
    const [url, init] = apiFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/quotation-versions\/version-1\/lines\/line-1\/media-escalation$/);
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ kind: 'drawing' });
    release({ ok: true, status: 200, json: async () => ({ joined: true, escalation: escalation() }) });
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('Already escalated: added you to the request'));
  });

  it('a single requester reads "by 1 person"', () => {
    renderCell(line(drawing({ escalation: escalation({ requester_count: 1 }) })));
    expect(screen.getByTitle(/Escalated/).getAttribute('title')).toMatch(/by 1 person\b/);
  });

  it('state 6: once the team responded the tile reads "Replied <date>", the hover keeps "Responded"', () => {
    renderCell(line(drawing({ escalation: escalation({ responded_at: RESPONDED }) })));

    const label = screen.getByText(/Replied/);
    expect(label.textContent).toMatch(/29 Oct/);
    expect(screen.queryByText(/Escalated 29/)).not.toBeInTheDocument();
    expect(screen.getByTitle(/Responded/).getAttribute('title')).toMatch(/Responded 29 Oct/);
    // It still joins: a later requester is added to the open request.
    expect(screen.getByRole('button', { name: 'Join the drawing request for PRD-CCC-03' })).toBeEnabled();
  });

  it('the label sits inside a 48px tile: tight tracking, no side padding, no wrapping surprises', () => {
    renderCell(line(drawing({ escalation: escalation({ responded_at: RESPONDED }) })));
    const tile = screen.getByRole('button', { name: /Join the drawing request/ });
    expect(tile.className).toMatch(/tracking-tight/);
    expect(tile.className).toMatch(/px-0/);
    expect(tile.className).toMatch(/overflow-hidden/);
  });

  it('colour follows the deadline: neutral with time to spare, amber under 4h, red overdue', () => {
    const { unmount } = renderCell(
      line(drawing({ escalation: escalation({ due_at: new Date(Date.now() + 10 * HOUR).toISOString() }) })),
    );
    let around = classesAround(screen.getByText(/Escalated/));
    expect(around).not.toMatch(/amber/);
    expect(around).not.toMatch(/destructive|red-/);
    unmount();

    const amber = renderCell(
      line(drawing({ escalation: escalation({ due_at: new Date(Date.now() + 2 * HOUR).toISOString() }) })),
    );
    around = classesAround(screen.getByText(/Escalated/));
    expect(around).toMatch(/amber/);
    amber.unmount();

    renderCell(
      line(drawing({ escalation: escalation({ due_at: new Date(Date.now() - 1 * HOUR).toISOString() }) })),
    );
    around = classesAround(screen.getByText(/Escalated/));
    expect(around).toMatch(/destructive|red-/);
  });

  it('the colour of a responded task follows the same deadline rule', () => {
    renderCell(
      line(
        drawing({
          escalation: escalation({
            responded_at: RESPONDED,
            due_at: new Date(Date.now() - 1 * HOUR).toISOString(),
          }),
        }),
      ),
    );
    expect(classesAround(screen.getByText(/Replied/))).toMatch(/destructive|red-/);
  });

  it('state 9: a drawing added while the task is open shows the thumbnail, not the flag', () => {
    renderCell(
      line(
        drawing({
          state: 'default',
          url: 'https://cdn.test/signed/ts-0005.png',
          preview_url: 'https://cdn.test/signed/ts-0005.png',
          attachment_id: 'att-5',
          filename: 'TS-0005.png',
          candidate_count: 1,
          escalation: escalation(),
        }),
      ),
    );

    expect(screen.getByRole('img')).toHaveAttribute('src', 'https://cdn.test/signed/ts-0005.png');
    expect(screen.queryByText(/Escalated/)).not.toBeInTheDocument();
    expect(escalateButton()).not.toBeInTheDocument();
  });
});

describe('QuotationLineFileCell, drawing cell: nothing to escalate', () => {
  it('state 11: an off-catalogue line reads a dash and offers nothing', () => {
    renderCell(
      line(drawing({ state: 'off_catalog' }), {
        product_id: null,
        product_code: null,
      }),
    );

    expect(screen.getByText('-')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('an unsaved line (no server row yet) renders nothing at all', () => {
    const { container } = renderCell(null);
    expect(container).toBeEmptyDOMElement();
    expect(apiFetch).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------------------------
// REWORK (owner hand test 30 Oct): the Photo column escalates too. Same tile, same states, on
// `no_photos` only; `not_chosen` keeps today's photo behaviour; the request names kind "photo".
// ---------------------------------------------------------------------------------------------

function photo(overrides: Record<string, unknown> = {}) {
  return {
    state: 'no_photos',
    url: null,
    preview_url: null,
    attachment_id: null,
    filename: null,
    candidate_count: 0,
    candidates: [],
    escalation: null,
    ...overrides,
  };
}

function photoLine(product_image: Record<string, unknown>, overrides: Partial<QuotationLine> = {}) {
  return {
    ...line(drawing({ state: 'default', url: 'https://cdn.test/d.png', attachment_id: 'att-d' })),
    product_image,
    ...overrides,
  } as unknown as QuotationLine;
}

function renderPhotoCell(l: QuotationLine | null, editable = false) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <QuotationLineFileCell
        kind="photo"
        line={l}
        label="PRD-CCC-03"
        pickedId=""
        editable={editable}
        onPick={() => {}}
        onPreview={() => {}}
      />
    </QueryClientProvider>,
  );
}

const photoEscalateButton = () =>
  screen.queryByRole('button', { name: /Escalate missing photo for PRD-CCC-03/i });
const photoJoinButton = () =>
  screen.queryByRole('button', { name: 'Join the photo request for PRD-CCC-03' });

describe('QuotationLineFileCell, photo cell: no photo at all, escalate', () => {
  it('a saved catalogue line with no photo offers Escalate, hover names the product', () => {
    renderPhotoCell(photoLine(photo()));

    const button = photoEscalateButton();
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent('Escalate');
    expect(button).toHaveAttribute('title', 'Ask for a photo of PRD-CCC-03');
    expect(button).toBeEnabled();
    // The drawing flow's wording must not leak into the photo column.
    expect(screen.queryByRole('button', { name: /missing drawing/i })).not.toBeInTheDocument();
  });

  it('one click posts the photo kind to the line media-escalation endpoint, no dialog', async () => {
    apiFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ joined: false, escalation: escalation() }),
    });
    renderPhotoCell(photoLine(photo()));

    fireEvent.click(photoEscalateButton() as HTMLElement);

    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
    const [url, init] = apiFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/quotation-versions\/version-1\/lines\/line-1\/media-escalation$/);
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ kind: 'photo' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
  });

  it('is disabled and busy while the request is in flight, one request only', async () => {
    let release: (value: unknown) => void = () => {};
    apiFetch.mockReturnValue(new Promise((resolve) => { release = resolve; }));
    renderPhotoCell(photoLine(photo()));

    fireEvent.click(photoEscalateButton() as HTMLElement);

    await waitFor(() => expect(photoEscalateButton()).toBeDisabled());
    expect(photoEscalateButton()).toHaveAttribute('aria-busy', 'true');
    fireEvent.click(photoEscalateButton() as HTMLElement);
    expect(apiFetch).toHaveBeenCalledTimes(1);
    release({ ok: true, status: 200, json: async () => ({ joined: false, escalation: escalation() }) });
  });

  it('a refused escalate toasts the server message and returns to Escalate', async () => {
    apiFetch.mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: 'The marketing product team is not set up for this company',
          code: 'marketing_team_not_set_up',
        }),
        { status: 409, headers: { 'content-type': 'application/json' } },
      ),
    );
    renderPhotoCell(photoLine(photo()));

    fireEvent.click(photoEscalateButton() as HTMLElement);

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(String(toastError.mock.calls[0][0])).toContain('The marketing product team is not set up');
    await waitFor(() => expect(photoEscalateButton()).toBeEnabled());
  });

  it('resolved without a photo reads Escalate again, hover says when', () => {
    renderPhotoCell(
      photoLine(
        photo({
          escalation: escalation({
            tracking_id: null,
            opened_at: null,
            due_at: null,
            requester_count: 0,
            last_resolved_at: '2026-10-30T06:00:00.000Z',
          }),
        }),
      ),
    );

    const button = photoEscalateButton();
    expect(button).toBeInTheDocument();
    expect(button?.getAttribute('title') ?? '').toMatch(/Last request resolved 30 Oct/);
    expect(button?.getAttribute('title') ?? '').toMatch(/no photo on file/);
  });
});

describe('QuotationLineFileCell, photo cell: already escalated', () => {
  it('shows "Escalated <date>", people and due date, as a Join button', () => {
    renderPhotoCell(photoLine(photo({ escalation: escalation() })));

    expect(screen.getByText(/Escalated/).textContent).toMatch(/29 Oct/);
    expect(photoEscalateButton()).not.toBeInTheDocument();
    const hover = screen.getByTitle(/Escalated/);
    expect(hover.getAttribute('title')).toMatch(/by 2 people/);
    expect(hover.getAttribute('title')).toMatch(/Due /);
    expect(photoJoinButton()).toBeEnabled();
  });

  it('clicking the Escalated tile joins: posts the photo kind, disabled while in flight', async () => {
    let release: (value: unknown) => void = () => {};
    apiFetch.mockReturnValue(new Promise((resolve) => { release = resolve; }));
    renderPhotoCell(photoLine(photo({ escalation: escalation() })));

    fireEvent.click(photoJoinButton() as HTMLElement);

    await waitFor(() => expect(photoJoinButton()).toBeDisabled());
    expect(apiFetch).toHaveBeenCalledTimes(1);
    const [url, init] = apiFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/lines\/line-1\/media-escalation$/);
    expect(JSON.parse(String(init.body))).toEqual({ kind: 'photo' });
    release({ ok: true, status: 200, json: async () => ({ joined: true, escalation: escalation() }) });
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith('Already escalated: added you to the request'));
  });

  it('reads "Replied <date>" once the team responded, and still joins', () => {
    renderPhotoCell(photoLine(photo({ escalation: escalation({ responded_at: RESPONDED }) })));

    expect(screen.getByText(/Replied/).textContent).toMatch(/29 Oct/);
    expect(screen.getByTitle(/Responded/).getAttribute('title')).toMatch(/Responded 29 Oct/);
    expect(photoJoinButton()).toBeEnabled();
  });

  it('an open DRAWING request does not colour the photo cell: each kind reads its own escalation', () => {
    renderPhotoCell(
      photoLine(photo(), {
        technical_drawing: drawing({ escalation: escalation() }),
      }),
    );

    expect(photoEscalateButton()).toBeInTheDocument();
    expect(screen.queryByText(/Escalated/)).not.toBeInTheDocument();
  });

  it('colour follows the deadline: red when overdue', () => {
    renderPhotoCell(
      photoLine(photo({ escalation: escalation({ due_at: new Date(Date.now() - HOUR).toISOString() }) })),
    );
    expect(classesAround(screen.getByText(/Escalated/))).toMatch(/destructive|red-/);
  });
});

describe('QuotationLineFileCell, photo cell: no Escalate where a photo exists or cannot', () => {
  it('not_chosen (photographs exist, none picked) keeps today photo cell and offers no Escalate', () => {
    renderPhotoCell(
      photoLine(photo({ state: 'not_chosen', candidate_count: 2, candidates: [] })),
    );

    expect(photoEscalateButton()).not.toBeInTheDocument();
    expect(photoJoinButton()).not.toBeInTheDocument();
    expect(screen.queryByText(/Escalated|Replied/)).not.toBeInTheDocument();
  });

  it('not_chosen with a stale escalation on the payload still shows no flag', () => {
    renderPhotoCell(
      photoLine(photo({ state: 'not_chosen', candidate_count: 1, escalation: escalation() })),
    );
    expect(screen.queryByText(/Escalated/)).not.toBeInTheDocument();
    expect(photoJoinButton()).not.toBeInTheDocument();
  });

  it('a chosen photo shows the thumbnail and no Escalate', () => {
    renderPhotoCell(
      photoLine(
        photo({
          state: 'chosen',
          url: 'https://cdn.test/signed/p.png',
          preview_url: 'https://cdn.test/signed/p.png',
          attachment_id: 'att-p',
          filename: 'p.png',
          candidate_count: 1,
        }),
      ),
    );
    expect(photoEscalateButton()).not.toBeInTheDocument();
  });

  it('off_catalog reads a dash and offers nothing', () => {
    renderPhotoCell(
      photoLine(photo({ state: 'off_catalog' }), { product_id: null, product_code: null }),
    );
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('an unsaved line renders nothing and calls nothing', () => {
    const { container } = renderPhotoCell(null);
    expect(container).toBeEmptyDOMElement();
    expect(apiFetch).not.toHaveBeenCalled();
  });
});
