'use client';

/**
 * A rich price tag description as read-only text (PRICETAG-COMBO-FORMAT): drawn from the parser's
 * blocks as React elements, never raw tags and never `innerHTML`. Legacy plain text reads as it
 * always did, one paragraph per line.
 */

import type { CSSProperties } from 'react';
import { cn } from '@/lib/utils';
import { parseRichText, type RichBlock, type RichRun } from '@/lib/dealer-kit/rich-text';

function Run({ run }: { run: RichRun }) {
  const style: CSSProperties = {
    ...(run.color ? { color: run.color } : {}),
    ...(run.highlight ? { backgroundColor: run.highlight } : {}),
    ...(run.underline || run.strike
      ? {
          textDecoration: [run.underline && 'underline', run.strike && 'line-through']
            .filter(Boolean)
            .join(' '),
        }
      : {}),
  };
  let node: React.ReactNode = run.text;
  if (run.code) node = <code className="rounded bg-muted px-1">{node}</code>;
  if (run.italic) node = <em>{node}</em>;
  if (run.bold) node = <strong>{node}</strong>;
  return <span style={style}>{node}</span>;
}

const SIZE: Record<RichBlock['kind'], string> = {
  p: '',
  li: '',
  quote: 'border-l-2 pl-3 text-muted-foreground',
  h1: 'text-lg font-semibold',
  h2: 'text-base font-semibold',
  h3: 'text-sm font-semibold',
};

export function RichTextView({
  value,
  blocks: given,
  className,
}: {
  value?: string | null;
  /** Already parsed blocks (merge fields resolved), instead of a stored value. */
  blocks?: RichBlock[];
  className?: string;
}) {
  const blocks = given ?? parseRichText(value);
  if (blocks.length === 0) return <p className={cn('text-sm', className)}>-</p>;
  return (
    <div className={cn('space-y-1 break-words text-sm', className)}>
      {blocks.map((block, index) => (
        <p
          key={index}
          className={cn('whitespace-pre-line', SIZE[block.kind])}
          style={{
            ...(block.align ? { textAlign: block.align } : {}),
            ...(block.kind === 'li' ? { paddingLeft: `${(block.level ?? 1) * 1.25}rem` } : {}),
          }}
        >
          {block.kind === 'li' ? <span className="mr-1">{block.marker}</span> : null}
          {block.runs.length === 0 ? ' ' : block.runs.map((run, at) => <Run key={at} run={run} />)}
        </p>
      ))}
    </div>
  );
}

export default RichTextView;
