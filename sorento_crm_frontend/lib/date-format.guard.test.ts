/**
 * DATE-FORMAT-UNIFY guard (owner, 4 Nov 2026: "all the dates need to use dd/mm/yyyy format like a
 * standardized format across the system").
 *
 * Every date a person reads goes through the shared helpers in `lib/helpers.ts`
 * (`formatDateInMalaysia`, `formatDateTimeInMalaysia`, `formatDateRange` and the wrappers beside
 * them). A direct `toLocaleDateString`, `Intl.DateTimeFormat`, date-valued `toLocaleString` or a
 * date-fns display pattern anywhere else renders in the browser's locale or in a private style,
 * which is how one screen came to read `1 Jan 2026` beside a header reading `25/10/2026`.
 *
 * Something that is not a calendar date (a month bucket like `Dec 2026`, a chat day pill, a
 * timezone name) is allowed in place: put `date-format-ok: <reason>` in a comment on the SAME line
 * (or, for a month-name table, anywhere in the file), or list the whole file on ALLOWED with its
 * reason. Anything else is a new straggler: use the helper.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect } from 'vitest';

const root = path.resolve(__dirname, '..');

/** file -> why it may format a date itself. Keep this list short and every reason specific. */
export const ALLOWED: Record<string, string> = {
  'lib/helpers.ts': 'the shared date helpers themselves',
  'i18n/timezones.ts': 'formats a timezone NAME for the timezone select, not a date',
};

/** Patterns that render a date outside the helper. Each regex runs per source line. */
const FORBIDDEN: { name: string; re: RegExp }[] = [
  { name: 'toLocaleDateString', re: /\.toLocaleDateString\(/ },
  { name: 'toLocaleTimeString', re: /\.toLocaleTimeString\(/ },
  { name: 'Intl.DateTimeFormat', re: /\bIntl\.DateTimeFormat\(/ },
  // A Date's toLocaleString: a `new Date(...)` receiver, or date/time options in the call.
  { name: 'Date#toLocaleString', re: /Date\([^)]*\)\)?\.toLocaleString\(/ },
  { name: 'Date#toLocaleString', re: /\b(d|date|dt|when|ts|cursor)\.toLocaleString\(/ },
  {
    name: 'toLocaleString with date options',
    re: /\.toLocaleString\([^)]*(dateStyle|timeStyle|month:|weekday:|day:)/,
  },
  // date-fns display patterns. Wire/bucket keys (`yyyy-MM-dd`, `yyyy-MM`, `yyyy`) stay legal.
  {
    name: 'date-fns display format',
    re: /\bformat\([^'"`\n]*,\s*['"](?!yyyy-MM-dd['"]|yyyy-MM['"]|yyyy['"])[^'"]*[dMyLEHhP][^'"]*['"]/,
  },
];

function sourceFiles(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    const abs = path.join(root, dir);
    if (!fs.existsSync(abs)) return;
    for (const entry of fs.readdirSync(abs, { withFileTypes: true })) {
      const rel = path.posix.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name === '.next') continue;
        walk(rel);
      } else if (/\.tsx?$/.test(entry.name) && !/\.(test|spec)\.tsx?$/.test(entry.name)) {
        out.push(rel);
      }
    }
  };
  for (const dir of ['app', 'components', 'lib', 'hooks', 'services', 'providers', 'i18n', 'config']) {
    walk(dir);
  }
  return out;
}

/** Lines that are code, not comments: a comment that names the forbidden call is fine. */
function codeLines(src: string): { line: number; text: string }[] {
  const out: { line: number; text: string }[] = [];
  let inBlock = false;
  src.split('\n').forEach((raw, i) => {
    let text = raw;
    if (inBlock) {
      const end = text.indexOf('*/');
      if (end === -1) return;
      text = text.slice(end + 2);
      inBlock = false;
    }
    text = text.replace(/\/\*.*?\*\//g, '');
    const open = text.indexOf('/*');
    if (open !== -1) {
      text = text.slice(0, open);
      inBlock = true;
    }
    const trimmed = text.trim();
    if (trimmed.startsWith('//')) return;
    out.push({ line: i + 1, text: text.replace(/\s\/\/.*$/, '') });
  });
  return out;
}

export function findOffenders(files: string[]): string[] {
  const offenders: string[] = [];
  for (const file of files) {
    if (ALLOWED[file]) continue;
    const src = fs.readFileSync(path.join(root, file), 'utf8');
    // A hand-rolled month-name table is a private date style (`1 Jan 2026`), on one line or many.
    if (/\[\s*['"]Jan['"],\s*['"]Feb['"]/.test(src) && !/date-format-ok: \S/.test(src)) {
      offenders.push(`${file} month-name table`);
    }
    const raw = src.split('\n');
    for (const { line, text } of codeLines(src)) {
      if (/date-format-ok: \S/.test(raw[line - 1])) continue;
      for (const { name, re } of FORBIDDEN) {
        if (re.test(text)) offenders.push(`${file}:${line} ${name}`);
      }
    }
  }
  return offenders;
}

describe('DATE-FORMAT-UNIFY: no date is formatted outside the shared helpers', () => {
  it('every allow-listed file still exists (a stale entry hides nothing and should go)', () => {
    for (const file of Object.keys(ALLOWED)) {
      expect(fs.existsSync(path.join(root, file)), file).toBe(true);
    }
  });

  it('no source file formats a date directly', () => {
    expect(findOffenders(sourceFiles())).toEqual([]);
  });
});
