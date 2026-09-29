/**
 * AC-SR-05 (#1288, Lane A) - every single-select on the cost price screens is
 * `SearchableSelect` and every multi-select is `SearchableMultiSelect`.
 *
 * Source scan, not a render test, same reasoning as `components/ui/raw-table.inventory.test.ts`:
 * "no raw `<select>` and no `@/components/ui/select` import anywhere in this feature" is a
 * property of the whole tree, and a render test can only speak for the one screen it mounted.
 * Scope is the three surfaces the plan (section 8.5) and the captain's test list name: the
 * cost price uploads feature directory, the supplier record's Prices tab, and the product
 * record's Suppliers tab.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

const FRONTEND_ROOT = path.resolve(__dirname, '..', '..', '..', '..');

const ROOTS = [
  path.resolve(__dirname), // this directory: app/(protected)/procurement-management/cost-price-uploads
  path.resolve(
    __dirname,
    '..',
    'suppliers',
    '[id]',
    'components',
    'SupplierPricesTab.tsx',
  ),
  path.resolve(
    __dirname,
    '..',
    '..',
    'master-data-management',
    'products',
    '[id]',
    'components',
    'ProductSuppliersTab.tsx',
  ),
];

function sourceFiles(): string[] {
  const out: string[] = [];
  const visit = (target: string) => {
    const stat = fs.statSync(target);
    if (stat.isFile()) {
      if (/\.(tsx|ts)$/.test(target) && !/\.test\.(tsx|ts)$/.test(target)) out.push(target);
      return;
    }
    for (const entry of fs.readdirSync(target, { withFileTypes: true })) {
      if (entry.name === 'node_modules') continue;
      const full = path.join(target, entry.name);
      const s = fs.statSync(full);
      if (s.isDirectory()) visit(full);
      else if (/\.(tsx|ts)$/.test(full) && !/\.test\.(tsx|ts)$/.test(full)) out.push(full);
    }
  };
  for (const root of ROOTS) visit(root);
  return out;
}

function rel(file: string): string {
  return path.relative(FRONTEND_ROOT, file).split(path.sep).join('/');
}

describe('AC-SR-05: cost price screens use only SearchableSelect / SearchableMultiSelect', () => {
  const files = sourceFiles();

  it('found at least one source file to scan (the walk itself is not vacuous)', () => {
    expect(files.length).toBeGreaterThan(0);
  });

  it('imports no @/components/ui/select', () => {
    const offenders = files.filter((f) => /['"]@\/components\/ui\/select['"]/.test(fs.readFileSync(f, 'utf8')));
    expect(offenders.map(rel)).toEqual([]);
  });

  it('renders no raw <select> element', () => {
    const offenders = files.filter((f) => /<select[\s>]/i.test(fs.readFileSync(f, 'utf8')));
    expect(offenders.map(rel)).toEqual([]);
  });

  it('every dropdown import is SearchableSelect or SearchableMultiSelect', () => {
    // A "dropdown component" here means anything under components/common whose name ends
    // in Select, other than the two allowed ones - so a future stand-in (a bespoke
    // `ProductPicker`, a copy-pasted `Combobox`) fails this the same way a native <select>
    // does, per the captain's brief ("fails on a native <select> OR ANOTHER DROPDOWN
    // COMPONENT").
    const importPattern = /from ['"]@\/components\/common\/(\w*Select\w*)['"]/g;
    const allowed = new Set(['SearchableSelect', 'SearchableMultiSelect']);
    const offenders: string[] = [];
    for (const file of files) {
      const text = fs.readFileSync(file, 'utf8');
      let m: RegExpExecArray | null;
      importPattern.lastIndex = 0;
      while ((m = importPattern.exec(text))) {
        if (!allowed.has(m[1])) offenders.push(`${rel(file)} -> ${m[1]}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
