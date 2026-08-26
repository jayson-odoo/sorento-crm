'use client';

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowDownToLine,
  Check,
  CheckCheck,
  AlertCircle,
  Clock,
  CornerUpLeft,
  ExternalLink,
  FileText,
  Headphones,
  Image as ImageIcon,
  Loader2,
  MapPin,
  Paperclip,
  Search,
  Smile,
  StickyNote,
  Video,
} from 'lucide-react';
import {
  dateKeyFromMs,
  describeMessageAttachments,
  extractSelectionOptions,
  formatBubbleTime,
  formatDatePillLabel,
  describeQuotedContext,
  extractTemplateButtons,
  getMessageBodyText,
  getReceiptTier,
  type MessageAttachmentDescriptor,
  type QuotedContext,
  type RespondMessageRenderable,
} from '@/lib/respondIoChatRender';
import { getRespondMessageDisplayTimeMs, getRespondMessageSortTimeMs } from '@/lib/respondIoMessage';
import {
  getNormalizedRespondSource,
  getOutgoingSenderLabel,
  getRespondSenderName,
} from '@/lib/respondIoOutgoingMessage';
import { parseWhatsAppText, stripWhatsAppMarkup } from '@/lib/whatsappText';
import AttachmentPreviewModal, {
  type AttachmentPreviewItem,
} from '@/components/common/AttachmentPreviewModal';
import ConversationSearchBar from '@/components/common/conversation/ConversationSearchBar';
import type { ConversationSearchController } from '@/components/common/conversation/useConversationThread';
import { splitHighlightSegments } from '@/lib/textHighlight';
import { parseDateTimeAsUTC } from '@/lib/helpers';

/** Distance from the top that starts the next older page (AC-L7). */
const LOAD_OLDER_THRESHOLD_PX = 80;
/** Distance from the bottom that pages a detached window forward. */
const LOAD_NEWER_THRESHOLD_PX = 80;
/**
 * How long our OWN smooth scroll is allowed to keep emitting scroll events
 * before they count as the reader's. Opening on the enquiry bubble scrolls the
 * container past the top, and every frame of that animation used to read as
 * "the reader reached the top" and fetched a page nobody asked for.
 */
const PROGRAMMATIC_SCROLL_SETTLE_MS = 400;
/** How close to the bottom still counts as "reading the live tail". */
const PIN_TO_BOTTOM_SLACK_PX = 120;
/**
 * How far up the reader has to be before the scroll-to-latest button appears:
 * roughly one viewport of the thread itself, which is WhatsApp's behaviour. A
 * fixed pixel figure would pop the button on a short panel and hide it on a
 * tall one, so it is measured against the container's own height.
 */
const SCROLLED_UP_SHOW_JUMP_RATIO = 1;

/**
 * An internal note rendered inline in the thread (UAC AC-L1). It is drawer-side
 * data merged at RENDER time - a comment is never written into `chat_histories`
 * and is never a message.
 */
export interface ConversationCommentRenderable {
  id: string;
  body: string;
  author_name: string | null;
  /** Naive UTC, as the backend serializes every datetime. */
  created_at: string;
  source?: 'crm' | 'respond';
  /**
   * Who the note tags. Respond draws its mentions as a "@Name" line above the
   * body, and the CRM's own body does NOT carry them (they live in
   * `mentioned_user_ids`), so without this row a mirrored note loses its
   * addressee on screen.
   */
  mentioned_names?: string[];
}

interface RespondChatListProps {
  items: RespondMessageRenderable[];
  contactName?: string | null;
  contactPhone?: string | null;
  emptyHint?: string;
  /** Caps message-list scroll height; chat header sits above. */
  maxHeightClass?: string;
  /**
   * If set, the bubble whose `messageId` matches gets a highlight ring + a
   * "Ticket based on this message" badge, and the list scrolls to it on mount
   * instead of to the latest message. String/number both accepted because the
   * Respond.io message id is numeric on the wire but ticket.source_message_id
   * is stored as text.
   */
  highlightMessageId?: string | number | null;
  /** Label shown above the highlighted bubble. */
  highlightLabel?: string;
  /**
   * Scroll-back (AC-L7). Supplied together: reaching the top of the scroll
   * container calls `onLoadOlder`, and the prepended page is scroll-anchored so
   * the reader keeps their place. Surfaces that pass none of these behave
   * exactly as before (one page, no top spinner, no start marker).
   */
  onLoadOlder?: () => void;
  hasMoreOlder?: boolean;
  isLoadingOlder?: boolean;
  /** Renders the "beginning of the conversation" marker once nothing is older. */
  atConversationStart?: boolean;
  /**
   * Detached window (the reader jumped to a search match in the past). It shows
   * a "Jump to latest" pill - with the count of live messages the window is
   * hiding - and pages forward when the reader reaches the bottom, so there is
   * always a visible way back to the live conversation.
   */
  isDetached?: boolean;
  onJumpToLatest?: () => void;
  newerUnseenCount?: number;
  onLoadNewer?: () => void;
  hasMoreNewer?: boolean;
  isLoadingNewer?: boolean;
  /**
   * In-thread search (AC-L8). Passing a controller adds the search icon to the
   * chat header and the search bar under it; the active match gets a ring and
   * is scrolled into view, and `highlightTerm` is `<mark>`ed inside bubbles.
   */
  searchController?: ConversationSearchController;
  highlightTerm?: string;
  /**
   * Internal notes to interleave with the messages, chronologically (AC-L1).
   * Surfaces that pass none render exactly as before.
   */
  comments?: ConversationCommentRenderable[];
  /**
   * Viewer-scoped byte loader for chat media (AC-N4). Chat attachments live on
   * hosts that send no CORS headers (R2 CDN, CloudFront, Respond media), so a
   * spreadsheet/csv cannot be read from the browser and the preview surface used
   * to dead-end on "No source available to load this file". Passing this routes
   * the Excel slide AND the Download button through the backend media proxy
   * (ticket-keyed in the drawer, contact-keyed in the Conversations inbox);
   * images/video/pdf keep their direct CDN url either way.
   *
   * A `Response` rather than the bytes: it is what `AttachmentPreviewModal`
   * consumes and what `apiFetch` already hands back, so nothing has to
   * re-wrap a blob on the way through.
   *
   * Surfaces that pass nothing (portal thread, complaint / SI / PR panels)
   * behave exactly as before.
   */
  mediaProxy?: (url: string) => Promise<Response>;
  /**
   * Caller-driven scroll target (AC-N6): the message to scroll to and flash.
   * `focusNonce` is what actually triggers it, so asking for the SAME message
   * twice scrolls twice. The pair comes straight from `useConversationThread`
   * (`focusMessageId` / `focusNonce`), which loads the surrounding page first
   * when the target is outside the window - this component only ever scrolls to
   * a bubble that is mounted, and waits for it if it is not there yet.
   */
  focusMessageId?: string | null;
  focusNonce?: number;
}

/** Message text with the searched term marked. Escaping lives in the helper. */
function HighlightedText({ text, term }: { text: string; term: string }) {
  if (!term.trim()) return <>{text}</>;
  return (
    <>
      {splitHighlightSegments(text, term).map((segment, i) =>
        segment.match ? (
          <mark key={i} className="rounded-sm bg-amber-300 px-0.5 text-zinc-900">
            {segment.text}
          </mark>
        ) : (
          <span key={i}>{segment.text}</span>
        ),
      )}
    </>
  );
}

/**
 * A message body, rendered the way the handset rendered it: WhatsApp markup
 * applied, bare URLs clickable, and the search term still highlighted inside
 * whatever style the segment ended up with.
 *
 * The two passes compose in this order on purpose - markup first, highlight
 * second - because a search term can land anywhere inside a styled run, and
 * splitting for the mark before parsing the markup would cut a `*bold*` pair in
 * half and leave the asterisks on screen.
 */
function FormattedMessageText({ text, term }: { text: string; term: string }) {
  const segments = parseWhatsAppText(text);
  return (
    <>
      {segments.map((segment, i) => {
        const marked = <HighlightedText text={segment.text} term={term} />;

        if (segment.code) {
          return (
            <code
              key={i}
              className="block whitespace-pre-wrap rounded bg-black/5 px-1.5 py-1 font-mono text-[13px] dark:bg-white/10"
            >
              {marked}
            </code>
          );
        }

        let node: React.ReactNode = marked;
        if (segment.strike) node = <s>{node}</s>;
        if (segment.italic) node = <em>{node}</em>;
        if (segment.bold) node = <strong className="font-semibold">{node}</strong>;

        if (segment.href) {
          return (
            <a
              key={i}
              href={segment.href}
              target="_blank"
              rel="noopener noreferrer"
              // Stops the click from also selecting/scrolling the bubble it sits in.
              onClick={(event) => event.stopPropagation()}
              className="underline underline-offset-2 hover:opacity-80"
            >
              {node}
            </a>
          );
        }
        return <span key={i}>{node}</span>;
      })}
    </>
  );
}

/**
 * The buttons a WhatsApp template put on the contact's handset. A `url` button
 * is a real link here so staff can open the same page the contact was sent;
 * anything else is a label, because there is nothing for us to press.
 */
function TemplateButtons({ buttons }: { buttons: ReturnType<typeof extractTemplateButtons> }) {
  if (buttons.length === 0) return null;
  return (
    <div
      data-testid="template-buttons"
      className="mt-2 flex flex-col divide-y divide-zinc-200 overflow-hidden rounded border border-zinc-200 bg-white/70 dark:divide-zinc-700 dark:border-zinc-700 dark:bg-zinc-900/40"
    >
      {buttons.map((button, i) =>
        button.url ? (
          <a
            key={i}
            href={button.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center gap-1 px-2.5 py-1.5 text-xs font-medium text-sky-700 hover:bg-black/5 dark:text-sky-300 dark:hover:bg-white/5"
          >
            <ExternalLink className="size-3" />
            {button.text}
          </a>
        ) : (
          <div key={i} className="px-2.5 py-1.5 text-center text-xs text-zinc-800 dark:text-zinc-200">
            {button.text}
          </div>
        ),
      )}
    </div>
  );
}

function AttachmentIcon({ kind }: { kind: MessageAttachmentDescriptor['kind'] }) {
  if (kind === 'image') return <ImageIcon className="size-3.5 shrink-0" />;
  if (kind === 'video') return <Video className="size-3.5 shrink-0" />;
  if (kind === 'audio') return <Headphones className="size-3.5 shrink-0" />;
  if (kind === 'file') return <FileText className="size-3.5 shrink-0" />;
  if (kind === 'sticker') return <Smile className="size-3.5 shrink-0" />;
  if (kind === 'location') return <MapPin className="size-3.5 shrink-0" />;
  return <Paperclip className="size-3.5 shrink-0" />;
}

/** Human label for an attachment: the real filename when we have one (ours end
 *  in the clean name by construction - AC-D5), else the typed placeholder. */
function attachmentDisplayName(item: MessageAttachmentDescriptor): string {
  return item.fileName || item.label;
}

/** Typed placeholder for a non-text payload. Images preview inline; everything
 *  else (including types we do not know) shows an icon + label, never a blank.
 *  With a URL the whole block opens the shared CRM attachment preview (AC-D6);
 *  without one it stays a static placeholder. */
function AttachmentBlock({
  item,
  onOpen,
}: {
  item: MessageAttachmentDescriptor;
  onOpen?: () => void;
}) {
  const name = attachmentDisplayName(item);
  const caption = item.fileName ? `${item.label} · ${item.fileName}` : item.label;
  const body = (
    <>
      {item.kind === 'image' && item.url ? (
        // Remote Respond.io media: a plain <img> (next/image needs configured hosts).
        <img
          src={item.url}
          alt={caption}
          className="max-h-48 w-full rounded object-cover"
          loading="lazy"
        />
      ) : null}
      <div className="flex items-center gap-1.5 px-0.5 pt-1 text-xs opacity-80" title={caption}>
        <AttachmentIcon kind={item.kind} />
        <span className="truncate">{caption}</span>
      </div>
    </>
  );
  const shell = 'mt-1 rounded-md border border-black/5 bg-black/5 p-1.5 dark:border-white/10 dark:bg-white/5';
  if (!onOpen) return <div className={shell}>{body}</div>;
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={`Preview ${name}`}
      className={`${shell} block w-full cursor-pointer text-left hover:bg-black/10 dark:hover:bg-white/10`}
    >
      {body}
    </button>
  );
}

/**
 * Who to name as the sender of a quoted OUTGOING message. "You" is a lie
 * whenever a colleague, the bot or a workflow sent it, so a known automated
 * sender is named and anything else reads as the company.
 */
function quotedAgentLabel(quoted?: RespondMessageRenderable): string {
  if (!quoted) return 'Sorento';
  const label = getOutgoingSenderLabel(
    getNormalizedRespondSource(quoted),
    getRespondSenderName(quoted),
  );
  return label ?? 'Sorento';
}

function ReceiptTicks({ tier }: { tier: ReturnType<typeof getReceiptTier> }) {
  if (tier === 'none') return null;
  if (tier === 'sending') return <Clock className="size-3.5 opacity-70" aria-label="Sending" />;
  if (tier === 'failed') return <AlertCircle className="size-3.5 text-red-500" aria-label="Failed" />;
  if (tier === 'sent') return <Check className="size-3.5 opacity-70" aria-label="Sent" />;
  if (tier === 'delivered')
    return <CheckCheck className="size-3.5 opacity-70" aria-label="Delivered" />;
  return <CheckCheck className="size-3.5 text-sky-500" aria-label="Read" />;
}

/**
 * The "replying to" block above a bubble whose message quotes an earlier one
 * (UAC AC-L6). Clickable ONLY when the quoted message is in the loaded window:
 * a control that cannot do the thing it offers is worse than a plain label.
 */
function QuotedContextBlock({
  context,
  agentLabel,
  contactLabel,
  onJump,
}: {
  context: QuotedContext;
  /** Who sent the quoted message on OUR side, when it can be named. */
  agentLabel: string;
  /** The contact's own name, when the thread knows it. */
  contactLabel?: string | null;
  onJump?: () => void;
}) {
  // A quoted message from the contact reads as their name when we hold one, and
  // otherwise as a bare "Replying to" - the generic word "Contact" names nobody.
  const senderLabel =
    context.sender === 'contact'
      ? (contactLabel ?? '').trim() || null
      : context.sender === 'agent'
        ? agentLabel
        : null;
  const inner = (
    <>
      <span className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide opacity-70">
        <CornerUpLeft className="size-3" />
        {senderLabel ? `Replying to ${senderLabel}` : 'Replying to'}
      </span>
      <span className="line-clamp-3 whitespace-pre-wrap break-words">
        {stripWhatsAppMarkup(context.excerpt)}
      </span>
    </>
  );
  const className =
    'mb-1 flex w-full flex-col gap-0.5 rounded border-s-2 border-emerald-500 bg-black/5 px-2 py-1 text-start text-xs italic opacity-80 dark:bg-white/5';

  if (!onJump) {
    return (
      <div data-testid="quoted-context" className={className}>
        {inner}
      </div>
    );
  }
  return (
    <button
      type="button"
      data-testid="quoted-context"
      onClick={onJump}
      aria-label="Go to the quoted message"
      className={`${className} transition-colors hover:bg-black/10 dark:hover:bg-white/10`}
    >
      {inner}
    </button>
  );
}

export default function RespondChatList({
  items,
  contactName,
  contactPhone,
  emptyHint = 'No messages yet.',
  maxHeightClass = 'max-h-[60vh]',
  highlightMessageId = null,
  highlightLabel = 'Ticket based on this message',
  onLoadOlder,
  hasMoreOlder = false,
  isLoadingOlder = false,
  atConversationStart = false,
  isDetached = false,
  onJumpToLatest,
  newerUnseenCount = 0,
  onLoadNewer,
  hasMoreNewer = false,
  isLoadingNewer = false,
  searchController,
  highlightTerm = '',
  comments = [],
  mediaProxy,
  focusMessageId = null,
  focusNonce = 0,
}: RespondChatListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const highlightRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  // Populated by ref callbacks so a search jump can reach a bubble that is
  // already rendered without re-querying the DOM. Entries delete on unmount, so
  // a replaced window never leaves a stale node behind.
  const bubbleRefs = useRef(new Map<string, HTMLDivElement>());
  // Scroll metrics captured at the instant an older page was requested. The
  // correction has to run BEFORE paint (useLayoutEffect) or the viewport
  // visibly jumps to the top as the prepended messages push everything down.
  const prependAnchor = useRef<{ scrollHeight: number; scrollTop: number } | null>(null);

  // AC-D6: attachment bubbles open the SAME preview surface the rest of the CRM
  // uses (image/video/pdf inline, spreadsheets via its Excel slide, everything
  // else its download/open fallback) - never a raw-URL new tab. Chat media has
  // no `attachments` row, so items carry the CDN url only: without a
  // `mediaProxy` there is no `downloadUrl` either, the modal's authenticated
  // byte-fetch is never called, and the token-authenticated portal thread keeps
  // working. With one (AC-N4) the url doubles as the item's byte source and the
  // proxy reads it server-side, which is what makes .xlsx/.csv render inline.
  const [previewItems, setPreviewItems] = useState<AttachmentPreviewItem[]>([]);
  const [previewIndex, setPreviewIndex] = useState(0);
  // Briefly ringed after a quote-block jump, so the reader sees WHICH bubble the
  // thread moved to (AC-L6).
  const [flashMessageId, setFlashMessageId] = useState<string | null>(null);
  // The reader is far enough up the thread that the live tail is off screen.
  // Drives the scroll-to-latest button on EVERY surface, not only a detached
  // (search-jumped) window.
  const [scrolledUp, setScrolledUp] = useState(false);

  const openPreview = useCallback(
    (attachments: MessageAttachmentDescriptor[], clicked: number, idPrefix: string) => {
      const items = attachments
        .map((att, i) => ({ att, i }))
        .filter(({ att }) => !!att.url)
        .map(({ att, i }) => ({
          id: `${idPrefix}-att-${i}`,
          name: attachmentDisplayName(att),
          url: att.url as string,
          // Only with a proxy: `downloadUrl` is what turns the Download button
          // and the Excel slide on, and both read it through `fetchBytes`.
          downloadUrl: mediaProxy ? (att.url as string) : undefined,
        }));
      if (items.length === 0) return;
      const start = items.findIndex((it) => it.id === `${idPrefix}-att-${clicked}`);
      setPreviewIndex(start < 0 ? 0 : start);
      setPreviewItems(items);
    },
    [mediaProxy],
  );

  const previewFetchBytes = useMemo(
    () =>
      mediaProxy
        ? (item: AttachmentPreviewItem) => mediaProxy(item.downloadUrl ?? item.url)
        : undefined,
    [mediaProxy],
  );

  const normalizedHighlightId =
    highlightMessageId != null && String(highlightMessageId).trim() !== ''
      ? String(highlightMessageId)
      : null;

  const sortedItems = useMemo(() => {
    return [...items].sort((a, b) => {
      const ta = getRespondMessageSortTimeMs(a);
      const tb = getRespondMessageSortTimeMs(b);
      if (ta !== tb) return ta - tb;
      return (a.messageId ?? 0) - (b.messageId ?? 0);
    });
  }, [items]);

  // Messages and internal notes are two streams shown as one thread: comments
  // live in their own table (never in `chat_histories`), so the interleave
  // happens here, at render time, on the wall clock both carry.
  const entries = useMemo(() => {
    const messageEntries = sortedItems.map((item) => ({
      kind: 'message' as const,
      item,
      ms: getRespondMessageSortTimeMs(item),
    }));
    if (comments.length === 0) return messageEntries;
    const commentEntries = comments.map((comment) => ({
      kind: 'comment' as const,
      comment,
      ms: parseDateTimeAsUTC(comment.created_at).getTime() || 0,
    }));
    // Stable sort with the messages listed first, so a note written in the same
    // millisecond as a message reads as the reaction it is.
    return [...messageEntries, ...commentEntries].sort((a, b) => a.ms - b.ms);
  }, [sortedItems, comments]);

  const activeMatchId = searchController?.activeMessageId ?? null;
  // Pinning to the newest message is right while reading the live tail and
  // wrong the moment the reader is looking at something specific: a search
  // jump, or a pending one, would be yanked back to the bottom.
  const pinToBottom = !searchController?.open && !activeMatchId;

  /**
   * When we last scrolled the reader to an arbitrary bubble (the enquiry, a
   * search match, a quoted message). Those animations emit scroll events all
   * the way there, and one landing near the top reads exactly like a reader who
   * dragged to the top - which fetched a page nobody asked for. Scrolling to
   * the BOTTOM needs no such guard: it ends far from the top threshold.
   */
  const lastProgrammaticScrollAt = useRef(0);
  const scrollBubbleIntoView = useCallback(
    (node: HTMLElement | null | undefined, options: ScrollIntoViewOptions) => {
      if (!node?.scrollIntoView) return;
      lastProgrammaticScrollAt.current = Date.now();
      node.scrollIntoView(options);
    },
    [],
  );

  // The enquiry bubble is scrolled to ONCE per highlighted message, not on every
  // render that changes the item count: the drawer always passes a highlight id,
  // so re-running this on each prepended page (or each live poll) dragged the
  // reader back to the enquiry every time they scrolled up. The item count stays
  // in the deps because the target bubble mounts asynchronously - the ref, not
  // the dependency list, is what makes it fire once.
  const didHighlight = useRef<string | null>(null);
  useEffect(() => {
    if (activeMatchId || !normalizedHighlightId) return;
    if (didHighlight.current === normalizedHighlightId) return;
    const node = highlightRef.current;
    if (!node) return;
    didHighlight.current = normalizedHighlightId;
    scrollBubbleIntoView(node, { behavior: 'smooth', block: 'center' });
  }, [sortedItems.length, normalizedHighlightId, activeMatchId, scrollBubbleIntoView]);

  // Whether this thread has been landed on its tail yet. The slack check below
  // exists so a reader who scrolled up to read history is not yanked back on
  // every poll - but on the FIRST render of a long thread the reader is at the
  // top only because that is where a fresh scroll container starts, and the
  // slack check read that as "reading history" and never pinned at all. Reset
  // when the items empty out (a different conversation loading in the same
  // mounted list).
  const pinnedOnce = useRef(false);
  useEffect(() => {
    if (sortedItems.length === 0) {
      pinnedOnce.current = false;
      return;
    }
    if (activeMatchId || !pinToBottom) return;
    // A highlighted thread anchors on the enquiry, not on the tail. Until that
    // bubble is loaded there is nothing to anchor to, so the newest message is
    // still the right place to be.
    if (normalizedHighlightId) {
      if (highlightRef.current || didHighlight.current === normalizedHighlightId) return;
    }
    // A page that was just prepended leaves the reader at the top on purpose.
    if (prependAnchor.current) return;
    const firstPin = !pinnedOnce.current;
    // The reader's own send always lands at the tail, wherever they were
    // scrolled (optimistic send AC-B1): a bubble they cannot see is no answer
    // to "did it go?".
    const newest = sortedItems[sortedItems.length - 1] as { source?: string } | undefined;
    const ownSend = newest?.source === 'pending';
    if (!firstPin && !ownSend) {
      const node = scrollRef.current;
      const distanceFromBottom = node
        ? node.scrollHeight - node.scrollTop - node.clientHeight
        : 0;
      if (distanceFromBottom > PIN_TO_BOTTOM_SLACK_PX) return;
    }
    pinnedOnce.current = true;
    messagesEndRef.current?.scrollIntoView?.({ behavior: firstPin ? 'auto' : 'smooth' });
  }, [sortedItems, normalizedHighlightId, activeMatchId, pinToBottom]);

  // Scroll anchoring: restore the reader's distance from the OLD top edge.
  useLayoutEffect(() => {
    const anchor = prependAnchor.current;
    const node = scrollRef.current;
    if (!anchor || !node) return;
    const grew = node.scrollHeight - anchor.scrollHeight;
    if (grew <= 0) return;
    node.scrollTop = anchor.scrollTop + grew;
    prependAnchor.current = null;
  }, [sortedItems.length]);

  // A page request that came back empty (or failed) must release the anchor, or
  // the next genuine prepend would be corrected against stale metrics.
  useEffect(() => {
    if (!isLoadingOlder) prependAnchor.current = null;
  }, [isLoadingOlder]);

  useEffect(() => {
    if (!activeMatchId) return;
    scrollBubbleIntoView(bubbleRefs.current.get(activeMatchId), {
      behavior: 'smooth',
      block: 'center',
    });
  }, [activeMatchId, sortedItems.length, scrollBubbleIntoView]);

  // In-flight latch for the older lane. A ref, not the `isLoadingOlder` prop:
  // scroll fires many times per frame and the prop only arrives a render later,
  // so the state guard let a burst stack three or four pages.
  const olderRequested = useRef(false);
  useEffect(() => {
    if (!isLoadingOlder) olderRequested.current = false;
  });
  const newerRequested = useRef(false);
  useEffect(() => {
    if (!isLoadingNewer) newerRequested.current = false;
  });

  const handleScroll = useCallback(() => {
    const node = scrollRef.current;
    if (!node) return;
    // Measured on EVERY scroll event, including our own animations: the button
    // has to be right about where the reader ended up, whoever moved them.
    setScrolledUp(
      node.scrollHeight - node.scrollTop - node.clientHeight >
        node.clientHeight * SCROLLED_UP_SHOW_JUMP_RATIO,
    );
    if (Date.now() - lastProgrammaticScrollAt.current < PROGRAMMATIC_SCROLL_SETTLE_MS) return;

    if (node.scrollTop <= LOAD_OLDER_THRESHOLD_PX) {
      if (!onLoadOlder || !hasMoreOlder || isLoadingOlder || olderRequested.current) return;
      olderRequested.current = true;
      prependAnchor.current = { scrollHeight: node.scrollHeight, scrollTop: node.scrollTop };
      onLoadOlder();
      return;
    }
    // Away from the top again: whatever happened to the last request, the
    // reader can ask for another page next time they get there.
    olderRequested.current = false;

    if (!isDetached || !onLoadNewer || !hasMoreNewer || isLoadingNewer) return;
    const distanceFromBottom = node.scrollHeight - node.scrollTop - node.clientHeight;
    if (distanceFromBottom > LOAD_NEWER_THRESHOLD_PX) {
      newerRequested.current = false;
      return;
    }
    if (newerRequested.current) return;
    newerRequested.current = true;
    onLoadNewer();
  }, [
    onLoadOlder,
    hasMoreOlder,
    isLoadingOlder,
    isDetached,
    onLoadNewer,
    hasMoreNewer,
    isLoadingNewer,
  ]);

  const registerBubble = useCallback(
    (id: string) => (node: HTMLDivElement | null) => {
      if (node) bubbleRefs.current.set(id, node);
      else bubbleRefs.current.delete(id);
    },
    [],
  );

  // AC-L6: tapping a "replying to" block jumps to the quoted message when it is
  // in the loaded window. It deliberately does NOT fetch the page containing it:
  // that is the search jump's job (which replaces the window), and doing it from
  // a passive quote block would move the thread under a reader who only glanced
  // at the quote. Out of window = the block renders as plain text, not a
  // button, so nothing offers an action it cannot perform.
  const loadedMessages = useMemo(() => {
    const byId = new Map<string, RespondMessageRenderable>();
    for (const item of sortedItems) {
      if (item.messageId != null) byId.set(String(item.messageId), item);
    }
    return byId;
  }, [sortedItems]);

  const jumpToMessage = useCallback(
    (id: string) => {
      scrollBubbleIntoView(bubbleRefs.current.get(id), { behavior: 'smooth', block: 'center' });
      setFlashMessageId(id);
    },
    [scrollBubbleIntoView],
  );

  // AC-N6: an external jump (the drawer's quoted enquiry). The nonce is the
  // trigger, and it is only marked handled once the bubble EXISTS - after an
  // around-page load the target mounts a render or two later, so the effect
  // re-runs on the item count until it can actually scroll.
  const handledFocusNonce = useRef(0);
  useEffect(() => {
    if (!focusNonce || focusNonce === handledFocusNonce.current) return;
    if (!focusMessageId) return;
    const node = bubbleRefs.current.get(focusMessageId);
    if (!node) return;
    handledFocusNonce.current = focusNonce;
    scrollBubbleIntoView(node, { behavior: 'smooth', block: 'center' });
    setFlashMessageId(focusMessageId);
  }, [focusNonce, focusMessageId, sortedItems.length, scrollBubbleIntoView]);

  // Clear the flash ring after it has been seen. Reset on every new target so a
  // second jump re-flashes instead of inheriting the first one's timer.
  useEffect(() => {
    if (!flashMessageId) return;
    const t = setTimeout(() => setFlashMessageId(null), 1800);
    return () => clearTimeout(t);
  }, [flashMessageId]);

  const contactInitial = (contactName?.trim()?.charAt(0) || '?').toUpperCase();
  const headerName = contactName?.trim() || 'Unknown contact';
  const headerPhone = contactPhone?.trim() || '';

  let lastDateKey = '';

  return (
    <div className="relative flex flex-col">
      <div className="flex items-center gap-3 rounded-t-md border border-b-0 bg-[#f0f2f5] dark:bg-[#202c33] px-3 py-2">
        <div className="flex size-9 items-center justify-center rounded-full bg-emerald-600 text-sm font-semibold text-white">
          {contactInitial}
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            {headerName}
          </div>
          {headerPhone && (
            <div className="truncate text-xs text-zinc-500 dark:text-zinc-400">{headerPhone}</div>
          )}
        </div>
        {searchController && !searchController.open && (
          <button
            type="button"
            aria-label="Search messages"
            onClick={searchController.openSearch}
            className="ms-auto shrink-0 rounded p-1.5 text-zinc-600 hover:bg-black/5 dark:text-zinc-300 dark:hover:bg-white/10"
          >
            <Search className="size-4" />
          </button>
        )}
      </div>

      {searchController && <ConversationSearchBar controller={searchController} />}

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        data-testid="chat-scroll-container"
        className={`flex flex-col gap-2 overflow-y-auto rounded-b-md border bg-[#efeae2] dark:bg-[#0b141a] p-3 ${maxHeightClass}`}
      >
        {isLoadingOlder && (
          <div
            data-testid="chat-older-loading"
            className="flex items-center justify-center gap-2 py-2 text-xs text-zinc-500 dark:text-zinc-400"
          >
            <Loader2 className="size-3.5 animate-spin" />
            Loading earlier messages
          </div>
        )}
        {!isLoadingOlder && atConversationStart && (
          <p
            data-testid="chat-conversation-start"
            className="py-1 text-center text-[11px] text-zinc-500 dark:text-zinc-400"
          >
            Beginning of this conversation
          </p>
        )}
        {entries.length === 0 && (
          <p className="py-4 text-center text-sm text-zinc-500 dark:text-zinc-400">{emptyHint}</p>
        )}
        {entries.map((entry, idx) => {
          if (entry.kind === 'comment') {
            const comment = entry.comment;
            const dKeyNote = entry.ms > 0 ? dateKeyFromMs(entry.ms) : '';
            const noteDivider =
              dKeyNote && dKeyNote !== lastDateKey ? formatDatePillLabel(entry.ms) : '';
            if (dKeyNote) lastDateKey = dKeyNote;
            return (
              <div key={`note-${comment.id}`} data-testid="chat-internal-note">
                {noteDivider && (
                  <div className="sticky top-0 z-10 my-2 flex justify-center">
                    <span className="rounded-md bg-[#e1f3fb] dark:bg-[#1d282f] px-3 py-0.5 text-xs font-medium text-zinc-700 dark:text-zinc-300 shadow-sm">
                      {noteDivider}
                    </span>
                  </div>
                )}
                <div className="flex justify-center">
                  <div className="max-w-[92%] rounded-lg border border-amber-300 bg-amber-50 px-2.5 py-1.5 text-sm text-amber-950 shadow-sm dark:border-amber-700 dark:bg-amber-950/60 dark:text-amber-100">
                    <div className="mb-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] font-semibold text-amber-800 dark:text-amber-300">
                      <span className="inline-flex items-center gap-1">
                        <StickyNote className="size-3" />
                        Internal
                      </span>
                      <span>{comment.author_name || 'Unknown author'}</span>
                      {/* Same clock as the message bubbles: a note sitting
                          between two messages must not read on a different
                          timezone, and the date pill above already carries the
                          day. */}
                      <span
                        className="font-normal opacity-80"
                        data-testid="chat-internal-note-time"
                      >
                        {entry.ms > 0 ? formatBubbleTime(entry.ms) : ''}
                      </span>
                    </div>
                    {comment.mentioned_names && comment.mentioned_names.length > 0 && (
                      <div
                        className="mb-0.5 flex flex-wrap gap-x-1.5 text-xs font-medium text-sky-700 dark:text-sky-300"
                        data-testid="chat-internal-note-mentions"
                      >
                        {comment.mentioned_names.map((name) => (
                          <span key={name}>@{name}</span>
                        ))}
                      </div>
                    )}
                    <div className="whitespace-pre-wrap break-words leading-snug">
                      <HighlightedText text={comment.body} term={highlightTerm} />
                    </div>
                  </div>
                </div>
              </div>
            );
          }

          const item = entry.item;
          const isOutgoing = item.traffic === 'outgoing';
          const text = getMessageBodyText(item);
          // AC-L6: a contact's quote-reply arrives as a STRUCTURED `replyTo`.
          // There is no outgoing counterpart - Respond's send API takes no
          // reply-to, and the ">"-prefix emulation we used to write was removed
          // rather than left to read like a real quote.
          const quotedContext = describeQuotedContext(item);
          const attachments = describeMessageAttachments(item);
          const displayMs = getRespondMessageDisplayTimeMs(item);
          const key = item.messageId != null ? String(item.messageId) : `msg-${idx}`;

          const dKey = displayMs > 0 ? dateKeyFromMs(displayMs) : '';
          const dividerLabel =
            dKey && dKey !== lastDateKey ? formatDatePillLabel(displayMs) : '';
          if (dKey) lastDateKey = dKey;

          const sourceNorm = getNormalizedRespondSource(item);
          // No label on an incoming bubble (the thread IS this contact, and the
          // header already names them) and none on a machine send. A colleague's
          // own reply keeps their name - see getOutgoingSenderLabel.
          const senderLabel = isOutgoing
            ? getOutgoingSenderLabel(sourceNorm, getRespondSenderName(item))
            : null;

          const bubbleClass = isOutgoing
            ? 'bg-[#d9fdd3] text-zinc-900 dark:bg-[#005c4b] dark:text-zinc-50'
            : 'bg-white text-zinc-900 dark:bg-[#202c33] dark:text-zinc-50';

          const options = extractSelectionOptions(item);
          const templateButtons = extractTemplateButtons(item);
          const tier = getReceiptTier(item);
          const isHighlighted =
            normalizedHighlightId != null && String(item.messageId ?? '') === normalizedHighlightId;
          const isActiveMatch = activeMatchId != null && String(item.messageId ?? '') === activeMatchId;
          const isFlashed =
            flashMessageId != null && String(item.messageId ?? '') === flashMessageId;
          const quotedTarget = quotedContext?.messageId
            ? loadedMessages.get(quotedContext.messageId)
            : undefined;
          const quotedTargetId = quotedTarget ? (quotedContext?.messageId ?? null) : null;

          return (
            <div
              key={key}
              data-message-id={item.messageId != null ? String(item.messageId) : undefined}
              ref={(node) => {
                if (isHighlighted) highlightRef.current = node;
                if (item.messageId != null) registerBubble(String(item.messageId))(node);
              }}
            >
              {dividerLabel && (
                <div className="sticky top-0 z-10 my-2 flex justify-center">
                  <span className="rounded-md bg-[#e1f3fb] dark:bg-[#1d282f] px-3 py-0.5 text-xs font-medium text-zinc-700 dark:text-zinc-300 shadow-sm">
                    {dividerLabel}
                  </span>
                </div>
              )}
              {isHighlighted && (
                <div className={`mb-1 flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-800 ring-1 ring-amber-300 dark:bg-amber-900/40 dark:text-amber-200 dark:ring-amber-700">
                    {highlightLabel}
                  </span>
                </div>
              )}
              <div className={`flex ${isOutgoing ? 'justify-end' : 'justify-start'}`}>
                <div
                  data-active-match={isActiveMatch ? 'true' : undefined}
                  className={`max-w-[85%] rounded-lg px-2.5 py-1.5 text-sm shadow-sm ${bubbleClass}${
                    isHighlighted ? ' ring-2 ring-amber-400 dark:ring-amber-500' : ''
                  }${isActiveMatch ? ' ring-2 ring-sky-500 dark:ring-sky-400' : ''}${
                    isFlashed ? ' ring-2 ring-emerald-500 dark:ring-emerald-400' : ''
                  }`}
                >
                  {senderLabel && (
                    <div className="mb-0.5 flex items-center gap-2">
                      <span className="text-[11px] font-semibold text-emerald-700 dark:text-emerald-300">
                        {senderLabel}
                      </span>
                    </div>
                  )}
                  {quotedContext && (
                    <QuotedContextBlock
                      context={quotedContext}
                      agentLabel={quotedAgentLabel(quotedTarget)}
                      contactLabel={contactName}
                      onJump={quotedTargetId ? () => jumpToMessage(quotedTargetId) : undefined}
                    />
                  )}
                  {attachments.map((att, i) => (
                    <AttachmentBlock
                      key={`${key}-att-${i}`}
                      item={att}
                      onOpen={att.url ? () => openPreview(attachments, i, key) : undefined}
                    />
                  ))}
                  {text && (
                    <div className="whitespace-pre-wrap break-words leading-snug">
                      <FormattedMessageText text={text} term={highlightTerm} />
                    </div>
                  )}
                  {options.length > 0 && (
                    <div className="mt-2 flex flex-col divide-y divide-zinc-200 overflow-hidden rounded border border-zinc-200 bg-white/70 dark:divide-zinc-700 dark:border-zinc-700 dark:bg-zinc-900/40">
                      {options.map((opt, i) => (
                        <div
                          key={`${key}-opt-${i}`}
                          className="px-2.5 py-1.5 text-xs text-zinc-800 dark:text-zinc-200"
                        >
                          {opt}
                        </div>
                      ))}
                    </div>
                  )}
                  <TemplateButtons buttons={templateButtons} />
                  {!text &&
                    options.length === 0 &&
                    templateButtons.length === 0 &&
                    attachments.length === 0 &&
                    !quotedContext && <div className="italic opacity-70">(no text)</div>}
                  <div className="mt-1 flex items-center justify-end gap-1 text-[10px] text-zinc-500 dark:text-zinc-300/80">
                    {displayMs > 0 && <span>{formatBubbleTime(displayMs)}</span>}
                    <ReceiptTicks tier={tier} />
                  </div>
                </div>
              </div>
            </div>
          );
        })}
        {isLoadingNewer && (
          <div
            data-testid="chat-newer-loading"
            className="flex items-center justify-center gap-2 py-2 text-xs text-zinc-500 dark:text-zinc-400"
          >
            <Loader2 className="size-3.5 animate-spin" />
            Loading newer messages
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* The way back to the live tail: shown whenever the reader is about a
          viewport up, not only from a detached (search-jumped) window - being
          scrolled up in a long thread is the ordinary case, and hunting for the
          scrollbar is not an answer. ONE control for both: detached windows
          re-attach through `onJumpToLatest`, an attached one just scrolls.
          Absolutely positioned so it costs the scroll container no height and
          cannot disturb the anchoring maths. */}
      {(scrolledUp || (isDetached && onJumpToLatest)) && (
        <button
          type="button"
          data-testid="chat-jump-to-latest"
          aria-label="Jump to the latest messages"
          title="Jump to the latest messages"
          onClick={() => {
            if (isDetached && onJumpToLatest) {
              onJumpToLatest();
              return;
            }
            messagesEndRef.current?.scrollIntoView?.({ behavior: 'smooth' });
            setScrolledUp(false);
          }}
          className="absolute bottom-3 end-3 z-20 inline-flex size-9 items-center justify-center rounded-full border bg-white text-zinc-700 shadow-md hover:bg-zinc-50 dark:border-zinc-700 dark:bg-[#202c33] dark:text-zinc-200 dark:hover:bg-[#2a3942]"
        >
          <ArrowDownToLine className="size-4" />
          {newerUnseenCount > 0 && (
            <span
              data-testid="chat-unseen-count"
              className="absolute -top-2 -end-2 rounded-full bg-emerald-600 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-white"
            >
              {newerUnseenCount} new
            </span>
          )}
        </button>
      )}

      <AttachmentPreviewModal
        open={previewItems.length > 0}
        onOpenChange={(next) => {
          if (!next) setPreviewItems([]);
        }}
        items={previewItems}
        startIndex={previewIndex}
        fetchBytes={previewFetchBytes}
      />
    </div>
  );
}
