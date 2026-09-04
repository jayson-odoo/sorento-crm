import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { usePendingThreadItems } from './usePendingThreadItems';

describe('usePendingThreadItems (M6-01)', () => {
  it('adds a text bubble with a pending receipt', () => {
    const { result } = renderHook(() => usePendingThreadItems());
    act(() => {
      result.current.addPending({ text: 'on my way' });
    });
    expect(result.current.pendingItems).toHaveLength(1);
    expect(result.current.pendingItems[0]).toMatchObject({
      traffic: 'outgoing',
      source: 'pending',
      message: { type: 'text', text: 'on my way' },
      status: [{ value: 'pending' }],
    });
  });

  it('adds one bubble per attachment, placeholder-labelled', () => {
    const { result } = renderHook(() => usePendingThreadItems());
    act(() => {
      result.current.addPending({ text: '', files: [{ name: 'photo.jpg' }] });
    });
    expect(result.current.pendingItems).toHaveLength(1);
    expect(result.current.pendingItems[0].message).toEqual({
      type: 'text',
      text: '[file] photo.jpg',
    });
  });

  it('a blank send with no files adds nothing', () => {
    const { result } = renderHook(() => usePendingThreadItems());
    act(() => {
      result.current.addPending({ text: '   ' });
    });
    expect(result.current.pendingItems).toEqual([]);
  });

  it('removePending takes down exactly the send that created it', () => {
    const { result } = renderHook(() => usePendingThreadItems());
    let first = '';
    let second = '';
    act(() => {
      first = result.current.addPending({ text: 'one' });
      second = result.current.addPending({ text: 'two' });
    });
    expect(result.current.pendingItems).toHaveLength(2);
    act(() => result.current.removePending(first));
    expect(result.current.pendingItems).toHaveLength(1);
    expect(result.current.pendingItems[0].pendingKey).toBe(second);
  });

  it('clearPending drops every bubble', () => {
    const { result } = renderHook(() => usePendingThreadItems());
    act(() => {
      result.current.addPending({ text: 'one' });
      result.current.addPending({ text: 'two' });
    });
    expect(result.current.pendingItems).toHaveLength(2);
    act(() => result.current.clearPending());
    expect(result.current.pendingItems).toEqual([]);
  });
});
