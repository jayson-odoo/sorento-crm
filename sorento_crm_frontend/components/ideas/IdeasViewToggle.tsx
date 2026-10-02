import Link from 'next/link';
import { Button } from '@/components/ui/button';

/** List and Board are two views of the same ideas: a toggle in the toolbar, not a second menu entry. */
export function IdeasViewToggle({ active }: { active: 'list' | 'board' }) {
  return (
    <div className="flex items-center gap-1 rounded-md border border-input p-0.5" role="group" aria-label="View">
      {(['list', 'board'] as const).map((view) => (
        <Button
          key={view}
          asChild
          size="sm"
          variant={active === view ? 'secondary' : 'ghost'}
          aria-current={active === view ? 'page' : undefined}
        >
          <Link href={view === 'list' ? '/ideas' : '/ideas/board'}>{view === 'list' ? 'List' : 'Board'}</Link>
        </Button>
      ))}
    </div>
  );
}
