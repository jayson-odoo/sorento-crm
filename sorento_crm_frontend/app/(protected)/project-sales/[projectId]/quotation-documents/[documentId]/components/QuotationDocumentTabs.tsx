'use client';

import * as React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Layers, Mail, PenLine, ScrollText } from 'lucide-react';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';

/**
 * The document's own tabs, route-driven the way the users screen the client pointed at does it.
 *
 * Their words: "the cover letter, terms and conditions, signatures should be their own tab, so I
 * don't need to scroll down to see, see how we do for users list". So each part is a ROUTE, not a
 * local switch: the terms can be linked to, the back button walks back through them, and a
 * reopened tab lands where it was left.
 *
 * Each trigger is a real link rather than a button that pushes. Same navigation, but it can also
 * be opened in a new tab and read by a screen reader as somewhere to go.
 */
type TabDefinition = {
  key: string;
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  path: string;
};

export function quotationDocumentTabs(projectId: string, documentId: string): TabDefinition[] {
  const base = `/project-sales/${projectId}/quotation-documents/${documentId}`;
  return [
    { key: 'scopes', title: 'Scopes', icon: Layers, path: base },
    { key: 'cover-letter', title: 'Cover letter', icon: Mail, path: `${base}/cover-letter` },
    { key: 'terms', title: 'Terms', icon: ScrollText, path: `${base}/terms` },
    { key: 'signatures', title: 'Signatures', icon: PenLine, path: `${base}/signatures` },
  ];
}

export function QuotationDocumentTabs({
  projectId,
  documentId,
}: {
  projectId: string;
  documentId: string;
}) {
  const pathname = usePathname();
  const tabs = React.useMemo(
    () => quotationDocumentTabs(projectId, documentId),
    [projectId, documentId],
  );
  // The pathname is the single source of truth for which tab is open, so a browser Back lands on
  // the tab it came from instead of on a component still holding the old selection.
  const activeKey = tabs.find((tab) => tab.path === pathname)?.key ?? 'scopes';

  return (
    <Tabs value={activeKey} className="min-w-0">
      {/* The strip scrolls inside its own gutter. Without `min-w-0` the ancestors refuse to shrink
          below its content and the whole PAGE drags sideways at 375px, which is the one failure
          that makes a phone unusable. */}
      <div className="min-w-0 overflow-x-auto" data-testid="quotation-document-tab-strip">
        {/* `w-max` so the strip's underline runs the full length of the tabs rather than stopping
            at the viewport edge once they overflow. */}
        <TabsList variant="line" className="w-max">
          {tabs.map(({ key, title, icon: Icon, path }) => (
            <TabsTrigger key={key} value={key} asChild>
              <Link href={path}>
                <Icon className="size-4" aria-hidden />
                <span>{title}</span>
              </Link>
            </TabsTrigger>
          ))}
        </TabsList>
      </div>
    </Tabs>
  );
}
