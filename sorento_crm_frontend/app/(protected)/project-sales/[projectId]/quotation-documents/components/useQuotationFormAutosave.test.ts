/**
 * QUOTE-AUTOSAVE kill tests: nothing typed on the proposal / quotation form is ever lost.
 *
 * Owner, 10 Nov 2026: "if I click outside then all the data will be gone". Each case is one way
 * that used to happen: navigating away mid-typing, closing the tab, going offline, a second tab.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';

import { AUTOSAVE_DEBOUNCE_MS } from '@/hooks/useAutosave';

const saveDraft = vi.fn();
const getHolder = vi.fn();
vi.mock('../../../_shared/services/quotationDocumentService', async () => {
  const actual = await vi.importActual<
    typeof import('../../../_shared/services/quotationDocumentService')
  >('../../../_shared/services/quotationDocumentService');
  return {
    ...actual,
    saveQuotationFormDraft: (...args: unknown[]) => saveDraft(...args),
    getQuotationDraftHolder: (...args: unknown[]) => getHolder(...args),
  };
});

import {
  DraftNotHolderError,
  type QuotationFormState,
} from '../../../_shared/services/quotationDocumentService';
import {
  clearMirror,
  HOLDER_POLL_MS,
  mirrorKey,
  mirrorPrefix,
  pickLocalCopy,
  readMirror,
  readMirrors,
  useQuotationFormAutosave,
  writeMirror,
} from './useQuotationFormAutosave';

const PROJECT = 'p-1';
const DOC = 'd-1';
const TOKEN = 'tok-tab-a';

function state(subject: string, total = '0'): QuotationFormState {
  return {
    v: 1,
    header: { subject_title: subject },
    letter: {},
    scopes: [],
    staged: {},
    removedIds: [],
    total,
  };
}

type Props = { state: QuotationFormState | null; isDirty: boolean };

function setup(initial: Props, documentId: string | null = DOC, token = TOKEN) {
  return renderHook(
    (props: Props) =>
      useQuotationFormAutosave({
        projectId: PROJECT,
        documentId,
        token,
        baseAt: '2026-11-10T06:00:00',
        state: props.state,
        isDirty: props.isDirty,
        ready: true,
      }),
    { initialProps: initial },
  );
}

async function tick(ms = AUTOSAVE_DEBOUNCE_MS) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe('useQuotationFormAutosave (QUOTE-AUTOSAVE)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    saveDraft.mockReset();
    saveDraft.mockResolvedValue({ updated_at: '2026-11-10T06:14:00' });
    getHolder.mockReset();
    getHolder.mockResolvedValue({ is_holder: true });
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("saves a typed edit to the DRAFT about a second later, with this tab's claim", async () => {
    const { rerender, result } = setup({ state: state('Opened'), isDirty: false });
    rerender({ state: state('Typed'), isDirty: true });
    expect(saveDraft).not.toHaveBeenCalled();
    await tick();
    expect(saveDraft).toHaveBeenCalledTimes(1);
    const [project, doc, value, token] = saveDraft.mock.calls[0];
    expect([project, doc, value.header.subject_title, token]).toEqual([PROJECT, DOC, 'Typed', TOKEN]);
    expect(result.current.status).toBe('saved');
  });

  it("a new proposal saves the person's own private draft (no document)", async () => {
    const { rerender } = setup({ state: state(''), isDirty: false }, null);
    rerender({ state: state('First word'), isDirty: true });
    await tick();
    expect(saveDraft.mock.calls[0][1]).toBeNull();
    expect(saveDraft.mock.calls[0][2].header.subject_title).toBe('First word');
  });

  it('never saves the starting point, nor a change made before anything was typed', async () => {
    const { rerender } = setup({ state: state('Opened'), isDirty: false });
    rerender({ state: state('Default from template'), isDirty: false });
    await tick(AUTOSAVE_DEBOUNCE_MS * 3);
    expect(saveDraft).not.toHaveBeenCalled();
  });

  // INSERT-SECTION-FIX B1: an edit taken back to the saved state (an empty heading inserted, then
  // dropped on blur) leaves the form clean again. That change must reach the draft too, or the
  // draft keeps the undone edit and the form reopens with it.
  it('an edit undone back to the saved state is saved too, so the draft no longer holds it', async () => {
    const { rerender } = setup({ state: state('Opened'), isDirty: false });
    rerender({ state: state('Opened, empty heading added'), isDirty: true });
    await tick();
    expect(saveDraft).toHaveBeenCalledTimes(1);
    rerender({ state: state('Opened'), isDirty: false });
    await tick();
    expect(saveDraft).toHaveBeenCalledTimes(2);
    expect(saveDraft.mock.calls[1][2].header.subject_title).toBe('Opened');
  });

  it('an edit undone inside the debounce sends the undone state, not the edit', async () => {
    const { rerender } = setup({ state: state('Opened'), isDirty: false });
    rerender({ state: state('Opened, empty heading added'), isDirty: true });
    rerender({ state: state('Opened'), isDirty: false });
    await tick(AUTOSAVE_DEBOUNCE_MS * 3);
    expect(saveDraft).toHaveBeenCalled();
    expect(saveDraft.mock.calls.at(-1)?.[2].header.subject_title).toBe('Opened');
  });

  it('a different total alone is not an edit (opening a saved scope re-sums it)', async () => {
    const { rerender } = setup({ state: state('Opened', '100'), isDirty: true });
    rerender({ state: state('Opened', '100.00'), isDirty: true });
    await tick(AUTOSAVE_DEBOUNCE_MS * 3);
    expect(saveDraft).not.toHaveBeenCalled();
  });

  it('navigating away mid-typing still saves: the unmount flushes the pending edit', async () => {
    const { rerender, unmount } = setup({ state: state('Opened'), isDirty: false });
    rerender({ state: state('Half typed'), isDirty: true });
    await tick(200); // well inside the debounce
    expect(saveDraft).not.toHaveBeenCalled();
    unmount();
    await tick(0);
    expect(saveDraft).toHaveBeenCalledTimes(1);
    expect(saveDraft.mock.calls[0][2].header.subject_title).toBe('Half typed');
    // An in-app route change is not held to keepalive's 64KB cap.
    expect(saveDraft.mock.calls[0][4]).toEqual({ keepalive: false });
  });

  it('closing the tab or refreshing saves with keepalive, so the request outlives the page', async () => {
    const { rerender } = setup({ state: state('Opened'), isDirty: false });
    rerender({ state: state('Closing'), isDirty: true });
    act(() => {
      window.dispatchEvent(new Event('pagehide'));
    });
    await tick(0);
    expect(saveDraft).toHaveBeenCalledTimes(1);
    expect(saveDraft.mock.calls[0][4]).toEqual({ keepalive: true });
  });

  it('offline then online: the failed save is kept in this browser and resent on reconnect', async () => {
    saveDraft.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    const { rerender, result } = setup({ state: state('Opened'), isDirty: false });
    rerender({ state: state('Typed offline'), isDirty: true });
    await tick();
    expect(result.current.status).toBe('error');
    // The unsent copy survives even a closed tab.
    const mirror = readMirror(mirrorKey(PROJECT, DOC, TOKEN));
    expect(mirror?.doc.header.subject_title).toBe('Typed offline');
    expect(mirror?.token).toBe(TOKEN);
    // Made on top of the server version this tab opened on.
    expect(mirror?.baseAt).toBe('2026-11-10T06:00:00');

    act(() => {
      window.dispatchEvent(new Event('online'));
    });
    await tick(0);
    expect(saveDraft).toHaveBeenCalledTimes(2);
    expect(saveDraft.mock.calls[1][2].header.subject_title).toBe('Typed offline');
    expect(result.current.status).toBe('saved');
    expect(readMirror(mirrorKey(PROJECT, DOC, TOKEN))).toBeNull();
  });

  it('two tabs: a refused write locks this tab view-only, naming who opened it, and saves no more', async () => {
    saveDraft.mockRejectedValueOnce(
      new DraftNotHolderError('opened elsewhere', {
        holder_name: 'Ben',
        holder_at: '2026-11-10T06:30:00',
      }),
    );
    const { rerender, result } = setup({ state: state('Opened'), isDirty: false });
    rerender({ state: state('Older tab'), isDirty: true });
    await tick();
    expect(result.current.viewOnly).toEqual({ holderName: 'Ben', holderAt: '2026-11-10T06:30:00' });
    // The server kept this tab's state as History, so the local copy is not needed.
    expect(readMirror(mirrorKey(PROJECT, DOC, TOKEN))).toBeNull();

    rerender({ state: state('Older tab again'), isDirty: true });
    await tick(AUTOSAVE_DEBOUNCE_MS * 3);
    expect(saveDraft).toHaveBeenCalledTimes(1);
  });

  it('two tabs: the check lands mid-debounce: what is pending is sent (kept as History), then it locks', async () => {
    getHolder.mockResolvedValue({
      is_holder: false,
      holder_name: 'Aina',
      holder_at: '2026-11-10T07:00:00',
    });
    saveDraft.mockRejectedValueOnce(new DraftNotHolderError('x', { holder_name: 'Aina' }));
    const { rerender, result } = setup({ state: state('Opened'), isDirty: false });
    await tick(HOLDER_POLL_MS - 300);
    // Typed 300 ms before the check: still inside the debounce when the check fires.
    rerender({ state: state('Typed just before'), isDirty: true });
    await tick(300);
    expect(getHolder).toHaveBeenCalledWith(PROJECT, DOC, TOKEN);
    expect(saveDraft).toHaveBeenCalledTimes(1);
    expect(saveDraft.mock.calls[0][2].header.subject_title).toBe('Typed just before');
    expect(result.current.viewOnly?.holderName).toBe('Aina');
  });

  it('two tabs: an idle tab with nothing pending still locks when another tab opened the draft', async () => {
    getHolder.mockResolvedValue({ is_holder: false, holder_name: 'Aina', holder_at: null });
    const { result } = setup({ state: state('Opened'), isDirty: false });
    expect(result.current.viewOnly).toBeNull();
    await tick(HOLDER_POLL_MS);
    expect(result.current.viewOnly).toEqual({ holderName: 'Aina', holderAt: null });
    expect(saveDraft).not.toHaveBeenCalled();
  });

  it('Discard draft: an edit already waiting when Discard starts is not sent either', async () => {
    const { rerender, result, unmount } = setup({ state: state('Opened'), isDirty: false });
    rerender({ state: state('Typed just before Discard'), isDirty: true });
    await tick(200); // pending in the debounce
    act(() => {
      result.current.setPaused(true);
    });
    unmount(); // the navigation after the commit flushes what was pending
    await tick(AUTOSAVE_DEBOUNCE_MS * 2);
    expect(saveDraft).not.toHaveBeenCalled();
  });

  it('two tabs in one browser keep separate local copies, so neither erases the other', async () => {
    saveDraft.mockRejectedValue(new TypeError('Failed to fetch'));
    const holder = setup({ state: state('Opened'), isDirty: false }, DOC, 'tok-holder');
    const older = setup({ state: state('Opened'), isDirty: false }, DOC, 'tok-older');
    holder.rerender({ state: state('Holder offline'), isDirty: true });
    older.rerender({ state: state('Older offline'), isDirty: true });
    await tick();
    const copies = readMirrors(mirrorPrefix(PROJECT, DOC)).map((m) => m.value.doc.header.subject_title);
    expect(copies.sort()).toEqual(['Holder offline', 'Older offline']);
  });

  it("after a save, the local copy's base is the server's new version", async () => {
    saveDraft.mockResolvedValueOnce({ updated_at: '2026-11-10T06:20:00' });
    saveDraft.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    const { rerender } = setup({ state: state('Opened'), isDirty: false });
    rerender({ state: state('First'), isDirty: true });
    await tick();
    rerender({ state: state('Second, offline'), isDirty: true });
    await tick();
    expect(readMirror(mirrorKey(PROJECT, DOC, TOKEN))?.baseAt).toBe('2026-11-10T06:20:00');
  });

  it('an edit typed while a save is on its way keeps its local copy, re-based on the new version', async () => {
    let land: (value: { updated_at: string }) => void = () => undefined;
    saveDraft.mockImplementationOnce(
      () => new Promise((resolve) => {
        land = resolve;
      }),
    );
    saveDraft.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    const { rerender } = setup({ state: state('Opened'), isDirty: false });
    rerender({ state: state('A'), isDirty: true });
    await tick(); // A is on its way
    rerender({ state: state('B, typed meanwhile'), isDirty: true });
    await act(async () => {
      land({ updated_at: '2026-11-10T06:30:00' });
    });
    const copy = readMirror(mirrorKey(PROJECT, DOC, TOKEN));
    expect(copy?.doc.header.subject_title).toBe('B, typed meanwhile');
    expect(copy?.baseAt).toBe('2026-11-10T06:30:00');
    await tick(); // B fails offline: still there, on the right base, for the next open
    expect(readMirror(mirrorKey(PROJECT, DOC, TOKEN))?.baseAt).toBe('2026-11-10T06:30:00');
  });

  it('Discard draft pauses saving: nothing typed during the countdown revives the draft', async () => {
    const { rerender, result, unmount } = setup({ state: state('Opened'), isDirty: false });
    act(() => {
      result.current.setPaused(true);
    });
    rerender({ state: state('During countdown'), isDirty: true });
    await tick(AUTOSAVE_DEBOUNCE_MS * 2);
    unmount(); // the navigation after the commit
    await tick(0);
    expect(saveDraft).not.toHaveBeenCalled();
  });

  it('resume() sends a state the page reopened on that the server never received', async () => {
    const { result } = setup({ state: state('Opened'), isDirty: false });
    act(() => {
      result.current.resume(state('From last night'));
    });
    await tick();
    expect(saveDraft).toHaveBeenCalledTimes(1);
    expect(saveDraft.mock.calls[0][2].header.subject_title).toBe('From last night');
  });
});

describe('local mirror', () => {
  it('reads, writes and clears, and never throws when storage is blocked', () => {
    const key = mirrorKey(PROJECT, null, TOKEN);
    expect(key).toBe(`quotation-form-draft:new:${PROJECT}:${TOKEN}`);
    writeMirror(key, { token: TOKEN, baseAt: null, doc: state('x'), at: 'now' });
    expect(readMirror(key)?.doc.header.subject_title).toBe('x');
    clearMirror(key);
    expect(readMirror(key)).toBeNull();

    const getSpy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    const setSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(readMirror(key)).toBeNull();
    expect(() =>
      writeMirror(key, { token: TOKEN, baseAt: null, doc: state('x'), at: 'now' }),
    ).not.toThrow();
    getSpy.mockRestore();
    setSpy.mockRestore();
  });
});

describe('pickLocalCopy: what a reopened form takes from this browser', () => {
  const prefix = mirrorPrefix(PROJECT, DOC);
  const put = (token: string, baseAt: string | null, subject: string, at: string) =>
    writeMirror(mirrorKey(PROJECT, DOC, token), { token, baseAt, doc: state(subject), at });

  beforeEach(() => window.localStorage.clear());

  it('reopens the newest copy made on the version the server still has, and sends the rest as History', async () => {
    put('tok-old-tab', '2026-11-10T06:00:00', 'older tab', '2026-11-10T06:01:00Z');
    put('tok-new-tab', '2026-11-10T06:00:00', 'newer tab', '2026-11-10T06:02:00Z');
    put('tok-stale', '2026-11-10T05:00:00', 'server moved past it', '2026-11-10T05:30:00Z');
    const send = vi.fn(async (doc: QuotationFormState, token: string) => ({ doc, token }));
    const doc = pickLocalCopy(prefix, '2026-11-10T06:00:00', 'tok-now', send);
    expect(doc?.header.subject_title).toBe('newer tab');
    expect(send.mock.calls.map(([doc, token]) => [doc.header.subject_title, token]).sort()).toEqual([
      ['older tab', 'tok-old-tab'],
      ['server moved past it', 'tok-stale'],
    ]);
    await act(async () => undefined);
    expect(readMirrors(prefix)).toEqual([]);
  });

  it('keeps a copy whose send failed (offline, a locked document) for the next open', async () => {
    put('tok-stale', '2026-11-10T05:00:00', 'not delivered', '2026-11-10T05:30:00Z');
    const send = vi.fn(async () => {
      throw new TypeError('Failed to fetch');
    });
    expect(pickLocalCopy(prefix, '2026-11-10T06:00:00', 'tok-now', send)).toBeNull();
    await act(async () => undefined);
    expect(readMirrors(prefix).map((m) => m.value.doc.header.subject_title)).toEqual(['not delivered']);
  });

  it('drops a copy once the server kept it (409, a conflict History entry)', async () => {
    put('tok-stale', '2026-11-10T05:00:00', 'kept as History', '2026-11-10T05:30:00Z');
    const send = vi.fn(async () => {
      throw new DraftNotHolderError('kept', {});
    });
    pickLocalCopy(prefix, '2026-11-10T06:00:00', 'tok-now', send);
    await act(async () => undefined);
    expect(readMirrors(prefix)).toEqual([]);
  });

  it('nothing local: the server draft opens', () => {
    expect(pickLocalCopy(prefix, null, 'tok-now', vi.fn())).toBeNull();
  });
});
