import { toast } from '@/lib/toast';

/**
 * Copy the supplier's read-only link, wherever it is offered from.
 *
 * Two places offer it - the Requests sent card's per-send button and the record toolbar's
 * gear (R5) - and they must not drift on what happens when the clipboard refuses, so the
 * refusal is handled here rather than twice.
 *
 * Returns whether anything was copied, and says nothing when it worked: the confirmation is
 * the tick the caller flashes on the control that was pressed, not a toast (S7-05).
 */
export async function copyPublicLink(url: string | null | undefined): Promise<boolean> {
  if (!url) return false;
  try {
    await navigator.clipboard.writeText(url);
    return true;
  } catch {
    toast.error('Could not copy the link. Copy it from the address bar instead.');
    return false;
  }
}
