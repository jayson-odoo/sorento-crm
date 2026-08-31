/**
 * S9-02 - the accessibility guardrail inventory, checked against the source tree.
 *
 * Same reasoning as `PageHeader.inventory.test.ts` and `tabs.inventory.test.ts`:
 * what S9-02 asserts is a property of the WHOLE tree ("no icon button ships
 * without a name"), and a render test can only speak for the component it
 * mounted. A 307th icon-only `<Button size="icon">` added next month would pass
 * every component test in the repo and fail here.
 *
 * If you are adding an icon-only Button: pass `aria-label` (or render an
 * `sr-only` label as a child). If you are adding a `role="content"` anywhere,
 * don't - it is not a valid ARIA role and `<main>` already carries the
 * implicit one. If you are removing a focus ring alongside `outline-none`,
 * pair it with a `focus-visible:ring-*` (or a `focus-within:ring-*` on the
 * element's interactive wrapper) in the same change.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

const ROOTS = ['app', 'components'];

/**
 * Icon buttons the sweep does not reach, each for a reason recorded once here
 * rather than repeated at every site (mirrors the exemption style S4-03/S5-01
 * established for classes of files, not individual judgement calls):
 *
 * - `app/components/layouts/demo2` through `demo10` and their private
 *   `components/`: vendor Metronic shells. Only `demo1` is `Demo1Layout`, the
 *   layout `app/(protected)/layout.tsx` actually mounts; demo2-10 back routes
 *   nothing of ours renders.
 * - `app/(protected)/{account,auth,network,store-admin,store-client,public-profile}`:
 *   the same class of Metronic demo pages S5-01 exempted from the PageHeader
 *   sweep, for the same reason - every entry under these prefixes is
 *   commented out of `MENU_SIDEBAR` (`config/menu.config.tsx`), so none of
 *   them has a trail, and none of them is reachable from the app's own nav.
 * - `app/(protected)/components/**`: not a route at all - zero `page.tsx`
 *   anywhere under this tree, so Next.js cannot serve it regardless of what
 *   the sidebar says. Leftover starter-kit component gallery.
 * - the `app/components/partials/**` files that are demo-only transitively
 *   (only ever imported by the demo2-10 layouts, the account/network/
 *   public-profile pages above, or by nothing at all): cards barrel,
 *   `dialogs/search/search-mixed|search-users|search-docs` (the real Cmd+K
 *   palette is `search-dialog.tsx`, which does not import them),
 *   `topbar/chat-sheet`, `topbar/sheet-chat`, `topbar/dropdown-menu-notifications`
 *   (+ its `notifications/item-11`, `item-15`), `dialogs/share-profile/**`,
 *   `dropdown-menu/dropdown-menu-9`, `dialogs/give-award-dialog`,
 *   `common/avatar-input`. `topbar/notifications-sheet.tsx` and
 *   `topbar/notifications/NotificationItem.tsx` are NOT in this list: demo1's
 *   own header renders `<NotificationsSheet />`, so they are live.
 */
const ICON_BUTTON_EXEMPT_PATH_PREFIXES = [
  'app/components/layouts/demo2/',
  'app/components/layouts/demo3/',
  'app/components/layouts/demo4/',
  'app/components/layouts/demo5/',
  'app/components/layouts/demo6/',
  'app/components/layouts/demo7/',
  'app/components/layouts/demo8/',
  'app/components/layouts/demo9/',
  'app/components/layouts/demo10/',
  'app/(protected)/account/',
  'app/(protected)/auth/',
  'app/(protected)/network/',
  'app/(protected)/store-admin/',
  'app/(protected)/store-client/',
  'app/(protected)/public-profile/',
  'app/(protected)/components/',
  'app/components/partials/cards/',
  'app/components/partials/dialogs/search/search-mixed.tsx',
  'app/components/partials/dialogs/search/search-users.tsx',
  'app/components/partials/dialogs/search/search-docs.tsx',
  'app/components/partials/topbar/chat-sheet.tsx',
  'app/components/partials/topbar/sheet-chat.tsx',
  'app/components/partials/topbar/dropdown-menu-notifications.tsx',
  'app/components/partials/topbar/notifications/item-11.tsx',
  'app/components/partials/topbar/notifications/item-15.tsx',
  'app/components/partials/dialogs/share-profile/',
  'app/components/partials/dropdown-menu/dropdown-menu-9.tsx',
  'app/components/partials/dialogs/give-award-dialog.tsx',
  'app/components/partials/common/avatar-input.tsx',
];

function isIconButtonExempt(file: string): boolean {
  return ICON_BUTTON_EXEMPT_PATH_PREFIXES.some((prefix) => file.startsWith(prefix));
}

/** Every `.tsx`/`.ts` under the scanned roots, tests excluded. */
function sourceFiles(roots: string[]): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name === '.next') continue;
        walk(full);
      } else if (
        (entry.name.endsWith('.tsx') || entry.name.endsWith('.ts')) &&
        !entry.name.includes('.test.')
      ) {
        out.push(full);
      }
    }
  };
  for (const root of roots) walk(root);
  return out;
}

/**
 * The opening tag and children of every `<Button ...>...</Button>` in `src`,
 * brace/quote depth tracked so `className={cn('a', x && 'b')}` does not end
 * the tag early - same technique as `tabs.inventory.test.ts`'s `openTags`.
 */
function findButtons(src: string): { tag: string; children: string }[] {
  const out: { tag: string; children: string }[] = [];
  const opener = /<Button(?![A-Za-z])/g;
  let m: RegExpExecArray | null;
  while ((m = opener.exec(src))) {
    let i = m.index;
    let depth = 0;
    let quote: string | null = null;
    let tagEnd = -1;
    let selfClosing = false;
    while (i < src.length) {
      const c = src[i];
      if (quote) {
        if (c === '\\') i += 1;
        else if (c === quote) quote = null;
      } else if (c === '"' || c === "'" || c === '`') {
        quote = c;
      } else if (c === '{') {
        depth += 1;
      } else if (c === '}') {
        depth -= 1;
      } else if (c === '>' && depth === 0) {
        tagEnd = i + 1;
        selfClosing = src[i - 1] === '/';
        break;
      }
      i += 1;
    }
    if (tagEnd === -1) continue;
    const tag = src.slice(m.index, tagEnd);
    let children = '';
    if (!selfClosing) {
      // Find the matching </Button>, counting nested <Button opens.
      let nestDepth = 1;
      let j = tagEnd;
      const openRe = /<Button(?![A-Za-z])/g;
      const closeRe = /<\/Button>/g;
      openRe.lastIndex = j;
      closeRe.lastIndex = j;
      while (nestDepth > 0) {
        openRe.lastIndex = j;
        closeRe.lastIndex = j;
        const om = openRe.exec(src);
        const cm = closeRe.exec(src);
        if (!cm) break;
        if (om && om.index < cm.index) {
          nestDepth += 1;
          j = om.index + om[0].length;
        } else {
          nestDepth -= 1;
          j = cm.index + cm[0].length;
          if (nestDepth === 0) {
            children = src.slice(tagEnd, cm.index);
          }
        }
      }
    }
    out.push({ tag, children });
  }
  return out;
}

describe('Icon-button labels (S9-02)', () => {
  it('every mode="icon" / size="icon" Button has an accessible name', () => {
    const offenders: string[] = [];
    for (const file of sourceFiles(ROOTS)) {
      if (isIconButtonExempt(file)) continue;
      const src = fs.readFileSync(file, 'utf8');
      if (!src.includes('<Button')) continue;
      for (const { tag, children } of findButtons(src)) {
        if (!/mode="icon"|size="icon"/.test(tag)) continue;
        const hasAria = /aria-label|aria-labelledby/.test(tag);
        if (hasAria) continue;
        const hasSrOnly = children.includes('sr-only');
        if (hasSrOnly) continue;
        // asChild delegates the rendered element (and its aria-label) to its
        // single child - Radix Slot merges the Button's own props onto it.
        if (tag.includes('asChild') && children.includes('aria-label')) continue;
        // A numbered pager button (`data-grid-pagination.tsx`) renders its own
        // page number as visible text, so the number itself is the accessible
        // name - an `aria-label` would duplicate it under a different string
        // (VoiceOver reads "Page 4", `getByRole('button', { name: '4' })`
        // cannot find it). `aria-current="page"` marks the active one instead.
        if (tag.includes('aria-current')) continue;
        offenders.push(`${file}: ${tag.slice(0, 120).replace(/\s+/g, ' ')}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});

describe('role="content" removed everywhere (S9-02)', () => {
  it('no file sets role="content" (not a valid ARIA role; <main> already has an implicit one)', () => {
    const offenders: string[] = [];
    for (const file of sourceFiles(ROOTS)) {
      const src = fs.readFileSync(file, 'utf8');
      if (src.includes('role="content"')) offenders.push(file);
    }
    expect(offenders).toEqual([]);
  });
});

describe('Skip link (S9-02)', () => {
  it('the protected shell renders a skip link to #main, and #main exists', () => {
    const layout = fs.readFileSync('app/components/layouts/demo1/layout.tsx', 'utf8');
    expect(layout).toMatch(/href="#main"/);
    expect(layout).toMatch(/id="main"/);
  });
});

describe('IssuedKeyDialog no longer traps the keyboard (S9-02)', () => {
  it('Escape and click-outside are only blocked before the key is acknowledged', () => {
    const src = fs.readFileSync(
      'app/(protected)/integration-management/integrations/components/IssuedKeyDialog.tsx',
      'utf8',
    );
    // The old, unconditional guards must be gone...
    expect(src).not.toMatch(/onEscapeKeyDown=\{\(e\) => e\.preventDefault\(\)\}/);
    expect(src).not.toMatch(/onPointerDownOutside=\{\(e\) => e\.preventDefault\(\)\}/);
    // ...replaced by a guard that only fires while the key has not been copied.
    expect(src).toMatch(/onEscapeKeyDown=\{[\s\S]{0,80}!acknowledged[\s\S]{0,40}preventDefault/);
    expect(src).toMatch(
      /onPointerDownOutside=\{[\s\S]{0,80}!acknowledged[\s\S]{0,40}preventDefault/,
    );
  });
});

describe('Focus rings on the S9-02 outline-none sweep (S9-02)', () => {
  // Each site the sweep fixed, pinned so a later refactor cannot drop the ring
  // silently. `components/ui` primitives (button, tabs, input, input-otp,
  // datefield) already carried a ring before S9 and are not re-asserted here -
  // this list is the sites that had none.
  const RING_FIXED: { file: string; needle: string | RegExp }[] = [
    { file: 'app/components/common/AIAssistantBubble.tsx', needle: 'focus-visible:ring-2 focus-visible:ring-ring' },
    // The S7 sweep replaces this list's hand-rolled box with ListSearchInput,
    // whose Input primitive carries the ring itself - either form satisfies the pin.
    { file: 'app/(protected)/marketing-management/promotions/components/PromotionsList.tsx', needle: /focus-visible:ring-2 focus-visible:ring-ring|<ListSearchInput/ },
    { file: 'app/(protected)/system-management/health/components/HealthDashboard.tsx', needle: 'focus-visible:ring-2 focus-visible:ring-ring' },
    { file: 'components/common/find-in-text/FindBar.tsx', needle: 'focus-visible:ring-2 focus-visible:ring-ring' },
    { file: 'components/common/find-in-text/SearchableCode.tsx', needle: 'focus-visible:ring-2 focus-visible:ring-ring' },
    { file: 'components/common/conversation/ConversationSearchBar.tsx', needle: 'focus-visible:ring-2 focus-visible:ring-ring' },
    { file: 'components/common/AttachmentPreviewModal.tsx', needle: 'focus-visible:ring-2 focus-visible:ring-ring' },
    { file: 'components/ui/rich-text-editor.tsx', needle: 'focus-within:ring-2 focus-within:ring-ring' },
  ];

  it('each fixed site still carries its ring', () => {
    for (const { file, needle } of RING_FIXED) {
      const src = fs.readFileSync(file, 'utf8');
      if (typeof needle === 'string') expect(src, file).toContain(needle);
      else expect(src, file).toMatch(needle);
    }
  });
});
