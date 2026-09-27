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
];

const BANNED_SPECIFIERS = ['@/components/ui/select'];

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
    // Any OTHER select/combobox-shaped import is the failure mode this guard exists
    // for - named narrowly (not "anything with 'select' in it") so it does not also
    // flag `useSelect`-shaped React Query selectors or an unrelated `selectValue` var.
    const otherComboboxImports = [
      /from\s+['"]@radix-ui\/react-select['"]/,
      /from\s+['"]cmdk['"]/,
      /\bCommand(Item|List|Group|Empty)\b/,
    ];
    const offenders: string[] = [];
    for (const { rel, src } of readTouched()) {
      for (const pattern of otherComboboxImports) {
        if (pattern.test(src)) offenders.push(`${rel} matches ${pattern}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
