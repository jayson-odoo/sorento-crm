/**
 * Helpers for rendering Respond.io messages in a WhatsApp-style chat list:
 * date grouping, read-receipt tier, selection-option extraction.
 */

export type RespondStatusEntry = { value?: string; timestamp?: number; message?: string };

export type RespondMessageRenderable = {
  messageId?: number;
  traffic?: string;
  message?: {
    type?: string;
    text?: string;
    messageTag?: string;
    // Selection-style payloads observed in Respond.io v2 list/quick-reply messages.
    quickReplies?: Array<string | { title?: string; label?: string; text?: string }>;
    options?: Array<string | { title?: string; label?: string; text?: string }>;
    buttons?: Array<string | { title?: string; label?: string; text?: string }>;
    list?: {
      title?: string;
      sections?: Array<{ rows?: Array<{ title?: string }> }>;
      rows?: Array<{ title?: string }>;
    };
  } & Record<string, unknown>;
  status?: RespondStatusEntry[];
  sender?: { source?: string };
};

/** WhatsApp-like read receipt tiers derived from Respond.io status[] entries. */
export type ReceiptTier = 'sending' | 'sent' | 'delivered' | 'read' | 'failed' | 'none';

export function getReceiptTier(item: RespondMessageRenderable): ReceiptTier {
  if (item.traffic !== 'outgoing') return 'none';
  const arr = item.status ?? [];
  if (arr.some((s) => (s.value ?? '').toLowerCase() === 'failed')) return 'failed';
  if (arr.some((s) => (s.value ?? '').toLowerCase() === 'read')) return 'read';
  if (arr.some((s) => (s.value ?? '').toLowerCase() === 'delivered')) return 'delivered';
  if (arr.some((s) => (s.value ?? '').toLowerCase() === 'sent')) return 'sent';
  if (arr.some((s) => (s.value ?? '').toLowerCase() === 'pending')) return 'sending';
  return 'sent';
}

/** Extract selection options from Respond.io interactive payloads (defensive across shapes). */
export function extractSelectionOptions(item: RespondMessageRenderable): string[] {
  const m = item.message;
  if (!m) return [];
  const pickLabel = (v: unknown): string => {
    if (typeof v === 'string') return v;
    if (v && typeof v === 'object') {
      const o = v as Record<string, unknown>;
      return (
        (typeof o.title === 'string' && o.title) ||
        (typeof o.label === 'string' && o.label) ||
        (typeof o.text === 'string' && o.text) ||
        ''
      );
    }
    return '';
  };
  const out: string[] = [];
  for (const arr of [m.quickReplies, m.options, m.buttons]) {
    if (Array.isArray(arr)) {
      for (const v of arr) {
        const s = pickLabel(v).trim();
        if (s) out.push(s);
      }
    }
  }
  if (m.list) {
    const rows: Array<{ title?: string }> = [];
    if (Array.isArray(m.list.rows)) rows.push(...m.list.rows);
    if (Array.isArray(m.list.sections)) {
      for (const sec of m.list.sections) {
        if (Array.isArray(sec.rows)) rows.push(...sec.rows);
      }
    }
    for (const r of rows) {
      const s = (r?.title ?? '').toString().trim();
      if (s) out.push(s);
    }
  }
  return out;
}

/** Group messages by local date stamp (YYYY-MM-DD in browser tz) for date dividers. */
export function dateKeyFromMs(ms: number): string {
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return '';
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/** Pretty date label for the WhatsApp-style sticky pill: Today, Yesterday, or "Mon 2 Feb 2026". */
export function formatDatePillLabel(ms: number): string {
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return '';
  const today = new Date();
  const yest = new Date();
  yest.setDate(today.getDate() - 1);
  const sameDay = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  if (sameDay(d, today)) return 'Today';
  if (sameDay(d, yest)) return 'Yesterday';
  return d.toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: d.getFullYear() === today.getFullYear() ? undefined : 'numeric',
  });
}

/** Short HH:MM time inside each bubble (12h with am/pm to match WhatsApp). */
export function formatBubbleTime(ms: number): string {
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit', hour12: true });
}
