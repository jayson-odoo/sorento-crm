'use client';

/**
 * One proof-carrying fact chip on a planning change row (PLAN-so-book-diff-replanning.md).
 *
 * The captain: "for the facts, I need more justification, like what do you mean by hot
 * selling, is it dealer side hot selling? prove to me." A chip is never just a word - the
 * label already says what and where, and `title` carries the full sentence a hover reveals.
 */
export function FactChip({ label, title }: { label: string; title: string }) {
  return (
    <span
      title={title}
      className="inline-flex items-center rounded bg-amber-100 px-1.5 py-0.5 text-2xs font-medium text-amber-800"
    >
      {label}
    </span>
  );
}

export default FactChip;
