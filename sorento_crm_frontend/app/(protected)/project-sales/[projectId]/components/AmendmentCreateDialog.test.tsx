/**
 * OCN-ORDER-CHANGE-NOTICE UAC E1 / E2 (frontend half, red-first): the amendment dialog gains one
 * optional, clearable "Order change notice" select. Default = "Draft a new notice from this change"
 * (today's behaviour); picking one of this project's notices links it and drafts no second one.
 * Component: ./AmendmentCreateDialog.tsx (named export).
 *
 * Contract this file fixes for the coder:
 *  - new prop `projectId: string`; the dialog reads the candidates itself through
 *    `listProjectOrderChangeNotices(projectId)` in
 *    app/(protected)/procurement-management/order-change-notices/services/orderChangeNoticeService.ts
 *    (GET /api/v1/project-sales/projects/{id}/order-change-notices, the F1 envelope `{data: rows}`);
 *  - an option reads "<ocn_number>, <type>, <status word>" (e.g. "OCN26-0302, Exchange, Approved"),
 *    never an id;
 *  - `onConfirm(reason, ocnId)`: ocnId is the picked notice's id, and null / undefined when none is
 *    picked (the parent maps it to `ocn_id` in the create body);
 *  - after a pick the success text must not say a notice was "drafted" (none was).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();

const svc = vi.hoisted(() => ({ project: vi.fn() }));
vi.mock(
  '@/app/(protected)/procurement-management/order-change-notices/services/orderChangeNoticeService',
  async (importOriginal) => {
    const actual = await importOriginal<
      typeof import('@/app/(protected)/procurement-management/order-change-notices/services/orderChangeNoticeService')
    >();
    return { ...actual, listProjectOrderChangeNotices: (...a: unknown[]) => svc.project(...a) };
  },
);

import { AmendmentCreateDialog } from './AmendmentCreateDialog';
import { UUID_RE, ocnRow } from '@/app/(protected)/procurement-management/order-change-notices/components/ocnTestData';

const PROJECT_ID = '0c4f1d7e-6a53-4e0b-8d0e-3c1b8f9a2d02';
const OCN_A = 'b2c3d4e5-0302-4a00-8000-000000000302';
const OCN_B = 'b2c3d4e5-0304-4a00-8000-000000000304';
const DEFAULT_OPTION = 'Draft a new notice from this change';
const REASON = 'Customer revised PO (R1), model change';

const PREVIEW = {
  from: { kind: 'po', id: 'v1', version_no: 1, label: 'Version 1' },
  to: { kind: 'po', id: 'v2', version_no: 2, label: 'Version 2' },
  verb_summary: { DELAY: 1, CHANGE_MODEL: 1 },
  rows: [{}, {}],
  unmatched: [],
};

function mount(overrides: Partial<React.ComponentProps<typeof AmendmentCreateDialog>> = {}) {
  const onConfirm = vi.fn(async () => ({
    amendment_id: 'am-1',
    ocn_id: 'ocn-x',
    ocn_number: 'OCN26-0305',
    verb_summary: {},
  }));
  const onDone = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <AmendmentCreateDialog
        {...({
          preview: PREVIEW,
          projectId: PROJECT_ID,
          onDone,
          onConfirm,
          submitting: false,
          ...overrides,
        } as React.ComponentProps<typeof AmendmentCreateDialog>)}
      />
    </QueryClientProvider>,
  );
  return { onConfirm, onDone };
}

const select = () => screen.getByLabelText(/order change notice/i);
const typeReason = (text = REASON) =>
  fireEvent.change(screen.getByLabelText(/^Reason/), { target: { value: text } });
const confirm = () => fireEvent.click(screen.getByRole('button', { name: /^create the amendment$/i }));

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  svc.project.mockResolvedValue({
    data: [
      ocnRow({ id: OCN_A, ocn_number: 'OCN26-0302', change_type_name: 'Exchange', status: 'approved', approval_status: 'approved' }),
      ocnRow({ id: OCN_B, ocn_number: 'OCN26-0304', change_type_name: 'Advance', status: 'approved', approval_status: 'approved' }),
    ],
    pagination: { total: 2, page: 1, limit: 200 },
    empty: false,
  });
});
afterEach(() => cleanup());

describe('E1 the default is unchanged: draft a new notice', () => {
  it('shows an optional "Order change notice" select that starts on the default', async () => {
    mount();
    expect(select()).toBeTruthy();
    expect(screen.getAllByText(DEFAULT_OPTION).length).toBeGreaterThan(0);
  });

  it('confirming without a pick passes no notice id', async () => {
    const { onConfirm } = mount();
    typeReason();
    confirm();
    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    const [reason, ocnId] = onConfirm.mock.calls[0] as unknown as [string, string | null | undefined];
    expect(reason).toBe(REASON);
    expect(ocnId ?? null).toBeNull();
  });

  it('still needs the reason, and Cancel confirms nothing', async () => {
    const { onConfirm, onDone } = mount();
    expect((screen.getByRole('button', { name: /^create the amendment$/i }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));
    expect(onDone).toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('after a new notice is drafted, the dialog says so and names it', async () => {
    mount();
    typeReason();
    confirm();
    expect(await screen.findByText(/OCN26-0305 is drafted/)).toBeTruthy();
  });
});

describe('E2 pick an existing notice of this project', () => {
  it('asks for this project’s notices only', async () => {
    mount();
    await waitFor(() => expect(svc.project).toHaveBeenCalledWith(PROJECT_ID));
  });

  it('lists each notice as number, type and status in words, never an id', async () => {
    mount();
    fireEvent.click(select());
    expect(await screen.findByRole('option', { name: 'OCN26-0302, Exchange, Approved' })).toBeTruthy();
    expect(screen.getByRole('option', { name: 'OCN26-0304, Advance, Approved' })).toBeTruthy();
    expect(document.body.textContent).not.toMatch(UUID_RE);
  });

  it('confirming with a pick passes that notice’s id', async () => {
    const { onConfirm } = mount();
    fireEvent.click(select());
    fireEvent.click(await screen.findByRole('option', { name: 'OCN26-0302, Exchange, Approved' }));
    typeReason();
    confirm();
    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    expect(onConfirm.mock.calls[0]).toEqual([REASON, OCN_A]);
  });

  it('is clearable: clearing the pick goes back to drafting a new notice', async () => {
    const { onConfirm } = mount();
    fireEvent.click(select());
    fireEvent.click(await screen.findByRole('option', { name: 'OCN26-0304, Advance, Approved' }));
    fireEvent.pointerDown(within(select()).getByRole('button', { name: 'Clear selection' }));
    typeReason();
    confirm();
    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    const [, ocnId] = onConfirm.mock.calls[0] as unknown as [string, string | null | undefined];
    expect(ocnId ?? null).toBeNull();
  });

  it('after a link, the dialog does not claim a notice was drafted', async () => {
    const onConfirm = vi.fn(async () => ({
      amendment_id: 'am-1',
      ocn_id: OCN_A,
      ocn_number: 'OCN26-0302',
      verb_summary: {},
    }));
    mount({ onConfirm } as never);
    fireEvent.click(select());
    fireEvent.click(await screen.findByRole('option', { name: 'OCN26-0302, Exchange, Approved' }));
    typeReason();
    confirm();
    expect(await screen.findByText(/OCN26-0302/)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/drafted/i);
  });
});

describe('E2 empty and error states of the select', () => {
  it('with no notices on the project the default stays usable', async () => {
    svc.project.mockResolvedValue({ data: [], pagination: { total: 0, page: 1, limit: 200 }, empty: true });
    const { onConfirm } = mount();
    typeReason();
    confirm();
    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
  });

  it('if the notices cannot be read the amendment can still be created with a new notice', async () => {
    svc.project.mockRejectedValue(new Error('Could not load the notices'));
    const { onConfirm } = mount();
    typeReason();
    confirm();
    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
  });
});
