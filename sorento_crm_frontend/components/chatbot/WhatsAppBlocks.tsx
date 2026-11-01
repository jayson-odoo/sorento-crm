'use client';

import { parseWhatsAppBlocks } from '@/lib/whatsappText';
import { WhatsAppText } from './WhatsAppText';

// A triple-backtick fence (left whole for `WhatsAppText`) or a single-backtick span on one line.
const CODE_SPAN = /(```[\s\S]*?```)|`([^`\n]+)`/g;

/**
 * Inline code on the panel: a `span` becomes a code element with its content as plain text (literal HTML
 * stays text), everything else goes through `WhatsAppText`. Splitting first keeps `*bold*` beside code
 * working. A lone backtick stays as typed.
 */
function InlineText({ text }: { text: string }) {
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(CODE_SPAN)) {
    if (match[2] === undefined) continue;
    const at = match.index ?? 0;
    if (at > last) parts.push(<WhatsAppText key={`t${at}`} text={text.slice(last, at)} />);
    parts.push(
      <code key={`c${at}`} className="rounded bg-muted px-1 py-0.5 text-[0.9em]">
        {match[2]}
      </code>,
    );
    last = at + match[0].length;
  }
  if (parts.length === 0) return <WhatsAppText text={text} />;
  if (last < text.length) parts.push(<WhatsAppText key="tail" text={text.slice(last)} />);
  return <>{parts}</>;
}

/**
 * A brain reply on the panel: WhatsApp text with real lists. Text runs keep their line breaks, list
 * items hang under their marker, and every line goes through `WhatsAppText` (so markup, links and
 * literal HTML behave as they do in the console and the inbox).
 */
export function WhatsAppBlocks({ text }: { text: string }) {
  const blocks = parseWhatsAppBlocks(text);
  if (blocks.length === 0) return null;
  return (
    <div className="space-y-1.5">
      {blocks.map((block, i) => {
        if (block.kind === 'text') {
          return (
            <div key={i} className="whitespace-pre-wrap break-words">
              <InlineText text={block.text} />
            </div>
          );
        }
        const items = block.items.map((item, j) => (
          <li key={j} value={item.number ?? undefined} className="whitespace-pre-wrap break-words">
            <InlineText text={item.text} />
          </li>
        ));
        return block.ordered ? (
          <ol key={i} start={block.start} className="list-decimal space-y-0.5 ps-5">
            {items}
          </ol>
        ) : (
          <ul key={i} className="list-disc space-y-0.5 ps-5">
            {items}
          </ul>
        );
      })}
    </div>
  );
}
