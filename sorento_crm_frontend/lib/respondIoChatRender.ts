/**
 * Helpers for rendering Respond.io messages in a WhatsApp-style chat list:
 * date grouping, read-receipt tier, selection-option extraction, typed
 * attachment placeholders, and the quoted-reply text convention.
 */

export type RespondStatusEntry = { value?: string; timestamp?: number; message?: string };

export type RespondMessageRenderable = {
  messageId?: number;
  traffic?: string;
  message?: {
    type?: string;
    text?: string;
    /**
     * The body of a `quick_reply` message. Respond.io puts the prose under
     * `title` there and leaves `text` unset, so a reader of `text` alone shows
     * an empty bubble for every option prompt the bot has ever sent.
     */
    title?: string;
    messageTag?: string;
    // Selection-style payloads observed in Respond.io v2 list/quick-reply messages.
    /** What a `quick_reply` actually carries: bare option strings. */
    replies?: Array<string | { title?: string; label?: string; text?: string }>;
    /** WhatsApp template payload: the body text is mirrored onto `text`, the buttons are not. */
    template?: {
      name?: string;
      components?: Array<{
        type?: string;
        text?: string;
        buttons?: Array<{ type?: string; text?: string; url?: string }>;
      }>;
    };
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
  /** `name` is resolved by the backend from `sender.userId` - Respond sends only the id. */
  sender?: { source?: string; userId?: number | string | null; name?: string | null };
  /**
   * Inbound quote context (UAC AC-L6). Respond's `message.received` webhook and
   * its message objects carry `replyTo` when the contact quoted an earlier
   * message; the local `chat_histories` lane reconstructs the same shape from
   * `reply_to_message_id` / `reply_to_message`. Outbound quoting has no API
   * support at all, so this is inbound-only: a READ-side field.
   */
  replyTo?: {
    messageId?: number | string | null;
    traffic?: string;
    message?: { type?: string; text?: string } & Record<string, unknown>;
  } & Record<string, unknown> | null;
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

/**
 * The prose of a message, wherever this message type happens to keep it.
 *
 * `text` for a plain message and for a WhatsApp template (Respond mirrors the
 * template body onto it), but a `quick_reply` carries its body under `title`
 * and no `text` at all - which is why every option prompt used to render as
 * "(no text)" with its question invisible.
 */
export function getMessageBodyText(item: RespondMessageRenderable): string {
  const m = item.message;
  if (!m) return '';
  const text = (m.text ?? '').trim();
  if (text) return m.text ?? '';
  return m.title ?? '';
}

/** A button a WhatsApp template offered the contact. */
export interface TemplateButton {
  text: string;
  /** Absolute URL for a `url` button; absent for a quick-reply style button. */
  url?: string;
}

/**
 * The buttons a WhatsApp template put on the contact's handset.
 *
 * The template body is mirrored onto `message.text` and renders already, but
 * the button component is not: staff reading the thread could not see that the
 * contact had been handed a "View" link to their complaint, let alone follow
 * it. Read straight off the template component so what the thread shows is what
 * the handset showed.
 */
export function extractTemplateButtons(item: RespondMessageRenderable): TemplateButton[] {
  const components = item.message?.template?.components;
  if (!Array.isArray(components)) return [];
  const out: TemplateButton[] = [];
  for (const component of components) {
    if (!Array.isArray(component?.buttons)) continue;
    for (const button of component.buttons) {
      const text = (button?.text ?? '').toString().trim();
      if (!text) continue;
      const url = (button?.url ?? '').toString().trim();
      out.push(url ? { text, url } : { text });
    }
  }
  return out;
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
  for (const arr of [m.replies, m.quickReplies, m.options, m.buttons]) {
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

/** Media kinds Respond.io carries on a message, plus the fallbacks we render defensively. */
export type MessageAttachmentKind =
  | 'image'
  | 'video'
  | 'audio'
  | 'file'
  | 'sticker'
  | 'location'
  | 'unknown';

export interface MessageAttachmentDescriptor {
  kind: MessageAttachmentKind;
  /** Typed placeholder label, e.g. "Photo", "Document". Never empty. */
  label: string;
  url?: string;
  fileName?: string;
}

const ATTACHMENT_LABELS: Record<MessageAttachmentKind, string> = {
  image: 'Photo',
  video: 'Video',
  audio: 'Audio message',
  file: 'Document',
  sticker: 'Sticker',
  location: 'Location',
  unknown: 'Attachment',
};

function normalizeAttachmentKind(raw: unknown): MessageAttachmentKind {
  const t = String(raw ?? '').toLowerCase();
  if (t === 'image' || t === 'photo') return 'image';
  if (t === 'video') return 'video';
  if (t === 'audio' || t === 'voice') return 'audio';
  if (t === 'file' || t === 'document') return 'file';
  if (t === 'sticker') return 'sticker';
  if (t === 'location') return 'location';
  return 'unknown';
}

/**
 * Filename carried by an attachment URL's last path segment.
 *
 * Respond.io's message payload has no fileName field on most shapes, so the URL
 * is the only name channel we get - the same segment WhatsApp itself names the
 * delivered document from (AC-D5, which is why our own uploads put the uuid in
 * its own path segment and keep the clean filename last). Query string and
 * fragment are dropped, percent-escapes decoded; anything unusable yields
 * `undefined` so the caller falls back to the typed label.
 *
 * Respond-hosted media is named after a uuid or a content hash. That is not a
 * filename to anybody, and rendering it would put a UUID in the UI, so a stem
 * that is nothing but one is rejected in favour of "Photo" / "Document".
 */
const UUID_STEM = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
/** A hex run this long is a hash, never something a person typed. */
const HEX_HASH_STEM = /^[0-9a-f]{16,}$/i;

export function fileNameFromAttachmentUrl(url?: string): string | undefined {
  const raw = (url ?? '').trim();
  if (!raw) return undefined;
  const last = raw.split(/[?#]/)[0].split('/').pop() ?? '';
  if (!last) return undefined;
  let decoded = last;
  try {
    decoded = decodeURIComponent(last);
  } catch {
    // Malformed escape - keep the raw segment rather than losing the name.
  }
  const name = decoded.trim();
  if (!name) return undefined;
  const dot = name.lastIndexOf('.');
  const stem = dot > 0 ? name.slice(0, dot) : name;
  if (UUID_STEM.test(stem) || HEX_HASH_STEM.test(stem)) return undefined;
  return name;
}

function toDescriptor(raw: unknown, fallbackKind?: unknown): MessageAttachmentDescriptor | null {
  if (typeof raw === 'string') {
    const url = raw.trim();
    if (!url) return null;
    const kind = normalizeAttachmentKind(fallbackKind);
    return {
      kind,
      label: ATTACHMENT_LABELS[kind],
      url,
      fileName: fileNameFromAttachmentUrl(url),
    };
  }
  if (!raw || typeof raw !== 'object') return null;
  const o = raw as Record<string, unknown>;
  const kind = normalizeAttachmentKind(o.type ?? fallbackKind);
  const url =
    (typeof o.url === 'string' && o.url) ||
    (typeof o.link === 'string' && o.link) ||
    undefined;
  const fileName =
    (typeof o.fileName === 'string' && o.fileName) ||
    (typeof o.filename === 'string' && o.filename) ||
    (typeof o.name === 'string' && o.name) ||
    fileNameFromAttachmentUrl(url) ||
    undefined;
  if (!url && !fileName && kind === 'unknown') return null;
  return { kind, label: ATTACHMENT_LABELS[kind], url, fileName };
}

/**
 * Typed descriptors for whatever non-text payload a message carries (image,
 * video, audio, file, sticker, location, or an unrecognised type). Defensive
 * across the shapes Respond.io v2 emits: `message.attachments[]`,
 * `message.attachment` (object or array), or a bare `message.url` on a typed
 * message. An unknown type still yields a placeholder, so the chat list never
 * renders a blank bubble and never crashes on a shape we have not seen.
 */
export function describeMessageAttachments(
  item: RespondMessageRenderable,
): MessageAttachmentDescriptor[] {
  const m = item.message as Record<string, unknown> | undefined;
  if (!m) return [];
  const out: MessageAttachmentDescriptor[] = [];
  const push = (raw: unknown) => {
    const d = toDescriptor(raw, m.type);
    if (d) out.push(d);
  };
  if (Array.isArray(m.attachments)) m.attachments.forEach(push);
  if (Array.isArray(m.attachment)) m.attachment.forEach(push);
  else if (m.attachment) push(m.attachment);
  if (out.length === 0) {
    const kind = normalizeAttachmentKind(m.type);
    if (kind !== 'unknown') {
      push({ type: m.type, url: m.url ?? m.link, fileName: m.fileName ?? m.filename });
    }
  }
  return out;
}

/** The "replying to" block above a bubble, when the message quotes an earlier one. */
export type QuotedContext = {
  /** Respond message id of the quoted message, as a string. Null when absent. */
  messageId: string | null;
  /** What to show in the block. Never empty - falls back to a typed placeholder. */
  excerpt: string;
  /** 'contact' | 'agent' when the quoted direction is known, else null. */
  sender: 'contact' | 'agent' | null;
};

/** Longest quoted excerpt rendered in an inbound "replying to" block. */
export const QUOTED_CONTEXT_MAX_CHARS = 180;

/**
 * The quoted context carried BY the message itself (UAC AC-L6).
 *
 * Inbound only. It reads Respond's structured `replyTo`, which is how a
 * contact's quote-reply arrives - there is no ">" in it to parse, and parsing
 * one would be wrong anyway (the contact's own words are never ours to
 * rewrite). There is no outgoing counterpart: Respond's send API takes no
 * reply-to, and the ">"-prefix emulation we once wrote was removed rather than
 * left on screen looking like a real quote.
 *
 * A quoted media message has no text, so the excerpt falls back to a typed
 * placeholder ("[image]") rather than rendering an empty block; a quote we hold
 * no excerpt for at all reads "Quoted message", because "this replies to
 * something" is still true and useful.
 */
export function describeQuotedContext(item: RespondMessageRenderable): QuotedContext | null {
  const reply = item.replyTo;
  if (!reply || typeof reply !== 'object') return null;

  const rawId = reply.messageId;
  const messageId =
    rawId === null || rawId === undefined || String(rawId).trim() === ''
      ? null
      : String(rawId).trim();

  const quotedMessage = (reply.message ?? {}) as { type?: string; text?: string };
  const text = (quotedMessage.text ?? '').replace(/\s+/g, ' ').trim();
  const kind = (quotedMessage.type ?? '').trim();
  let excerpt = text;
  if (!excerpt) excerpt = kind && kind !== 'text' ? `[${kind}]` : '';
  if (!excerpt) excerpt = 'Quoted message';
  if (excerpt.length > QUOTED_CONTEXT_MAX_CHARS) {
    excerpt = `${excerpt.slice(0, QUOTED_CONTEXT_MAX_CHARS).trimEnd()}…`;
  }

  const traffic = (reply.traffic ?? '').toString().trim().toLowerCase();
  const sender =
    traffic === 'incoming' ? 'contact' : traffic === 'outgoing' ? 'agent' : null;

  // Nothing identifiable at all (no id, no text, no type) is not a quote.
  if (!messageId && !text && !kind) return null;

  return { messageId, excerpt, sender };
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
