'use client';

import { useCallback, useRef, useState } from 'react';
import type React from 'react';

/** How far a bubble must travel before letting go starts a reply (#1317, AC-RT-8). */
export const SWIPE_REPLY_THRESHOLD_PX = 56;
/** The furthest a bubble follows the finger (AC-RT-7). */
export const SWIPE_REPLY_MAX_PX = 80;
/**
 * Travel before the gesture decides whether it is a swipe or a scroll. Below
 * it nothing moves, so a thumb resting on a bubble while the thread scrolls
 * never nudges it sideways (AC-RT-10).
 */
const DIRECTION_LOCK_SLOP_PX = 10;

/**
 * WhatsApp's swipe-right-to-reply, touch only: the bubble follows the finger
 * (capped), and letting go past the threshold replies while letting go early
 * snaps back. A mouse drag is text selection, never a swipe.
 *
 * The caller writes `offset` into the bubble's transform and puts
 * `touch-action: pan-y` on it, so the browser keeps vertical scrolling and
 * hands the horizontal travel to these handlers.
 */
export function useSwipeToReply({ enabled, onReply }: { enabled: boolean; onReply: () => void }) {
  const [offset, setOffset] = useState(0);
  const [dragging, setDragging] = useState(false);
  const gesture = useRef<{ id: number; x: number; y: number; lock: 'x' | 'y' | null } | null>(null);
  // The live offset, read on release: state from the last move may not have
  // re-rendered yet when the pointerup arrives in the same frame.
  const offsetRef = useRef(0);

  const settle = useCallback(() => {
    gesture.current = null;
    offsetRef.current = 0;
    setOffset(0);
    setDragging(false);
  }, []);

  const onPointerDown = useCallback(
    (event: React.PointerEvent<HTMLElement>) => {
      if (!enabled || event.pointerType !== 'touch') return;
      gesture.current = { id: event.pointerId, x: event.clientX, y: event.clientY, lock: null };
    },
    [enabled],
  );

  const onPointerMove = useCallback((event: React.PointerEvent<HTMLElement>) => {
    const g = gesture.current;
    if (!g || event.pointerId !== g.id) return;
    const dx = event.clientX - g.x;
    const dy = event.clientY - g.y;
    if (g.lock === null) {
      if (Math.max(Math.abs(dx), Math.abs(dy)) < DIRECTION_LOCK_SLOP_PX) return;
      g.lock = dx > 0 && Math.abs(dx) > Math.abs(dy) ? 'x' : 'y';
    }
    if (g.lock !== 'x') return;
    const next = Math.min(Math.max(dx, 0), SWIPE_REPLY_MAX_PX);
    // A haptic tick the moment the reply is armed, as WhatsApp does.
    if (next >= SWIPE_REPLY_THRESHOLD_PX && offsetRef.current < SWIPE_REPLY_THRESHOLD_PX) {
      navigator.vibrate?.(10);
    }
    offsetRef.current = next;
    setOffset(next);
    setDragging(true);
  }, []);

  const onPointerUp = useCallback(
    (event: React.PointerEvent<HTMLElement>) => {
      const g = gesture.current;
      if (!g || event.pointerId !== g.id) return;
      const armed = g.lock === 'x' && offsetRef.current >= SWIPE_REPLY_THRESHOLD_PX;
      settle();
      if (armed) onReply();
    },
    [onReply, settle],
  );

  const onPointerCancel = useCallback(
    (event: React.PointerEvent<HTMLElement>) => {
      if (gesture.current && event.pointerId === gesture.current.id) settle();
    },
    [settle],
  );

  return {
    offset,
    dragging,
    /** 0..1 toward the threshold; drives the reply icon's fade-in. */
    progress: Math.min(offset / SWIPE_REPLY_THRESHOLD_PX, 1),
    handlers: { onPointerDown, onPointerMove, onPointerUp, onPointerCancel },
  };
}
