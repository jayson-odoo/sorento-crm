import { toast } from 'sonner';

/**
 * Copy the supplier's read-only link, wherever it is offered from.
 *
 * Two places offer it - the Requests sent card's per-send button and the record toolbar's
 * gear (R5) - and they must not drift on what "copied" says or what happens when the
 * clipboard refuses, so the toast lives here rather than twice.
 *
 * Returns whether anything was copied, so the caller can flash its own confirmation.
 */
export async function copyPublicLink(url: string | null | undefined): Promise<boolean> {
  if (!url) return false;
  try {
    await navigator.clipboard.writeText(url);
    toast.success('Link copied');
    return true;
  } catch {
    toast.error('Could not copy the link. Copy it from the address bar instead.');
    return false;
  }
}
