import type { EmailBlock } from '../types/emailTemplate.types';
import { BLOCK_TYPE_LABELS, summarizeBlock } from '../lib/emailBlocks';

/** The view-mode counterpart to `BlockListEditor` - each block as one
 * read-only row (type + short summary), same order (AC-EM040). */
export function BlockListReadOnly({ blocks }: { blocks: EmailBlock[] }) {
  if (blocks.length === 0) {
    return <p className="text-sm text-muted-foreground">No blocks yet.</p>;
  }

  return (
    <ol className="space-y-1" data-slot="block-list-readonly">
      {blocks.map((block, index) => (
        <li
          key={block.id ?? index}
          className="flex items-start gap-2 rounded-md border border-border px-2.5 py-1.5 text-sm"
        >
          <span className="w-5 shrink-0 text-muted-foreground tabular-nums">{index + 1}.</span>
          <div className="min-w-0 flex-1">
            <span className="font-medium">{BLOCK_TYPE_LABELS[block.type]}</span>
            <span className="ml-2 truncate text-muted-foreground" title={summarizeBlock(block)}>
              {summarizeBlock(block)}
            </span>
          </div>
        </li>
      ))}
    </ol>
  );
}

export default BlockListReadOnly;
