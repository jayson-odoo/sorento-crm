import type { SpecDerivationRule } from '../types/productSpec.types';

/**
 * One browser-only identity per rule (B-4, review round 2). A rule read from the
 * server is given `r{index}` once, by `projectSpecKeyDraft`; a rule added in this
 * sitting is given `new-{n}` here, which can never collide with a server one. The
 * rule modal keeps whichever id the rule already had, so add, edit, drag, inline
 * edit and remove all match on the SAME id.
 */
let sequence = 0;

export function newRuleUid(): string {
  sequence += 1;
  return `new-${sequence}`;
}

/** A builder as one comparable string: keys sorted, absent parts dropped. */
export function builderKey(builder: unknown): string {
  const walk = (value: unknown): unknown => {
    if (Array.isArray(value)) return value.map(walk);
    if (value && typeof value === 'object') {
      return Object.fromEntries(
        Object.keys(value as Record<string, unknown>)
          .sort()
          .filter((key) => (value as Record<string, unknown>)[key] !== undefined)
          .map((key) => [key, walk((value as Record<string, unknown>)[key])]),
      );
    }
    return value;
  };
  return JSON.stringify(walk(builder));
}

/**
 * Whether this exact rule is what the server holds. Only a saved rule has anything
 * for `spec_rule.remove` to remove; one added (or changed) in this sitting exists
 * only in the draft, so taking it away is a local edit that the next Save carries.
 */
export function isSavedRule(rule: SpecDerivationRule, saved: readonly SpecDerivationRule[]): boolean {
  const key = builderKey(rule.builder);
  return saved.some((stored) => builderKey(stored.builder) === key);
}

/** The id the grid keys a row by. The position fallback only ever applies to
 *  view mode, where the rules come straight off the row and nothing edits them. */
export function ruleUid(rule: SpecDerivationRule, index: number): string {
  return rule._uid ?? `r${index}`;
}
