/**
 * Guard (CLIENT-ERROR-REPORT): code that runs before any page can render must not
 * use APIs that throw in Safari. A throw there is "The app could not start" on every
 * page, sign-in included.
 * - Root providers and shell: no `structuredClone` (absent before Safari 15.4), and
 *   any storage access inside a `try` block.
 * - Whole app: no `localStorage` / `sessionStorage` reference outside `lib/storage.ts`
 *   (Safari with storage blocked throws SecurityError on the bare reference, and the
 *   crew pass found one in the protected shell that the root-file rule did not reach).
 *   `lib/chunk-load-error.ts` is the one exception: its reload guard needs real storage.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const ROOT = path.resolve(__dirname, '..');

function rootFiles(): string[] {
  const providers = fs
    .readdirSync(path.join(ROOT, 'providers'))
    .filter((f) => /\.tsx?$/.test(f) && !/\.test\.tsx?$/.test(f))
    .map((f) => path.join('providers', f));
  return [
    ...providers,
    'components/ClientProviders.tsx',
    'components/DynamicClientProviders.tsx',
    'app/layout.tsx',
    'app/(protected)/layout.tsx',
    'app/global-error.tsx',
    'lib/impersonation-store.ts',
    'lib/chunk-load-error.ts',
    'lib/client-error-report.ts',
  ];
}

/** Source with comments and string literals blanked out, offsets preserved. */
function codeOnly(src: string): string {
  return src.replace(
    /\/\*[\s\S]*?\*\/|\/\/[^\n]*|'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*"|`(?:\\.|[^`\\])*`/g,
    (m) => m.replace(/[^\n]/g, ' '),
  );
}

function insideTry(code: string, at: number): boolean {
  const tryRe = /\btry\s*\{/g;
  let m: RegExpExecArray | null;
  while ((m = tryRe.exec(code)) && m.index < at) {
    let depth = 0;
    for (let i = m.index + m[0].length - 1; i < at; i++) {
      if (code[i] === '{') depth++;
      else if (code[i] === '}') depth--;
    }
    if (depth > 0) return true;
  }
  return false;
}

export function violations(file: string, src: string): string[] {
  const code = codeOnly(src);
  const out: string[] = [];
  for (const m of code.matchAll(/\bstructuredClone\b/g)) out.push(`${file}: structuredClone at ${m.index}`);
  for (const m of code.matchAll(/\b(localStorage|sessionStorage)\b/g)) {
    if (!insideTry(code, m.index!)) out.push(`${file}: ${m[1]} outside try at ${m.index}`);
  }
  return out;
}

describe('root providers are safe in old and locked-down Safari', () => {
  it('the guard itself catches both patterns', () => {
    expect(violations('x', 'const a = structuredClone(b);')).toHaveLength(1);
    expect(violations('x', 'Object.keys(localStorage)')).toHaveLength(1);
    expect(violations('x', 'try { localStorage.getItem("k") } catch {}')).toHaveLength(0);
    expect(violations('x', "// localStorage\nconst o = ['localStorage'];")).toHaveLength(0);
  });

  it.each(rootFiles())('%s', (file) => {
    const src = fs.readFileSync(path.join(ROOT, file), 'utf8');
    expect(violations(file, src)).toEqual([]);
  });
});

const STORAGE_OWNERS = new Set(['lib/storage.ts', 'lib/chunk-load-error.ts']);

function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const name of fs.readdirSync(path.join(ROOT, dir))) {
    const rel = path.join(dir, name);
    if (name === 'node_modules' || name.startsWith('.')) continue;
    if (fs.statSync(path.join(ROOT, rel)).isDirectory()) sourceFiles(rel, out);
    else if (/\.tsx?$/.test(name) && !/\.(test|spec)\.tsx?$/.test(name) && !/\.d\.ts$/.test(name)) out.push(rel);
  }
  return out;
}

describe('all Web Storage access goes through lib/storage', () => {
  it('no localStorage / sessionStorage reference anywhere else in app code', () => {
    const offenders: string[] = [];
    for (const dir of ['app', 'components', 'hooks', 'lib', 'providers', 'config', 'services']) {
      if (!fs.existsSync(path.join(ROOT, dir))) continue;
      for (const file of sourceFiles(dir)) {
        if (STORAGE_OWNERS.has(file)) continue;
        const code = codeOnly(fs.readFileSync(path.join(ROOT, file), 'utf8'));
        if (/\b(localStorage|sessionStorage)\b/.test(code)) offenders.push(file);
      }
    }
    expect(offenders).toEqual([]);
  });
});
