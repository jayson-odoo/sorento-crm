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
vi.mock('../../../_shared/services/quotationDocumentService', async () => {
  const actual = await vi.importActual<
    typeof import('../../../_shared/services/quotationDocumentService')
  >('../../../_shared/services/quotationDocumentService');
  return { ...actual, saveQuotationFormDraft: (...args: unknown[]) => saveDraft(...args) };
});

import {
  StaleDraftError,
  type QuotationDocument,
  type QuotationFormState,
} from '../../../_shared/services/quotationDocumentService';
import {
  clearMirror,
  mirrorKey,
  readMirror,
  useQuotationFormAutosave,
  writeMirror,
} from './useQuotationFormAutosave';

const PROJECT = 'p-1';
const DOC = 'd-1';

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

type Props = {
  state: QuotationFormState | null;
  isDirty: boolean;
  documentId?: string | null;
  rev?: number | null;
  create?: (s: QuotationFormState) => Promise<QuotationDocument>;
  onCreated?: (d: QuotationDocument) => void;
};

function setup(initial: Props) {
  const create = initial.create ?? vi.fn();
  const onCreated = initial.onCreated ?? vi.fn();
  return renderHook(
    (props: Props) =>
      useQuotationFormAutosave({
        projectId: PROJECT,
        initialDocumentId: initial.documentId === undefined ? DOC : initial.documentId,
        initialRev: initial.rev === undefined ? 3 : initial.rev,
        initialHasDraft: false,
        state: props.state,
        isDirty: props.isDirty,
        ready: true,
        create,
        onCreated,
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
    saveDraft.mockImplementation(async (_p, _d, _doc, baseRev: number) => ({
      rev: baseRev + 1,
      updated_at: '2026-11-10T06:14:00',
    }));
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('saves a typed edit to the DRAFT about a second later, on the revision it opened on', async () => {
    const { rerender, result } = setup({ state: state('Opened'), isDirty: false });
    rerender({ state: state('Typed'), isDirty: true });
    expect(saveDraft).not.toHaveBeenCalled();
    await tick();
    expect(saveDraft).toHaveBeenCalledTimes(1);
    expect(saveDraft.mock.calls[0][1]).toBe(DOC);
    expect(saveDraft.mock.calls[0][2].header.subject_title).toBe('Typed');
    expect(saveDraft.mock.calls[0][3]).toBe(3);
    expect(result.current.rev.current).toBe(4);
    expect(result.current.status).toBe('saved');
    expect(result.current.hasDraft).toBe(true);
  });

  it('never saves the starting point, nor a change made before anything was typed', async () => {
    const { rerender } = setup({ state: state('Opened'), isDirty: false });
    // A template default landing late: not an edit.
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
    expect(mirror?.baseRev).toBe(3);

    act(() => {
      window.dispatchEvent(new Event('online'));
    });
    await tick(0);
    expect(saveDraft).toHaveBeenCalledTimes(2);
    expect(saveDraft.mock.calls[1][2].header.subject_title).toBe('Typed offline');
    expect(result.current.status).toBe('saved');
    expect(readMirror(mirrorKey(PROJECT, DOC))).toBeNull();
  });

  it('two tabs: a stale save stops this tab and reports who wrote, and saves nothing more', async () => {
    saveDraft.mockRejectedValueOnce(
      new StaleDraftError('stale', {
        rev: 7,
        updated_at: '2026-11-10T06:30:00',
        updated_by_name: 'Ben',
      }),
    );
    const { rerender, result } = setup({ state: state('Opened'), isDirty: false });
    rerender({ state: state('Tab B'), isDirty: true });
    await tick();
    expect(result.current.conflict).toEqual({
      updatedByName: 'Ben',
      updatedAt: '2026-11-10T06:30:00',
    });
    // The server kept tab B's state as History, so the local copy is not needed.
    expect(readMirror(mirrorKey(PROJECT, DOC))).toBeNull();

    rerender({ state: state('Tab B again'), isDirty: true });
    await tick(AUTOSAVE_DEBOUNCE_MS * 3);
    expect(saveDraft).toHaveBeenCalledTimes(1);
  });

  it('a new proposal: the first edit creates the record, later edits save its draft', async () => {
    const create = vi.fn(
      async (draft: QuotationFormState) => ({ id: 'new-doc', subject_title: draft.header.subject_title }) as QuotationDocument,
    );
    const onCreated = vi.fn();
    const { rerender, result } = setup({
      state: state(''),
      isDirty: false,
      documentId: null,
      rev: 0,
      create,
      onCreated,
    });
    rerender({ state: state('First word'), isDirty: true });
    await tick();
    expect(create).toHaveBeenCalledTimes(1);
    expect(create.mock.calls[0][0].header.subject_title).toBe('First word');
    expect(onCreated).toHaveBeenCalledWith({ id: 'new-doc', subject_title: 'First word' });
    expect(saveDraft).not.toHaveBeenCalled();
    expect(result.current.documentId).toBe('new-doc');

    rerender({ state: state('Second word'), isDirty: true });
    await tick();
    expect(saveDraft).toHaveBeenCalledTimes(1);
    expect(saveDraft.mock.calls[0][1]).toBe('new-doc');
    expect(saveDraft.mock.calls[0][3]).toBe(1);
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
    writeMirror(key, { baseRev: 0, doc: state('x'), at: 'now' });
    expect(readMirror(key)?.doc.header.subject_title).toBe('x');
    clearMirror(key);
    expect(readMirror(key)).toBeNull();

    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    const setSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(readMirror(key)).toBeNull();
    expect(() => writeMirror(key, { baseRev: 0, doc: state('x'), at: 'now' })).not.toThrow();
    spy.mockRestore();
    setSpy.mockRestore();
  });
});
