/**
 * TOGGLE-SELECTED - the selected option of every toggle is the primary colour, checked
 * against the source tree.
 *
 * The primitives are pinned by toggle.selected.test.tsx and tabs.selected.test.tsx. What a
 * render test cannot see is a call site that paints its own selected state: a className
 * override on a ToggleGroupItem / TabsTrigger, or a hand-rolled row of buttons. The owner's
 * screenshot (Contact Tag settings, 20 Oct 2026) showed what that costs - a selected option
 * one shade off the unselected ones.
 *
 * If you are adding a toggle: use ToggleGroup, a pill TabsList, or Button `variant="primary"`
 * for the selected option. Do not give the selected state its own fill.
 *
 * Plan: documentation/plans/design-system/PLAN-toggle-selected-20oct.md (the audit table is on
 * the PR).
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

const ROOTS = ['app', 'components'];

function sourceFiles(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name === '.next') continue;
        walk(full);
      } else if (entry.name.endsWith('.tsx') && !entry.name.includes('.test.')) {
        out.push(full);
      }
    }
  };
  for (const root of ROOTS) walk(root);
  return out;
}

const read = (file: string) => fs.readFileSync(file, 'utf8');

/**
 * The hand-rolled selected states the audit found off-primary, each with the class string it
 * used to select with and the one it selects with now.
 */
const HAND_ROLLED: Array<{ file: string; was: string | null; now: string }> = [
  {
    file: 'app/(protected)/sla-management/conversations/components/ConversationListPane.tsx',
    was: "'bg-background text-foreground shadow-sm'",
    now: "'bg-primary text-primary-foreground shadow-sm'",
  },
  {
    file: 'app/(protected)/sla-management/conversations/components/ConversationThreadPane.tsx',
    was: "'bg-background text-foreground shadow-sm'",
    now: "'bg-primary text-primary-foreground shadow-sm'",
  },
  {
    file: 'app/(protected)/sla-management/conversation-sla-tracking/components/TicketConversationPanel.tsx',
    was: "'bg-background text-foreground shadow-sm'",
    now: "'bg-primary text-primary-foreground shadow-sm'",
  },
  {
    file: 'app/(protected)/project-sales/[projectId]/components/TasksPanel.tsx',
    was: 'bg-muted text-foreground',
    now: 'bg-primary text-primary-foreground',
  },
  {
    file: 'components/upload-activity/UploadSessionRow.tsx',
    was: "'bg-background border border-border'",
    now: "'bg-primary text-primary-foreground'",
  },
  {
    file: 'app/(protected)/dealer-kit/tag-templates/components/InspectorPanel.tsx',
    was: "'border-primary bg-primary/10 text-primary'",
    now: "'border-primary bg-primary text-primary-foreground'",
  },
  {
    file: 'app/(protected)/system-management/ai-assistant/components/TraceView.tsx',
    was: "'border-primary bg-primary/10 text-primary'",
    now: "'border-primary bg-primary text-primary-foreground'",
  },
  {
    file: 'app/(protected)/dealer-kit/tag-templates/components/CanvasToolbar.tsx',
    was: "active && 'bg-accent text-accent-foreground'",
    now: "variant={active ? 'primary' : 'ghost'}",
  },
  {
    file: 'app/(protected)/resource-management/attachment-directories/components/AttachmentsInFolderPanel.tsx',
    was: "? 'secondary' : 'ghost'",
    now: "variant={viewMode === 'grid' ? 'primary' : 'ghost'}",
  },
  {
    file: 'components/common/pdf-viewer/PdfViewerImpl.tsx',
    was: null, // pressed showed no selected state at all
    now: "variant={searchOpen ? 'primary' : 'ghost'}",
  },
  {
    file: 'components/common/pdf-viewer/PdfViewerImpl.tsx',
    was: null,
    now: "variant={zoom === 'fit' ? 'primary' : 'ghost'}",
  },
  {
    file: 'app/(protected)/project-sales/[projectId]/quotation-documents/[documentId]/components/QuotationScopeTabs.tsx',
    was: 'has-[[data-state=active]]:bg-background',
    now: 'has-[[data-state=active]]:bg-primary',
  },
];

describe('every toggle selects in the primary colour', () => {
  const files = sourceFiles();

  it('no call site paints a selected ToggleGroupItem / Toggle anything but primary', () => {
    const offenders = files.flatMap((file) =>
      [...read(file).matchAll(/data-\[state=on\]:bg-(?!primary\b)[\w/.-]+/g)].map((m) => `${file}: ${m[0]}`),
    );
    expect(offenders).toEqual([]);
  });

  it('no TabsTrigger override paints the active pill a non-primary fill', () => {
    const offenders = files
      .filter((file) => file !== path.join('components', 'ui', 'tabs.tsx'))
      .flatMap((file) =>
        [...read(file).matchAll(/data-\[state=active\]:bg-(?!primary\b|transparent\b)[\w/.-]+/g)].map(
          (m) => `${file}: ${m[0]}`,
        ),
      );
    expect(offenders).toEqual([]);
  });

  for (const { file, was, now } of HAND_ROLLED) {
    it(`${path.basename(file)} selects with ${now}`, () => {
      const src = read(file);
      if (was) expect(src).not.toContain(was);
      expect(src).toContain(now);
    });
  }
});
