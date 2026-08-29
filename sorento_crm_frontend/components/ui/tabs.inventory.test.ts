/**
 * S4-01 - the tab inventory, checked against the source tree.
 *
 * S1 made `line` the default variant and gave the list its own horizontal
 * scroller, then pinned every strip that had no explicit variant with
 * `variant="default"` so nothing migrated silently. S4 reconciles that pin list:
 * 19 strips become the Users style (line, icon + label), the segmented
 * two-and-three-option switches keep their pill and keep the pin.
 *
 * The reason this is a source scan and not a render test: what S4-01 asserts is
 * a property of the WHOLE tree ("no `grid grid-cols-N` TabsList remains"), and a
 * render test can only speak for the component it mounted. A twentieth strip
 * added next month with `grid w-full grid-cols-4` would pass every component
 * test in the repo and fail here, which is the point - the mechanical class is
 * what squeezed five pills into overlapping stubs at 375 in the first place.
 *
 * If you are adding a tab strip: do not pass `grid`; the list scrolls. If it is
 * a two- or three-option segmented switch, pin it `variant="default"` and add it
 * to `SEGMENTED_KEEPERS`; otherwise give each trigger an icon and leave the
 * variant alone.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

/** Roots scanned. `components/` is included: two keepers live there. */
const ROOTS = ['app', 'components'];

/**
 * The 18 files holding the 19 migrated strips (AttachmentDetailModal has two:
 * the linkage strip and the details/integration strip inside its preview card).
 */
const LINE_MIGRATED = [
  'app/(protected)/master-data-management/products/components/ProductForm.tsx',
  'app/(protected)/order-management/orders/components/OrderForm.tsx',
  'app/(protected)/order-management/orders/components/OrderDetail.tsx',
  'app/(protected)/inventory-management/warehouses/components/WarehouseForm.tsx',
  'app/(protected)/inventory-management/warehouses/[id]/page.tsx',
  'app/(protected)/marketing-management/promotions/components/PromotionForm.tsx',
  'app/(protected)/workflow-forms-management/components/WorkflowFormBuilder.tsx',
  'app/(protected)/resource-management/attachments/components/AttachmentDetail.tsx',
  'app/(protected)/resource-management/attachments/components/AttachmentDetailModal.tsx',
  'app/(protected)/sla-management/_shared/FormSLATrackerDetail.tsx',
  'app/(protected)/sla-management/conversation-sla-tracking/components/ConversationSLATrackingDetail.tsx',
  'app/(protected)/master-data-management/product-specifications/components/SpecWorkbench.tsx',
  'app/(protected)/scm/simulation/components/SimulationView.tsx',
  'app/(protected)/scm/policies/components/PolicyConfigView.tsx',
  'app/(protected)/user-management/settings/layout.tsx',
  'app/(protected)/project-sales/[projectId]/components/ProjectDetailClient.tsx',
  'app/(protected)/project-sales/leads/[leadId]/components/LeadDetailClient.tsx',
  'components/reports/ReportPage.tsx',
];

/**
 * The strips that stay pills: each is a two- or three-option segmented switch
 * where the underline reads as navigation the user does not have (D9).
 */
const SEGMENTED_KEEPERS = [
  'app/(protected)/system-management/companies/components/CompanyAccessDialog.tsx',
  'app/(protected)/scm/reorder/components/PlanRowDialogs.tsx',
  'app/(protected)/scm/components/PlanRowDialog.tsx',
  'app/(protected)/dealer-kit/design/components/RoomDesigner.tsx',
  'app/(protected)/dealer-kit/components/ProductPickerDialog.tsx',
  'app/(protected)/dealer-kit/components/PageEditor.tsx',
  'app/(protected)/project-sales/[projectId]/quotation-documents/[documentId]/components/QuotationScopeTabs.tsx',
  'app/(auth)/portal/components/PeriodPicker.tsx',
  'components/common/ActivitiesNotesPanel/index.tsx',
  'components/common/ActivitiesNotesPanel/EntityActivitiesLayout.tsx',
];

/** Every `.tsx` under the scanned roots, tests excluded. */
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

/**
 * The open tags of one JSX element, as source text.
 *
 * A regex to the next `>` is wrong here: `className={cn('a', x && 'b')}` closes
 * no tag, and several strips carry exactly that. So brace depth is tracked and
 * quotes are skipped, and the tag ends at the first `>` at depth zero.
 */
function openTags(src: string, name: string): string[] {
  const found: string[] = [];
  const opener = new RegExp(`<${name}(?![A-Za-z])`, 'g');
  let m: RegExpExecArray | null;
  while ((m = opener.exec(src))) {
    let i = m.index;
    let depth = 0;
    let quote: string | null = null;
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
        found.push(src.slice(m.index, i + 1));
        break;
      }
      i += 1;
    }
  }
  return found;
}

describe('Tabs inventory (S4-01)', () => {
  it('S4-01: no TabsList lays its triggers out on a CSS grid', () => {
    const offenders: string[] = [];
    for (const file of sourceFiles()) {
      const src = fs.readFileSync(file, 'utf8');
      if (!src.includes('<TabsList')) continue;
      for (const tag of openTags(src, 'TabsList')) {
        if (/\bgrid-cols-/.test(tag)) offenders.push(file);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('S4-01: the 19 migrated strips carry no pill pin', () => {
    const offenders: string[] = [];
    for (const file of LINE_MIGRATED) {
      const src = fs.readFileSync(file, 'utf8');
      for (const tag of openTags(src, 'TabsList')) {
        if (tag.includes('variant="default"')) offenders.push(file);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('S4-01: every migrated file renders a Tabs strip', () => {
    // A file that lost its `<TabsList` entirely would pass the two checks above
    // for the wrong reason. ProjectDetailClient and LeadDetailClient are here
    // because they had no Tabs at all before S4 - they hand-rolled a `<nav>` of
    // buttons, which is the thing this asserts is gone.
    for (const file of LINE_MIGRATED) {
      const src = fs.readFileSync(file, 'utf8');
      expect(openTags(src, 'TabsList').length, file).toBeGreaterThan(0);
    }
  });

  it('S4-01: every trigger in a migrated strip has an icon beside its label', () => {
    // The Users style is icon + label. A trigger is a component element
    // (`<Icon />`, `<History />`) somewhere inside the trigger body; a bare
    // label is what this rejects.
    const offenders: string[] = [];
    for (const file of LINE_MIGRATED) {
      const src = fs.readFileSync(file, 'utf8');
      const triggers = src.split('<TabsTrigger').slice(1);
      for (const chunk of triggers) {
        const end = chunk.indexOf('</TabsTrigger>');
        const body = end === -1 ? chunk.slice(0, 400) : chunk.slice(0, end);
        if (!/<[A-Z][A-Za-z0-9]*\s*\/?>/.test(body)) {
          offenders.push(`${file}: ${body.slice(0, 60).replace(/\s+/g, ' ')}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it('S4-01: the segmented keepers still pin the pill variant', () => {
    for (const file of SEGMENTED_KEEPERS) {
      const src = fs.readFileSync(file, 'utf8');
      const tags = openTags(src, 'TabsList');
      expect(tags.length, file).toBeGreaterThan(0);
      for (const tag of tags) {
        expect(tag, file).toContain('variant="default"');
      }
    }
  });

  it('S4-01: no strip outside the keepers pins the pill variant', () => {
    const keepers = new Set(SEGMENTED_KEEPERS);
    const offenders: string[] = [];
    for (const file of sourceFiles()) {
      if (keepers.has(file)) continue;
      const src = fs.readFileSync(file, 'utf8');
      if (!src.includes('<TabsList')) continue;
      for (const tag of openTags(src, 'TabsList')) {
        if (tag.includes('variant="default"')) offenders.push(file);
      }
    }
    expect(offenders).toEqual([]);
  });
});
