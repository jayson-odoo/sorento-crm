'use client';

import { Inbox } from 'lucide-react';

export function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center text-muted-foreground">
      <Inbox className="size-10 mb-3 opacity-60" />
      <p className="text-sm font-medium text-foreground">No uploads yet</p>
      <p className="text-xs mt-1 max-w-xs">
        Files you upload will appear here with their integration status.
      </p>
    </div>
  );
}
