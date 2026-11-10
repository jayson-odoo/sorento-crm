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
  readMirror,
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

function setup(initial: Props, documentId: string | null = DOC) {
  return renderHook(
    (props: Props) =>
      useQuotationFormAutosave({
        projectId: PROJECT,
        documentId,
        token: TOKEN,
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
    const mirror = readMirror(mirrorKey(PROJECT, DOC));
    expect(mirror?.doc.header.subject_title).toBe('Typed offline');
    expect(mirror?.token).toBe(TOKEN);

    act(() => {
      window.dispatchEvent(new Event('online'));
    });
    await tick(0);
    expect(saveDraft).toHaveBeenCalledTimes(2);
    expect(saveDraft.mock.calls[1][2].header.subject_title).toBe('Typed offline');
    expect(result.current.status).toBe('saved');
    expect(readMirror(mirrorKey(PROJECT, DOC))).toBeNull();
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
    expect(readMirror(mirrorKey(PROJECT, DOC))).toBeNull();

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
    const key = mirrorKey(PROJECT, null);
    expect(key).toBe(`quotation-form-draft:new:${PROJECT}`);
    writeMirror(key, { token: TOKEN, doc: state('x'), at: 'now' });
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
    expect(() => writeMirror(key, { token: TOKEN, doc: state('x'), at: 'now' })).not.toThrow();
    getSpy.mockRestore();
    setSpy.mockRestore();
  });
});
