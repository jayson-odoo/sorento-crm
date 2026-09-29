'use client';

import { parseWhatsAppText } from '@/lib/whatsappText';

/**
 * A bot reply rendered the way the handset renders it: WhatsApp `*bold*`,
 * `_italic_`, `~strike~` and fenced monospace applied, bare URLs clickable.
 * The parse is `lib/whatsappText.ts` (the same one the Conversations inbox
 * uses); this is only the React half, without the inbox's search highlight.
 * Plain React text nodes throughout, so literal markup in a reply stays text.
 */
export function WhatsAppText({ text }: { text: string }) {
  return (
    <>
      {parseWhatsAppText(text).map((segment, i) => {
        if (segment.code) {
          return (
            <code
              key={i}
              className="block whitespace-pre-wrap rounded bg-black/5 px-1.5 py-1 font-mono text-xs dark:bg-white/10"
            >
              {segment.text}
            </code>
          );
        }

        let node: React.ReactNode = segment.text;
        if (segment.strike) node = <s>{node}</s>;
        if (segment.italic) node = <em>{node}</em>;
        if (segment.bold)
          node = <strong className="font-semibold">{node}</strong>;

        if (segment.href) {
          return (
            <a
              key={i}
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
