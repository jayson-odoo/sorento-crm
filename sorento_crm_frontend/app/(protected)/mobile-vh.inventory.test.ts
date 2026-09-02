/**
 * M6-02 / M6-03 - the fixed-viewport-unit sweep.
 *
 * `100vh` (and its Tailwind shorthands `h-screen` / `min-h-screen`) is taller
 * than the visible viewport on mobile Safari, whose address bar and toolbar
 * come and go: a surface sized off it has its bottom edge sitting under
 * chrome the reader cannot scroll past. `dvh` (dynamic viewport height)
 * tracks the ACTUAL visible area instead.
 *
 * Three named sites were the M6 targets - `notifications-sheet.tsx`,
 * `AIAssistantBubble.tsx`, `ConversationsInbox.tsx` - and are converted. The
 * other 33 occurrences (24 files) from the 2 Sep audit are allowlisted with a
 * reason so this floor does not silently widen; each is due its own M6
 * follow-up rather than blocking this round.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

const PATTERN = /100vh|(?<![\w-])h-screen(?![\w-])|min-h-screen/;

/** file -> why it is still on `vh`/`-screen`, not yet converted. */
const ALLOWLIST = new Map<string, string>([
  ['app/unsubscribe/daily-sla-summary/page.tsx', 'M6 follow-up: unauthenticated one-off page'],
  ['app/components/layouts/demo10/components/sidebar-menu.tsx', 'M6 follow-up: unused demo shell'],
  ['app/components/layouts/demo3/components/sidebar.tsx', 'M6 follow-up: unused demo shell'],
  ['app/components/layouts/demo4/components/sidebar-secondary.tsx', 'M6 follow-up: unused demo shell'],
  ['app/components/layouts/demo6/components/sidebar-menu.tsx', 'M6 follow-up: unused demo shell'],
  ['app/components/layouts/demo8/components/sidebar-menu.tsx', 'M6 follow-up: unused demo shell'],
  ['app/components/layouts/demo1/components/sidebar-menu.tsx', 'M6 follow-up: the active shell, not an M6 target'],
  [
    'app/(protected)/forms-management/forms/[id]/builder/components/FormBuilder.tsx',
    'M6 follow-up: desktop-only builder canvas',
  ],
  [
    'app/(protected)/project-sales/[projectId]/components/POIntakeAnnotationsGrid.tsx',
    'M6 follow-up: desktop-only intake grid',
  ],
  [
    'app/(protected)/project-sales/[projectId]/components/POIntakeConfirmClient.tsx',
    'M6 follow-up: desktop-only intake flow',
  ],
  [
    'app/(protected)/project-sales/[projectId]/components/POIntakeLinesGrid.tsx',
    'M6 follow-up: desktop-only intake grid',
  ],
  [
    'app/(protected)/resource-management/attachment-directories/page.tsx',
    'M6 follow-up: desktop-only file browser',
  ],
  [
    'app/(protected)/store-admin/components/create-shipping-label-sheet/sheet.tsx',
    'M6 follow-up: internal admin sheet',
  ],
  ['app/(public)/c/[company]/[slug]/page.tsx', 'M6 follow-up: public catalogue landing'],
  ['app/(auth)/portal/components/PortalVerifyCard.tsx', 'M6 follow-up: portal auth screen'],
  ['app/(auth)/portal/components/SubmissionForm.tsx', 'M6 follow-up: portal form shell'],
  ['app/(auth)/view/stock-inquiry/page.tsx', 'M6 follow-up: emailed read-only view'],
  ['app/(auth)/view/complaint/page.tsx', 'M6 follow-up: emailed read-only view'],
  ['app/(auth)/view/request/page.tsx', 'M6 follow-up: emailed read-only view'],
  ['app/(auth)/approval/page.tsx', 'M6 follow-up: emailed approval screen'],
  ['components/ideas/IdeationEmbed.tsx', 'M6 follow-up: embedded iframe host'],
  ['components/my-downloads/MyDownloadsDrawer.tsx', 'M6 follow-up: desktop-oriented drawer'],
  [
    'components/ui/grid-background.tsx',
    'M6 follow-up: one of the 16 zero-importer motion components M1 deletes',
  ],
  ['components/upload-activity/UploadActivityDrawer.tsx', 'M6 follow-up: desktop-oriented drawer'],
]);

const CONVERTED_M6_SITES = [
  'app/components/partials/topbar/notifications-sheet.tsx',
  'app/components/common/AIAssistantBubble.tsx',
  'app/(protected)/sla-management/conversations/components/ConversationsInbox.tsx',
];

function sourceFiles(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    if (!fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name === '.next') continue;
        walk(full);
      } else if (/\.(ts|tsx)$/.test(entry.name) && !entry.name.includes('.test.')) {
        out.push(full);
      }
    }
  };
  walk('app');
  walk('components');
  return out;
}

describe('fixed viewport-height sweep (M6-02 / M6-03)', () => {
  it('every 100vh / h-screen / min-h-screen site is either converted or allowlisted with a reason', () => {
    const offenders: string[] = [];
    for (const file of sourceFiles()) {
      if (ALLOWLIST.has(file)) continue;
      const src = fs.readFileSync(file, 'utf8');
      if (PATTERN.test(src)) offenders.push(file);
    }
    expect(offenders).toEqual([]);
  });

  it('the three named M6 sites use dvh, not vh', () => {
    for (const file of CONVERTED_M6_SITES) {
      const src = fs.readFileSync(file, 'utf8');
      expect(src, file).not.toMatch(PATTERN);
      expect(src, file).toMatch(/dvh/);
    }
  });

  it('the allowlist matches the 2 Sep audit baseline (33 lines, 24 files)', () => {
    let matchingLines = 0;
    for (const file of ALLOWLIST.keys()) {
      const lines = fs.readFileSync(file, 'utf8').split('\n');
      matchingLines += lines.filter((line) => PATTERN.test(line)).length;
    }
    expect(ALLOWLIST.size).toBe(24);
    expect(matchingLines).toBe(33);
  });
});
