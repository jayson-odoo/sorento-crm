'use client';

import { parseWhatsAppBlocks } from '@/lib/whatsappText';
import { WhatsAppText } from './WhatsAppText';

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
              <WhatsAppText text={block.text} />
            </div>
          );
        }
        const items = block.items.map((item, j) => (
          <li key={j} className="break-words">
            <WhatsAppText text={item} />
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
