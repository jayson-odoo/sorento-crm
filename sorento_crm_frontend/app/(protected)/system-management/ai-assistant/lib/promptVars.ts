/**
 * Client-side mirror of the backend var validation (PLAN §9b Q7). Declared
 * vars are a fixed property of the KEY. Unknown `{{token}}` → hard block save;
 * missing declared var → soft warn.
 */
export interface VarValidation {
  present: string[]; // declared vars found in the template
  missing: string[]; // declared vars NOT in the template (soft warn)
  unknown: string[]; // `{{tokens}}` in the template that are not declared (hard block)
}

const TOKEN_RE = /\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g;

export function tokensInTemplate(template: string): string[] {
  const seen = new Set<string>();
  for (const m of template.matchAll(TOKEN_RE)) seen.add(m[1]);
  return Array.from(seen);
}

export function validateVars(template: string, declared: string[]): VarValidation {
  const found = new Set(tokensInTemplate(template));
  const declaredSet = new Set(declared);
  return {
    present: declared.filter((d) => found.has(d)),
    missing: declared.filter((d) => !found.has(d)),
    unknown: Array.from(found).filter((t) => !declaredSet.has(t)),
  };
}
