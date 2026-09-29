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
   * support at all (ours is the ">" text convention), so this is a READ-side field.
   */
  replyTo?: {
    /**
     * Respond's LIVE relay carries the quoted message's id under `id`, not
     * `messageId` - the outer envelope uses `messageId`, but the embedded
     * quote object is shaped differently (`{id, message, mId, sender}`, no
     * `messageId` key at all). `messageId` is kept for the local
     * `chat_histories` mirror, which reconstructs this shape itself and
     * still writes that key (`conversation_thread_service.py`'s
     * `_row_to_item`).
     */
    id?: number | string | null;
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

/** Quote line prefix of an outgoing reply-to (#1317, recovered from e91b225ce). */
export const QUOTE_LINE_PREFIX = '> ';

/** Longest quoted excerpt carried in an outgoing reply before it is elided. */
export const QUOTE_EXCERPT_MAX_CHARS = 160;

/** The message a staff reply answers, as the composer carries it. */
export type ReplyTarget = {
  /** Respond message id of the quoted message, for the audit trail only. */
  messageId: string | null;
  /** What gets quoted. Never empty. */
  excerpt: string;
  /** Who wrote the quoted message, as the preview names them. */
  senderLabel: string;
};

/**
 * Build the outgoing text for a "reply to this message" send.
 *
 * Respond.io's send API has NO reply-to/context parameter, so a reply is
 * emulated: the quoted excerpt is carried as a ">"-prefixed line above the body,
 * which WhatsApp renders as quoted text and which `splitQuotedPrefix` turns back
 * into a quote block in our own chat list. Shipped 12 Aug, dropped 16 Aug
 * (e313ac690), restored as-is for #1317.
 */
export function buildQuotedReplyText(quotedText: string, body: string): string {
  const excerpt = (quotedText ?? '').replace(/\s+/g, ' ').trim();
  if (!excerpt) return body;
  const clipped =
    excerpt.length > QUOTE_EXCERPT_MAX_CHARS
      ? `${excerpt.slice(0, QUOTE_EXCERPT_MAX_CHARS).trimEnd()}…`
      : excerpt;
  return `${QUOTE_LINE_PREFIX}${clipped}\n${body}`;
}

/**
 * Split a message body into its leading ">"-quoted excerpt (if any) and the
 * reply itself.
 *
 * ONLY valid on OUTGOING text: the ">" prefix is a convention WE write in
 * `buildQuotedReplyText`, so it is only ours to read back. Render inbound
 * traffic through `splitMessageQuote` (or verbatim) - a contact may legitimately
 * start their own message with ">" and those lines are their message.
 */
export function splitQuotedPrefix(text: string): { quoted: string | null; body: string } {
  const raw = text ?? '';
  if (!raw.startsWith(QUOTE_LINE_PREFIX.trimEnd())) return { quoted: null, body: raw };
  const lines = raw.split('\n');
  const quoted: string[] = [];
  let i = 0;
  for (; i < lines.length; i += 1) {
    const line = lines[i];
    if (!line.startsWith('>')) break;
    quoted.push(line.replace(/^>\s?/, ''));
  }
  if (quoted.length === 0) return { quoted: null, body: raw };
  return { quoted: quoted.join('\n').trim(), body: lines.slice(i).join('\n').replace(/^\n+/, '') };
}

/**
 * The quote + body to render for ONE message, direction aware (7b18bbb72):
 * outgoing is ours, so a leading ">" block is the reply-to emulation; inbound
 * is the contact's own words and is returned verbatim.
 */
export function splitMessageQuote(
  item: RespondMessageRenderable,
): { quoted: string | null; body: string } {
  const raw = getMessageBodyText(item);
  if (item.traffic !== 'outgoing') return { quoted: null, body: raw };
  return splitQuotedPrefix(raw);
}

/**
 * The text a Reply on this message quotes: what its bubble shows (an earlier
 * quote line of ours is not re-quoted), else the attachment placeholder, else
 * the bare type. Never empty.
 */
export function quoteExcerptOf(item: RespondMessageRenderable): string {
  const body = splitMessageQuote(item).body.replace(/\s+/g, ' ').trim();
  if (body) return body;
  const attachment = describeMessageAttachments(item)[0];
  if (attachment) {
    return attachment.fileName ? `[${attachment.kind}] ${attachment.fileName}` : `[${attachment.kind}]`;
  }
  const type = String(item.message?.type ?? '').trim();
  return type ? `[${type}]` : '[message]';
}

/**
 * The message an outgoing ">" quote was cut from, among the ones loaded before
 * it. The wire text carries no id, so the match is on the text itself: the
 * newest earlier message whose quotable text starts with the excerpt (minus the
 * ellipsis `buildQuotedReplyText` adds when it clips).
 */
export function findQuotedOriginal(
  excerpt: string,
  earlier: RespondMessageRenderable[],
): RespondMessageRenderable | undefined {
  const needle = excerpt.replace(/\s+/g, ' ').trim().replace(/…$/, '').trimEnd();
  if (!needle) return undefined;
  for (let i = earlier.length - 1; i >= 0; i -= 1) {
    if (quoteExcerptOf(earlier[i]).startsWith(needle)) return earlier[i];
  }
  return undefined;
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
 * rewrite). Our own outgoing quote is the ">" text convention instead
 * (`splitMessageQuote`), since Respond's send API takes no reply-to.
 *
 * A quoted media message has no text, so the excerpt falls back to a typed
 * placeholder ("[image]") rather than rendering an empty block; a quote we hold
 * no excerpt for at all reads "Quoted message", because "this replies to
 * something" is still true and useful.
 */
export function describeQuotedContext(item: RespondMessageRenderable): QuotedContext | null {
  const reply = item.replyTo;
  if (!reply || typeof reply !== 'object') return null;

  // Fix round 3: the LIVE Respond relay's `replyTo` carries the quoted
  // message's id as `id`, never `messageId` - only the local chat_histories
  // mirror's reconstructed shape (`_row_to_item`) still uses `messageId`.
  // Reading `id` first covers the real wire shape; the fallback keeps the
  // older stored shape working.
  const rawId = reply.id ?? reply.messageId;
  const messageId =
    rawId === null || rawId === undefined || String(rawId).trim() === ''
      ? null
      : String(rawId).trim();

  // The quoted message is read the way its own bubble is: a quick_reply keeps
  // its prose under `title` and its options under `replies`, so reading `text`
  // alone showed a literal "[quick_reply]" for every option prompt quoted.
  const quotedItem = { message: reply.message ?? {} } as RespondMessageRenderable;
  const quotedMessage = quotedItem.message ?? {};
  const text = getMessageBodyText(quotedItem).replace(/\s+/g, ' ').trim();
  const kind = (quotedMessage.type ?? '').trim();
  let excerpt = text;
  if (!excerpt) excerpt = extractSelectionOptions(quotedItem).join(' | ');
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
