/**
 * The WhatsApp message gestures every conversation surface carries (#1317),
 * driven the same way in every surface's spec so none of them can drift:
 * right click (desktop menu), long press is Radix's own and is pinned once in
 * RespondChatList.replyto.test.tsx, and a touch swipe to the right.
 */
import { fireEvent, screen } from '@testing-library/react';

/** The bubble wrapper the shared `MessageBubbleActions` renders around `text`. */
export function bubbleOf(text: string): HTMLElement {
  const el = screen.getByText(text).closest('[data-testid="message-bubble"]');
  if (!el) throw new Error(`no message bubble around "${text}"`);
  return el as HTMLElement;
}

/** Right click the bubble and return the menu's item labels, in order. */
export async function openBubbleMenu(text: string): Promise<string[]> {
  fireEvent.contextMenu(bubbleOf(text), { clientX: 20, clientY: 20 });
  const items = await screen.findAllByRole('menuitem');
  return items.map((i) => i.textContent?.trim() ?? '');
}

function touch(el: HTMLElement, type: 'pointerDown' | 'pointerMove' | 'pointerUp', x: number) {
  fireEvent[type](el, { pointerType: 'touch', pointerId: 7, clientX: x, clientY: 100, button: 0 });
}

/** A finger swipe right of `distance` px on the bubble, then release. */
export function swipeRight(text: string, distance = 70) {
  const bubble = bubbleOf(text);
  touch(bubble, 'pointerDown', 10);
  touch(bubble, 'pointerMove', 30);
  touch(bubble, 'pointerMove', 10 + distance);
  touch(bubble, 'pointerUp', 10 + distance);
}
