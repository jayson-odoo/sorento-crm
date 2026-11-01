'use client';

import { createContext, useContext, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

/**
 * The record card (identity, pager, gear, CTA) of a form detail page, lifted out of the
 * Details tab body to sit ABOVE the tab strip, on every tab (NAV-KEEP-TAB).
 *
 * The form shell (`FormDetailWithSLATabs`) owns the slot element; the detail component
 * renders its header inside `<RecordCardSlot>` and keeps the rest where it is. Without that,
 * the pager lived in the Details panel and vanished on Fulfilment DOs, Comments, SLA ... so
 * prev/next could not be pressed from any tab but Details.
 *
 * Outside a shell (a limited user's portal view, a unit test) the card renders in place.
 * Inside one, it renders nothing until the slot element exists (one commit).
 */
export const RecordCardSlotContext = createContext<
  HTMLElement | null | undefined
>(undefined);

export function RecordCardSlot({ children }: { children: ReactNode }) {
  const slot = useContext(RecordCardSlotContext);
  if (slot === undefined) return <>{children}</>;
  if (slot === null) return null;
  return createPortal(children, slot);
}
