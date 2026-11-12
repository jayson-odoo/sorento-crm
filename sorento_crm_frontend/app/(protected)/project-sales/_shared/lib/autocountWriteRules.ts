import {
  AUTOCOUNT_ALREADY_CANCELLED_TEXT,
  AUTOCOUNT_NOT_IN_AUTOCOUNT_TEXT,
  AUTOCOUNT_UNREACHABLE_TEXT,
  AUTOCOUNT_WAITING_TEXT,
} from '@/lib/autocountWriteWording';
import type { AutocountWriteCapabilities } from '../types/projectAutocountWrite.types';

/**
 * AC-QTSO-CRM: when each AutoCount write action may run, and the plain reason when it may not.
 * ONE place for the rules, read by the worksheet, the sales order detail page, the sales order
 * list and the amendment page, so the same order is greyed for the same reason everywhere.
 *
 * The server enforces all of it again; this only says why a button is grey.
 */
export interface ActionState {
  enabled: boolean;
  /** Why it is greyed; null when enabled. */
  reason: string | null;
}

type Caps = AutocountWriteCapabilities | undefined;

const hasBook = (caps: Caps): boolean => Boolean(caps?.book?.trim());

/** The capability step shared by every action: loading, unreachable, no book, then the op itself. */
function fromFeed(
  caps: Caps,
  loading: boolean,
  op: keyof NonNullable<AutocountWriteCapabilities['sales_orders']>,
): ActionState {
  const cap = caps?.sales_orders?.[op];
  if (loading) return { enabled: false, reason: 'Checking AutoCount…' };
  if (!cap) return { enabled: false, reason: AUTOCOUNT_UNREACHABLE_TEXT };
  if (!hasBook(caps)) return { enabled: false, reason: AUTOCOUNT_WAITING_TEXT };
  if (!cap.enabled) return { enabled: false, reason: cap.reason ?? AUTOCOUNT_WAITING_TEXT };
  return { enabled: true, reason: null };
}

export const CREATE_NOT_PUBLISHED_TEXT = 'Publish the order first';
export const CREATE_BLOCKED_TEXT = 'Clear the blocking findings first';
export const CREATE_ALREADY_TEXT = 'Already in AutoCount';

/**
 * Create in AutoCount for one sales order. `eligible` is the order's own state (published, can
 * export, not in AutoCount yet); the worksheet hides the button when it is false, the detail page
 * greys it with `reason`.
 */
export function createInAutocountState(input: {
  status: string;
  canExport: boolean;
  autocountDocNo?: string | null;
  inAutocount?: boolean;
  caps: Caps;
  capsLoading: boolean;
}): ActionState & { eligible: boolean } {
  const published = input.status === 'published' || input.status === 'amended';
  if (input.autocountDocNo || input.inAutocount) {
    return { eligible: false, enabled: false, reason: CREATE_ALREADY_TEXT };
  }
  if (!published) return { eligible: false, enabled: false, reason: CREATE_NOT_PUBLISHED_TEXT };
  if (!input.canExport) return { eligible: false, enabled: false, reason: CREATE_BLOCKED_TEXT };
  return { eligible: true, ...fromFeed(input.caps, input.capsLoading, 'create_doc') };
}

/** Cancel in AutoCount for one or several ticked orders (`inAutocount` means ALL are). */
export function cancelInAutocountState(input: {
  inAutocount: boolean;
  /** Any of them already cancelled. */
  cancelled: boolean;
  /** Any of them is in AutoCount (the book gate applies once one is). */
  anyInAutocount?: boolean;
  caps: Caps;
  capsLoading: boolean;
}): ActionState {
  if (!input.inAutocount) return { enabled: false, reason: AUTOCOUNT_NOT_IN_AUTOCOUNT_TEXT };
  if (input.cancelled) return { enabled: false, reason: AUTOCOUNT_ALREADY_CANCELLED_TEXT };
  return fromFeed(input.caps, input.capsLoading, 'cancel_doc');
}

/** Update in AutoCount (a published amendment's edits): edit_doc and the book. */
export function updateInAutocountState(input: { caps: Caps; capsLoading: boolean }): ActionState {
  return fromFeed(input.caps, input.capsLoading, 'edit_doc');
}
