'use client';

import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { ruleSentence } from '../../lib/ruleSentence';
import { useSpecTryIt, type TryItSource } from '../../hooks/useSpecTryIt';
import SpecPreviewPanel from '../SpecPreviewPanel';
import SpecRuleEditor from '../SpecRuleEditor';
import SpecTryItPanel from '../SpecTryItPanel';
import type { SpecKeyDraft } from '../../hooks/useSpecKeyRecord';
import type { SpecDerivationRule, SpecRegistryKey } from '../../types/productSpec.types';

export interface RulesTabProps {
  row: SpecRegistryKey;
  mode: 'view' | 'edit';
  draft: SpecKeyDraft | null;
  setDraft: (updater: (draft: SpecKeyDraft) => SpecKeyDraft) => void;
}

/**
 * How this specification is read from a product (AC-B.4).
 *
 * View mode reads each rule as a sentence; edit mode swaps the whole list for
 * `SpecRuleEditor` (dnd reorder, kind menu, per-row inputs) - the two DO diverge in
 * shape here, unlike the value rows, because a rule is a sentence to read in view and
 * a form to build in edit, and rendering the form read-only would not be reading it
 * as a sentence. Try it on a product runs in both modes; Preview on catalogue is
 * edit-only, "after a rule change" (B.4). No per-tab Edit (D16): the record page's
 * one Edit button is the only entry point, so shipped rules just list with their
 * "default" pill and an empty key says "No rules yet" with no CTA of its own.
 */
export function RulesTab({ row, mode, draft, setDraft }: RulesTabProps) {
  const rules: SpecDerivationRule[] =
    mode === 'edit' && draft ? draft.rules : (row.effective_rules ?? row.derivation_rules ?? []);

  const [trySource, setTrySource] = useState<TryItSource | null>(null);
  const {
    result: tryResult,
    loading: tryLoading,
    error: tryError,
  } = useSpecTryIt(row.spec_key, rules, trySource);

  const setRules = (next: SpecDerivationRule[]) =>
    setDraft((d) => ({ ...d, rules: next }));

  return (
    <div className="flex flex-col gap-4">
      <SpecTryItPanel
        source={trySource}
        onSourceChange={setTrySource}
        description={tryResult?.description ?? null}
        loading={tryLoading}
        error={tryError}
      />

      {mode === 'edit' ? (
        <SpecRuleEditor
          rules={rules}
          specKey={row.spec_key}
          onChange={setRules}
          reads={tryResult?.reads}
          winnerIndex={tryResult?.winner_index}
        />
      ) : rules.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-md border border-dashed p-8 text-center">
          <p className="text-sm font-medium">No rules yet</p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {rules.map((rule, index) => {
            const read = tryResult?.reads?.[index];
            const isWinner = tryResult?.winner_index === index;
            return (
              <div
                key={rule._uid ?? index}
                className={`flex flex-col gap-1 rounded-md border bg-background p-2 text-sm ${
                  isWinner ? 'border-primary ring-1 ring-primary' : ''
                }`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="w-5 shrink-0 text-center font-mono text-xs text-muted-foreground">
                    {index + 1}
                  </span>
                  {(rule.shipped || rule.shipped_backfill) && (
                    <Badge variant="secondary" appearance="light" size="sm">
                      default
                    </Badge>
                  )}
                  {isWinner && (
                    <Badge variant="primary" appearance="light" size="sm">
                      winner
                    </Badge>
                  )}
                  <span>{ruleSentence(rule, row.label)}</span>
                </div>
                {read !== undefined && trySource && (
                  <div className="ml-7 text-xs text-muted-foreground">
                    Reads:{' '}
                    <span className="font-mono">
                      {read?.value === null || read?.value === undefined
                        ? read?.evidence || 'nothing'
                        : `${String(read.value)}${read.evidence ? ` from \`${read.evidence}\`` : ''}`}
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {mode === 'edit' && <SpecPreviewPanel specKey={row.spec_key} rules={rules} />}
    </div>
  );
}

export default RulesTab;
