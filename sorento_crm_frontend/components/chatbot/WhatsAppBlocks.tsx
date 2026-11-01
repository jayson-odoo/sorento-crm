'use client';

import { Fragment } from 'react';
import { parseWhatsAppBlocks, parseWhatsAppText } from '@/lib/whatsappText';
import { WhatsAppText } from './WhatsAppText';

// A triple-backtick fence (left whole for `WhatsAppText`) or a single-backtick span on one line.
const CODE_SPAN = /(```[\s\S]*?```)|`([^`\n]+)`/g;

// Stands in for a code span while the markup is parsed, so a marker around code pairs up as it does on a
// handset. A private-use character is not whitespace, so it opens and closes a run like any word.
const SLOT = '\uE000';

/**
 * Inline code on the panel: each single-backtick span becomes a code element with its content as plain text
 * (literal HTML stays text). The spans are swapped for a slot, the rest is parsed by `parseWhatsAppText`
 * (so `*bold*` can wrap code), and each slot is filled back in. A lone backtick stays as typed.
 */
function InlineText({ text }: { text: string }) {
  const spans: string[] = [];
  const masked = text.replace(CODE_SPAN, (whole, _fence, code) => {
    if (code === undefined) return whole;
    spans.push(code);
    return SLOT;
  });
  if (spans.length === 0) return <WhatsAppText text={text} />;
  let next = 0;
  return (
    <>
      {parseWhatsAppText(masked).map((segment, i) => {
        if (segment.code) return <WhatsAppText key={i} text={`\`\`\`${segment.text}\`\`\``} />;
        let node: React.ReactNode = segment.text.split(SLOT).map((part, j) => (
          <Fragment key={j}>
            {j > 0 && (
              <code className="rounded bg-muted px-1 py-0.5 text-[0.9em]">{spans[next++]}</code>
            )}
            {part}
          </Fragment>
        ));
        if (segment.strike) node = <s>{node}</s>;
        if (segment.italic) node = <em>{node}</em>;
        if (segment.bold) node = <strong className="font-semibold">{node}</strong>;
        if (segment.href) {
          node = (
            <a
              href={segment.href}
              target="_blank"
              rel="noopener noreferrer"
              className="break-all underline underline-offset-2 hover:opacity-80"
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
