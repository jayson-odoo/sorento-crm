/**
 * AC-MEM058 (round 3 UAC, merged 5b110df8, owner ruling 27 Sep 2026 "need final
 * mockup"): every single-select on the chatbot memory screens this plan touches is
 * `SearchableSelect` (`@/components/common/SearchableSelect`) and every multi-select
 * is `SearchableMultiSelect` (`@/components/common/SearchableMultiSelect`) - no
 * `@/components/ui/select`, no raw `<select`, no `CommandInput` anywhere in the
 * touched files.
 *
 * The three named files are `ContactChatbotSection.tsx`, `MemorySettingsCard.tsx`
 * and `TurnDetailDrawer.tsx` (this plan's own contact / settings / turn-drawer
 * screens). A new contact "Chatbot" tab page, if the coder splits the section into
 * its own route file, does not exist as a separate file today - there is nothing
 * yet to add to this list; a future one lands beside `ContactChatbotSection.tsx`
 * and belongs in `TOUCHED_FILES` below when it appears (the guard cannot discover
 * a file that has not been written).
 *
 * Modelled on `components/ui/deleted-motion-components.guard.test.ts`'s resolved-
 * import scan (never a bare substring match, which would also flag an unrelated
 * `avatar-group`-shaped false positive) and `dismissVerb.guard.test.ts`'s repo-root
 * anchoring so the guard does not depend on the cwd it runs from.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const ROOT = path.resolve(__dirname, '..', '..', '..', '..', '..', '..');

const TOUCHED_FILES = [
  'app/(protected)/user-management/contacts/[id]/components/ContactChatbotSection.tsx',
  'app/(protected)/user-management/settings/chatbot/components/MemorySettingsCard.tsx',
  'app/(protected)/system-management/chat-history/components/TurnDetailDrawer.tsx',
  // The contact "Chatbot" tab page: it renders `ContactChatbotSection` and is a
  // touched file of this plan (round 3), even though it carries no select itself
  // today - a future select added straight to this file, rather than the section
  // it renders, would otherwise slip past this guard entirely.
  'app/(protected)/user-management/contacts/[id]/chatbot/page.tsx',
];

const BANNED_SPECIFIERS = ['@/components/ui/select'];

// Any OTHER select/combobox-shaped import is the failure mode this guard exists
// for - named narrowly (not "anything with 'select' in it") so it does not also
// flag `useSelect`-shaped React Query selectors or an unrelated `selectValue` var.
// Module-scoped (review finding S20, PR #1304) so the synthetic-fixture test below
// can prove each pattern actually fires, not just that the real touched files pass.
const OTHER_COMBOBOX_IMPORTS = [
  /from\s+['"]@radix-ui\/react-select['"]/,
  /from\s+['"]cmdk['"]/,
  // The umbrella `radix-ui` package (the repo's own precedent elsewhere) re-exports
  // `Select` as a named import - `import { Select } from 'radix-ui'` passed this
  // guard before this fix, since neither banned specifier above names it.
  /import\s*\{[^}]*\bSelect\b[^}]*\}\s*from\s+['"]radix-ui['"]/,
  // `Command(Item|List|Group|Empty)` alone missed a BARE `Command` import
  // (`import { Command } from 'cmdk'` or `.../ui/command`) - the combobox root
  // itself, not one of its named children.
  /\bCommand(Item|List|Group|Empty)?\b/,
];

function readTouched(): { rel: string; src: string }[] {
  return TOUCHED_FILES.map((rel) => ({ rel, src: fs.readFileSync(path.join(ROOT, rel), 'utf8') }));
}

describe('AC-MEM058: chatbot memory screens use only SearchableSelect / SearchableMultiSelect', () => {
  it('finds every touched file this guard is supposed to police', () => {
    for (const rel of TOUCHED_FILES) {
      expect(fs.existsSync(path.join(ROOT, rel)), `missing: ${rel}`).toBe(true);
    }
  });

  it('imports no @/components/ui/select anywhere', () => {
    const offenders: string[] = [];
    for (const { rel, src } of readTouched()) {
      for (const banned of BANNED_SPECIFIERS) {
        if (src.includes(banned)) offenders.push(`${rel} imports ${banned}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('renders no raw <select> element', () => {
    const offenders: string[] = [];
    for (const { rel, src } of readTouched()) {
      if (/<select[\s>]/.test(src)) offenders.push(rel);
    }
    expect(offenders).toEqual([]);
  });

  it('uses no CommandInput anywhere', () => {
    const offenders: string[] = [];
    for (const { rel, src } of readTouched()) {
      if (src.includes('CommandInput')) offenders.push(rel);
    }
    expect(offenders).toEqual([]);
  });

  it('every single-select import is SearchableSelect and every multi-select is SearchableMultiSelect', () => {
    const offenders: string[] = [];
    for (const { rel, src } of readTouched()) {
      for (const pattern of OTHER_COMBOBOX_IMPORTS) {
        if (pattern.test(src)) offenders.push(`${rel} matches ${pattern}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  // S20 (review finding, PR #1304): the matcher above only proves the REAL touched
  // files are clean today - it never proved the patterns themselves would catch a
  // violation. `import { Select } from 'radix-ui'` (the umbrella package the repo
  // uses elsewhere) and a bare `import { Command } from 'cmdk'` both slipped past
  // the pre-fix pattern list silently; this drives the SAME matcher over synthetic
  // fixture source so a future narrowing of the patterns is caught here first.
  it("the matcher itself catches a synthetic 'import { Select } from radix-ui' violation", () => {
    const fixture = "import { Select } from 'radix-ui';\n";
    const hit = OTHER_COMBOBOX_IMPORTS.some((pattern) => pattern.test(fixture));
    expect(hit).toBe(true);
  });

  it("the matcher itself catches a synthetic bare 'import { Command }' violation", () => {
    // From the repo's own command component path, not `cmdk` itself - so this only
    // passes because of the bare `Command` pattern, never the `from 'cmdk'` one.
    const fixture = "import { Command } from '@/components/ui/command';\n";
    const hit = OTHER_COMBOBOX_IMPORTS.some((pattern) => pattern.test(fixture));
    expect(hit).toBe(true);
  });
});
