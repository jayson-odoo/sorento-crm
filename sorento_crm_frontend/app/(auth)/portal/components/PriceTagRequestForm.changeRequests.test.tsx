/**
 * The change-request rail on the portal read view (r9 S2/D5, AC-S2-2, AC-S2-3).
 *
 * There is no "Request changes" button to press first. The rail and the Send
 * button are turned on by the first PIN, and Send posts the whole round in one
 * call - so a salesperson can place five pins, delete two, and the request
 * changes state exactly once.
 *
 * The real `DesignViewer` / `DesignPinLayer` are used here rather than stubs:
 * "clicking the tag is the change request" is the behaviour, and a stub with a
 * button labelled "place a pin" would assert nothing about it.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

class StubResizeObserver {
  callback: ResizeObserverCallback;
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }
  observe() {
    this.callback(
      [{ contentRect: { width: 640, height: 480 } } as ResizeObserverEntry],
      this as unknown as ResizeObserver,
    );
  }
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as Record<string, unknown>).ResizeObserver =
  StubResizeObserver;

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn() }),
}));

const toasts = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
}));
vi.mock('@/lib/toast', () => ({ toast: toasts }));

vi.mock('@/lib/dealer-kit/fonts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/dealer-kit/fonts')>();
  return {
    ...actual,
    ensureFontsLoaded: vi.fn(async () => {}),
    ensureSeedFontsLoaded: vi.fn(async () => {}),
  };
});

vi.mock('../lib/price-tag-request-service', async () => {
  const { computeLinePricing } = await import('@/lib/dealer-kit/mock-line-pricing');
  return {
  lookupLinePricing: vi.fn(async (mode: string, lines: unknown[]) =>
    computeLinePricing(mode as 'list' | 'selling', lines as never),
  ),
  lookupDebtors: vi.fn(async () => []),
  lookupPromotions: vi.fn(async () => []),
  lookupTagItems: vi.fn(async () => []),
  // The form asks for a product's packages on every pick since the combos
  // slice; a mock without it throws before the page renders at all.
  lookupProductCombos: vi.fn(async () => ({ host_guarded: false, combos: [] })),
  getRequest: vi.fn(),
  createRequest: vi.fn(),
  updateRequest: vi.fn(),
  deleteRequest: vi.fn(),
  submitRequest: vi.fn(),
  approveRequest: vi.fn(),
  requestChanges: vi.fn(),
  listReviewComments: vi.fn(async () => []),
  collectRequest: vi.fn(),
  downloadPriceTagPdf: vi.fn(),
  };
});

vi.mock('../lib/portal-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/portal-client')>();
  return {
    ...actual,
    getPriceTagDesign: vi.fn(),
    uploadAttachment: vi.fn(),
    fetchSubmissionNeighbours: vi.fn(async () => ({ prev: null, next: null })),
  };
});

vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: () => null,
}));

vi.mock('@/components/common/DetailActionsMenu', () => ({
  __esModule: true,
  DetailActionsMenu: () => null,
}));

import { getRequest, requestChanges } from '../lib/price-tag-request-service';
import { getPriceTagDesign } from '../lib/portal-client';
import { PriceTagRequestForm } from './PriceTagRequestForm';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

const REQUEST = {
  id: 'req-1',
  doc_number: 'PT-202609-0001',
  debtor_code: 'ZZTD01',
  debtor_name: 'ZZT Dealer',
  promotion_id: null,
  promotion_name: null,
  needed_by_date: '2026-09-20',
  notes: null,
  status: 'proof_ready',
  print_by: 'office',
  line_count: 1,
  created_at: '2026-09-01T00:00:00Z',
  portal_draft_at: null,
  contact_id: 'contact-1',
  has_completed_export: false,
  lines: [
    {
      id: 'line-1',
      line_type: 'product',
      product_id: 'prod-1',
      product_set_id: null,
      name: 'ZZT Kitchen Sink',
      code: 'ZZT-SINK-1',
      show_promo_price: false,
      quantity: 1,
      included_accessories: null,
      // One tag per line at submit (combos D3). Its id IS the line id here, so
      // every id this file already asserts on keeps meaning what it meant.
      tags: [{ id: 'line-1', label: '1a', quantity: 1 }],
    },
  ],
  attachments: [],
};

const DESIGN = {
  page_id: 'page-1',
  version: 2,
  source: 'version' as const,
  doc: {
    kind: 'tag_sheet',
    imposition: { page_width_mm: 210, page_height_mm: 297 },
    sheets: [
      {
        id: 'sheet-1',
        tags: [
          {
            id: 'tag-1',
            request_tag_id: 'line-1',
            x_mm: 20,
            y_mm: 30,
            width_mm: 80,
            height_mm: 40,
            layers: [],
          },
        ],
      },
    ],
  },
  resolvedData: {},
  assets: {},
  images: {},
  fonts: [],
};

/** Place a pin by clicking the tag, then type the comment and Add it. */
async function placePin(body: string) {
  const hit = await screen.findByTestId('pin-hit-line-1');
  hit.getBoundingClientRect = () =>
    ({ left: 100, top: 200, width: 200, height: 100, right: 300, bottom: 300 }) as DOMRect;
  fireEvent.pointerDown(hit, { clientX: 150, clientY: 250 });
  fireEvent.pointerUp(hit, { clientX: 150, clientY: 250 });
  const editor = await screen.findByTestId('pin-comment-editor');
  fireEvent.change(within(editor).getByRole('textbox'), { target: { value: body } });
  fireEvent.click(within(editor).getByRole('button', { name: 'Add' }));
}

async function renderReadView() {
  const result = render(<PriceTagRequestForm requestId="req-1" />);
  await screen.findByText('PT-202609-0001');
  return result;
}

beforeEach(() => {
  vi.clearAllMocks();
  asMock(getRequest).mockResolvedValue(REQUEST);
  asMock(getPriceTagDesign).mockResolvedValue(DESIGN);
  asMock(requestChanges).mockResolvedValue({
    status: 'changes_requested',
    comments: [],
  });
});

describe('the rail turns on with the first pin (AC-S2-2)', () => {
  it('has no Send button and no "Request changes" mode before any pin', async () => {
    await renderReadView();
    // The rail's own instruction sentence was retired in the review round; what
    // this test is about is that neither a mode nor a Send exists until the
    // salesperson has actually pointed at something.
    await screen.findByTestId('pin-hit-line-1');

    expect(screen.queryByTestId('send-change-requests')).toBeNull();
    expect(
      screen.queryByRole('button', { name: /Request changes/i }),
    ).toBeNull();
  });

  it('says `Send 1 change request` at one pin and lists it with its line code', async () => {
    await renderReadView();

    await placePin('Make the price bigger');

    const send = await screen.findByTestId('send-change-requests');
    expect(send).toHaveTextContent('Send 1 change request');
    expect(screen.getAllByText('ZZT-SINK-1').length).toBeGreaterThan(0);
    expect(screen.getByText('Make the price bigger')).toBeInTheDocument();
  });

  it('pluralises at two pins', async () => {
    await renderReadView();

    await placePin('Make the price bigger');
    await placePin('Move the logo');

    expect(await screen.findByTestId('send-change-requests')).toHaveTextContent(
      'Send 2 change requests',
    );
  });

  it('scrolls the change-request rail into view when the first pin lands (review-round leftover)', async () => {
    // jsdom has no scrollIntoView; the source can only be guarded with an
    // optional chain, never rely on it existing.
    const scrollIntoView = vi.fn();
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = scrollIntoView;

    try {
      await renderReadView();

      await placePin('Make the price bigger');
      await screen.findByTestId('send-change-requests');

      expect(scrollIntoView).toHaveBeenCalledTimes(1);

      scrollIntoView.mockClear();
      await placePin('Move the logo');

      // Only the FIRST pin scrolls - a second pin lands where the salesperson
      // already is, not somewhere that yanks the page again.
      expect(scrollIntoView).not.toHaveBeenCalled();
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });

  it('a pin can be deleted before it is sent, and the button goes with the last one', async () => {
    await renderReadView();
    await placePin('Make the price bigger');
    await screen.findByTestId('send-change-requests');

    fireEvent.click(
      screen.getByRole('button', { name: 'Delete change request 1' }),
    );

    await waitFor(() =>
      expect(screen.queryByTestId('send-change-requests')).toBeNull(),
    );
  });

  it('a general note alone is enough to send', async () => {
    await renderReadView();

    fireEvent.change(
      await screen.findByLabelText(/Anything else \(optional\)/),
      { target: { value: 'The whole thing is too busy' } },
    );

    expect(await screen.findByTestId('send-change-requests')).toHaveTextContent(
      'Send change request',
    );
  });
});

describe('Send (AC-S2-3)', () => {
  it('posts every pin and the note in ONE call', async () => {
    await renderReadView();
    await placePin('Make the price bigger');
    await placePin('Move the logo');
    fireEvent.change(await screen.findByLabelText(/Anything else \(optional\)/), {
      target: { value: 'Too busy overall' },
    });

    fireEvent.click(screen.getByTestId('send-change-requests'));

    await waitFor(() => expect(requestChanges).toHaveBeenCalledTimes(1));
    const [id, payload] = asMock(requestChanges).mock.calls[0];
    expect(id).toBe('req-1');
    expect(payload.comments).toHaveLength(2);
    expect(payload.comments[0]).toMatchObject({ tag_id: 'line-1', w: 0, h: 0 });
    expect(payload.comments[0].x).toBeCloseTo(0.25, 5);
    expect(payload.note).toBe('Too busy overall');
  });

  it('reports and returns to the list', async () => {
    await renderReadView();
    await placePin('Make the price bigger');

    fireEvent.click(await screen.findByTestId('send-change-requests'));

    await waitFor(() => expect(toasts.success).toHaveBeenCalled());
    await waitFor(() => expect(push).toHaveBeenCalled());
  });

  it('a refusal keeps the pins so the round is not lost', async () => {
    asMock(requestChanges).mockRejectedValue(new Error('Not waiting on you'));
    await renderReadView();
    await placePin('Make the price bigger');

    fireEvent.click(await screen.findByTestId('send-change-requests'));

    await waitFor(() => expect(toasts.error).toHaveBeenCalled());
    expect(screen.getByText('Make the price bigger')).toBeInTheDocument();
    expect(screen.getByTestId('send-change-requests')).toBeInTheDocument();
  });
});

describe('a design that is not waiting on the salesperson', () => {
  it('offers no rail, no Send and no pin placing at changes_requested', async () => {
    asMock(getRequest).mockResolvedValue({
      ...REQUEST,
      status: 'changes_requested',
    });
    await renderReadView();

    await screen.findByText('PT-202609-0001');
    expect(screen.queryByTestId('pin-hit-line-1')).toBeNull();
    expect(screen.queryByTestId('send-change-requests')).toBeNull();
    expect(screen.queryByRole('button', { name: /Approve/ })).toBeNull();
  });
});
