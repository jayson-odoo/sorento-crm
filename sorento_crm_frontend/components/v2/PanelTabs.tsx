'use client';

import { useId, useState, type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { useIsPhone } from './shell/useViewport';

export interface Panel {
  id: string;
  label: string;
  count?: number;
  content: ReactNode;
}

/**
 * Side-by-side panels above 720 px, browser-style tabs at 720 px and below (E-6, playbook P7).
 * The first panel is the main one and the default tab. Inactive tab panels stay mounted (hidden),
 * so each keeps its DOM, scroll position and state across switches.
 */
export function PanelTabs({ panels }: { panels: Panel[] }) {
  const isPhone = useIsPhone();
  const base = useId();
  const [activeId, setActiveId] = useState<string | null>(null);
  const active = panels.find((p) => p.id === activeId) ?? panels[0];

  if (panels.length <= 1 || !isPhone) {
    return (
      <div className="flex min-w-0 gap-4">
        {panels.map((panel, i) => (
          <section
            key={panel.id}
            aria-label={panel.label}
            className={cn('min-w-0 rounded-lg border bg-card p-4', i === 0 ? 'flex-[2]' : 'flex-1')}
          >
            {panel.content}
          </section>
        ))}
      </div>
    );
  }

  const tabId = (id: string) => `${base}-tab-${id}`;
  const panelId = (id: string) => `${base}-panel-${id}`;

  return (
    <div className="flex min-w-0 flex-col">
      <div role="tablist" className="flex gap-1 overflow-x-auto border-b px-1">
        {panels.map((panel) => {
          const selected = panel.id === active.id;
          return (
            <button
              key={panel.id}
              id={tabId(panel.id)}
              role="tab"
              type="button"
              aria-selected={selected}
              aria-controls={panelId(panel.id)}
              tabIndex={selected ? 0 : -1}
              onClick={() => setActiveId(panel.id)}
              className={cn(
                'inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-t-lg border border-b-0 px-3 py-1.5 text-sm font-medium pointer-coarse:min-h-11',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                selected
                  ? 'relative -mb-px border-border bg-card text-foreground'
                  : 'border-transparent bg-muted/50 text-muted-foreground hover:text-foreground',
              )}
            >
              <span>{panel.label}</span>
              {panel.count !== undefined && (
                <>
                  {' '}
                  <span className="text-xs text-muted-foreground">{panel.count}</span>
                </>
              )}
            </button>
          );
        })}
      </div>
      {panels.map((panel) => (
        <div
          key={panel.id}
          id={panelId(panel.id)}
          role="tabpanel"
          aria-labelledby={tabId(panel.id)}
          hidden={panel.id !== active.id}
          className="max-h-[calc(100dvh-12rem)] min-w-0 overflow-y-auto rounded-b-lg border border-t-0 bg-card p-4"
        >
          {panel.content}
        </div>
      ))}
    </div>
  );
}
