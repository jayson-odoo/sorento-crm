'use client';

import { CornerUpLeft } from 'lucide-react';

import type { QuotedContext } from '@/lib/respondIoChatRender';
import { stripWhatsAppMarkup } from '@/lib/whatsappText';

/**
 * The "replying to" block above a bubble whose message quotes an earlier one
 * (UAC AC-L6, #1317). One component for every thread surface, so a quote reads
 * the same wherever the conversation is shown.
 *
 * Compact on purpose (owner answer 2, #1317): the quote is at most two short
 * lines in the small size, the rest clipped (full text on hover), so a long
 * quoted message never buries the reply under it.
 *
 * Clickable ONLY when the quoted message is in the loaded window: a control
 * that cannot do the thing it offers is worse than a plain label.
 */
export default function QuotedContextBlock({
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
  const excerpt = stripWhatsAppMarkup(context.excerpt);
  const inner = (
    <>
      <span className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide opacity-70">
        <CornerUpLeft className="size-3" />
        {senderLabel ? `Replying to ${senderLabel}` : 'Replying to'}
      </span>
      <span
        data-testid="quoted-context-excerpt"
        title={excerpt}
        className="line-clamp-2 break-words"
      >
        {excerpt}
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
