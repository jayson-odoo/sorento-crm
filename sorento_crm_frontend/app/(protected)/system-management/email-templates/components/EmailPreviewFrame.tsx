'use client';

import { useState } from 'react';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

type PreviewMode = 'desktop' | 'mobile';

const WIDTH_BY_MODE: Record<PreviewMode, number> = {
  desktop: 600,
  mobile: 375,
};

export interface EmailPreviewFrameProps {
  subject?: string | null;
  html?: string | null;
  /** True while a fresh render is in flight (AC-EM030/031 debounce) - keeps
   * the last good frame on screen instead of blanking it every keystroke. */
  isLoading?: boolean;
  className?: string;
  /**
   * The desktop pane's width. 600 (the standard card) unless the document being
   * previewed is `width: 'wide'`, whose 900px card would otherwise be cut off.
   */
  desktopWidth?: number;
}

/**
 * The one preview iframe both the Email Theme page (AC-EM030) and the
 * template editor (AC-EM031) use: a desktop (600px) / mobile (375px)
 * segmented toggle - a view TOGGLE, not navigation, so `TabsList
 * variant="default"` per DESIGN-LANGUAGE.md - over a sandboxed iframe fed by
 * `srcDoc`.
 */
export function EmailPreviewFrame({
  subject,
  html,
  isLoading,
  className,
  desktopWidth = WIDTH_BY_MODE.desktop,
}: EmailPreviewFrameProps) {
  const [mode, setMode] = useState<PreviewMode>('desktop');
  const width = mode === 'desktop' ? desktopWidth : WIDTH_BY_MODE[mode];

  return (
    <div className={cn('space-y-3', className)} data-slot="email-preview-frame">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">Subject</p>
          {isLoading && !subject ? (
            <Skeleton className="h-5 w-48" />
          ) : (
            <p className="truncate font-medium" title={subject ?? ''}>
              {subject || '-'}
            </p>
          )}
        </div>
        <Tabs value={mode} onValueChange={(value) => setMode(value as PreviewMode)}>
          <TabsList variant="default" size="sm" aria-label="Preview width">
            <TabsTrigger value="desktop">Desktop</TabsTrigger>
            <TabsTrigger value="mobile">Mobile</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>
      <div className="overflow-x-auto rounded-md border bg-muted/30 p-3">
        <iframe
          title="Email preview"
          sandbox=""
          data-mode={mode}
          width={width}
          className="mx-auto min-h-[640px] bg-white"
          style={{ width, maxWidth: '100%' }}
          srcDoc={html ?? ''}
        />
      </div>
    </div>
  );
}

export default EmailPreviewFrame;
