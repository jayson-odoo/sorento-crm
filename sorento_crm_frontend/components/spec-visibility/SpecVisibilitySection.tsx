'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import {
  SearchableMultiSelect,
  type SearchableMultiSelectOption,
} from '@/components/common/SearchableMultiSelect';
import {
  useSpecVisibilityKeys,
  useSpecVisibilityMutations,
  useSpecVisibilityQuery,
} from '@/hooks/useSpecVisibility';
import {
  specVisibilityScopeKey,
  type SpecKeyRef,
  type SpecVisibilityPolicy,
  type SpecVisibilityScope,
} from '@/services/specVisibilityService';

/**
 * Spec visibility policy card (PLAN-spec-visibility-policy, S1).
 *
 * A sibling of `StockVisibilitySection`, not a generalisation of it (plan Decisions
 * "Card"): one rule, one picker, no mode, no presets. The same card serves all three
 * tiers - a contact, a market segment, and the global default - because they hold the
 * same one field and differ only in which row they write.
 *
 * `specs` and `excluded_specs` are two readings of ONE list, never both stored on a
 * row: under Show only, a list of keys is what stays VISIBLE (`null` = every key,
 * `[]` = none); under Hide these, a list is what is WITHHELD (`[]` = nothing hidden -
 * the opposite of what `[]` means under Show only). The picker only ever hands back a
 * list, so the placeholder is what names which reading is in force - drawing both
 * empty lists the same way would show the strictest policy as the loosest one. Flipping
 * the rule carries the ticked keys to the other list rather than clearing the picker,
 * except empty-Hide -> Show only, which lands on `null` ("All specs"), never `[]`
 * ("No specs") - the admin flipped away from "hide nothing", not towards "show nothing".
 */

export interface SpecVisibilitySectionProps {
  scope: SpecVisibilityScope;
  /** Heading above the fields. Pass null where the surrounding card already titles it. */
  heading?: string | null;
  className?: string;
}

type Rule = 'show_only' | 'hide_these';

type Draft = {
  rule: Rule;
  /** Meaningful under `show_only`: null = every key, [] = none. */
  specKeys: string[] | null;
  /** Meaningful under `hide_these`: never null while drafted here - [] IS "nothing
   * hidden" under this rule, the opposite of what [] means on `specKeys`. */
  excludedKeys: string[];
};

function toOption(ref: SpecKeyRef): SearchableMultiSelectOption {
  return { value: ref.key, label: ref.label };
}

export function sourceBadgeText(policy: SpecVisibilityPolicy): string {
  if (policy.source === 'contact') return 'Contact override';
  if (policy.source === 'segment') {
    return policy.source_label ? `Market segment: ${policy.source_label}` : 'Market segment';
  }
  return 'Default';
}

function sameKeys(a: string[] | null, b: string[] | null): boolean {
  if (a === null || b === null) return a === b;
  if (a.length !== b.length) return false;
  const left = [...a].sort();
  const right = [...b].sort();
  return left.every((value, index) => value === right[index]);
}

export function SpecVisibilitySection({
  scope,
  heading = 'Spec visibility',
  className,
}: SpecVisibilitySectionProps) {
  const { data, isLoading, isError, error } = useSpecVisibilityQuery(scope);
  const { save } = useSpecVisibilityMutations(scope);
  const keysQuery = useSpecVisibilityKeys();

  const [draft, setDraft] = useState<Draft>({ rule: 'show_only', specKeys: null, excludedKeys: [] });
  // Remove asks nothing (D7): the countdown takes the button's place and Cancel is
  // the way back. The scope IS the record here, same convention as stock visibility.
  const removal = useDeferredAction({
    actionKey: 'spec_visibility_policy.remove',
    entityType: 'spec_visibility_policy',
    entityId:
      scope.kind === 'contact'
        ? scope.contactId
        : scope.kind === 'segment'
          ? scope.segmentCode
          : undefined,
    verb: 'Removing',
    subject: scope.kind === 'contact' ? 'this override' : 'this policy',
    surface: 'inline',
    watchFromMount: true,
    successMessage: 'Spec visibility removed',
    payload: { scope_kind: scope.kind },
    invalidateKeys: [specVisibilityScopeKey(scope)],
  });
  /** Last server value the draft was seeded from - see the effect below. */
  const syncedRef = useRef<string | null>(null);

  // The card always opens on the policy in force, whichever tier it came from. Server
  // data is the only writer of the draft, so a save or a remove re-seeds it. Keyed on
  // the CONTENT, not the response object, so a background refetch does not clobber a
  // half-made edit.
  useEffect(() => {
    if (!data) return;
    const effective = data.effective;
    const specKeys = effective.specs ? effective.specs.map((s) => s.key) : null;
    const excludedKeys = effective.excluded_specs ? effective.excluded_specs.map((s) => s.key) : null;
    const rule: Rule = excludedKeys !== null ? 'hide_these' : 'show_only';
    const signature = JSON.stringify([
      rule,
      specKeys === null ? null : [...specKeys].sort(),
      excludedKeys === null ? null : [...excludedKeys].sort(),
    ]);
    if (syncedRef.current === signature) return;
    syncedRef.current = signature;
    setDraft({
      rule,
      specKeys: rule === 'show_only' ? specKeys : null,
      excludedKeys: rule === 'hide_these' ? (excludedKeys ?? []) : [],
    });
  }, [data]);

  // Static mode (a fixed ~11-key registry, no server search needed): the picker
  // resolves chip labels from this list itself, so no `selectedOptions` fallback
  // is needed the way an async picker (e.g. Locations) requires one.
  const keyOptions = useMemo(
    () => (keysQuery.data ?? []).map(toOption),
    [keysQuery.data],
  );

  /** The keys the picker is CURRENTLY drafting - the show list under Show only, the
   * hide list under Hide these. Never both at once. */
  const activeIds = useMemo(
    () => (draft.rule === 'show_only' ? (draft.specKeys ?? []) : draft.excludedKeys),
    [draft.rule, draft.specKeys, draft.excludedKeys],
  );

  const baseline = data?.effective;
  const baselineRule: Rule = baseline?.excluded_specs != null ? 'hide_these' : 'show_only';
  const baselineSpecKeys = baseline?.specs ? baseline.specs.map((s) => s.key) : null;
  const baselineExcludedKeys = baseline?.excluded_specs ? baseline.excluded_specs.map((s) => s.key) : [];
  const isDirty =
    !!baseline &&
    (baselineRule !== draft.rule ||
      (draft.rule === 'show_only'
        ? !sameKeys(baselineSpecKeys, draft.specKeys)
        : !sameKeys(baselineExcludedKeys, draft.excludedKeys)));

  const hasOwnRow = !!data?.override;
  const canRemove = hasOwnRow && scope.kind !== 'default';
  const isBusy = save.isPending || removal.isPending;
  // An inheriting tier has nothing of its own yet, so Save is the act of creating the
  // row - offered even when the values still match what is inherited.
  const canSave = !!data && !isBusy && (isDirty || !hasOwnRow);

  if (isLoading) {
    return (
      <div className={className}>
        <Skeleton className="h-5 w-40" />
        <Skeleton className="mt-3 h-9 w-full" />
        <Skeleton className="mt-3 h-5 w-56" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className={className}>
        <p className="text-sm text-destructive">
          {error?.message || 'Spec visibility could not be loaded. Reload the page to try again.'}
        </p>
      </div>
    );
  }

  /** Flips the rule, carrying the ticked keys over rather than clearing the picker
   * (see the component doc). Radix reports the deselect of an already-pressed item
   * as `''`, which is ignored - the toggle is not deselectable. */
  function handleRuleChange(next: string) {
    if (next !== 'show_only' && next !== 'hide_these') return;
    setDraft((prev) => {
      if (prev.rule === next) return prev;
      if (next === 'hide_these') {
        return { ...prev, rule: 'hide_these', excludedKeys: prev.specKeys ?? [] };
      }
      return {
        ...prev,
        rule: 'show_only',
        specKeys: prev.excludedKeys.length === 0 ? null : prev.excludedKeys,
      };
    });
  }

  const hiddenLabels = data.effective.hidden.map((h) => h.label);

  return (
    <div className={className}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        {heading ? <p className="text-sm text-muted-foreground">{heading}</p> : <span />}
        <Badge
          variant={data.effective.source === 'default' ? 'secondary' : 'primary'}
          className="font-normal"
        >
          {sourceBadgeText(data.effective)}
        </Badge>
      </div>

      <div className="mt-3 grid gap-2">
        <Label htmlFor="spec-visibility-keys">Spec keys</Label>
        <SearchableMultiSelect
          id="spec-visibility-keys"
          value={activeIds}
          onChange={(value) =>
            setDraft((prev) =>
              prev.rule === 'show_only' ? { ...prev, specKeys: value } : { ...prev, excludedKeys: value },
            )
          }
          options={keyOptions}
          placeholder={
            draft.rule === 'show_only'
              ? draft.specKeys === null
                ? 'All specs'
                : 'No specs'
              : 'All specs'
          }
          emptyMessage="No spec keys found"
          disabled={isBusy}
        />
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          value={draft.rule}
          onValueChange={handleRuleChange}
          disabled={isBusy}
          aria-label="Spec visibility rule"
          className="w-fit"
        >
          <ToggleGroupItem value="show_only">Show only</ToggleGroupItem>
          <ToggleGroupItem value="hide_these">Hide these</ToggleGroupItem>
        </ToggleGroup>
        <p className="text-sm text-muted-foreground">
          Hidden today: {hiddenLabels.length > 0 ? hiddenLabels.join(', ') : 'Nothing hidden'}
        </p>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          type="button"
          onClick={() =>
            save.mutate({
              // Sent as drafted: null stays null (every key visible), [] stays []
              // (none / nothing hidden). Collapsing one into the other here is what
              // made the two policies unreachable from this card. Exactly one of the
              // two lists is non-null, matching the selected rule - the backend 422s
              // on both non-null.
              spec_keys: draft.rule === 'show_only' ? draft.specKeys : null,
              excluded_spec_keys: draft.rule === 'hide_these' ? draft.excludedKeys : null,
            })
          }
          disabled={!canSave}
        >
          Save spec visibility
        </Button>
        {canRemove
          ? (removal.countdown ?? (
              <Button
                type="button"
                variant="outline"
                onClick={() => removal.start()}
                disabled={isBusy}
              >
                {scope.kind === 'contact' ? 'Remove override' : 'Remove policy'}
              </Button>
            ))
          : null}
      </div>
    </div>
  );
}

export default SpecVisibilitySection;
