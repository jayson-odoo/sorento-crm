'use client';

import { useState } from 'react';
import { SpecRuleModal } from '../SpecRuleModal';
import { SpecRulesGrid } from '../SpecRulesGrid';
import { useSpecTryIt, type TryItSource } from '../../hooks/useSpecTryIt';
import SpecTryItPanel from '../SpecTryItPanel';
import type { SpecKeyDraft } from '../../hooks/useSpecKeyRecord';
import type { SpecDerivationRule, SpecRegistryKey } from '../../types/productSpec.types';

export interface RulesTabProps {
  row: SpecRegistryKey;
  registry: SpecRegistryKey[];
  mode: 'view' | 'edit';
  draft: SpecKeyDraft | null;
  setDraft: (updater: (draft: SpecKeyDraft) => SpecKeyDraft) => void;
}

/**
 * How it is read (AC-S1.6, AC-S1.11, AC-S1.14): a structured grid, one row per
 * rule, one column per part. No rule is ever shown as a sentence, on the grid or
 * in the rule form (owner ruling, 27 Sep 2026). Add a rule / the row's Edit action
 * open `SpecRuleModal`; Try it on a product runs against the whole draft list, so
 * the winner shown per row is the one the engine would actually keep.
 */
export function RulesTab({ row, registry, mode, draft, setDraft }: RulesTabProps) {
  const rules: SpecDerivationRule[] = mode === 'edit' && draft ? draft.rules : row.effective_rules ?? [];

  const [trySource, setTrySource] = useState<TryItSource | null>(null);
  const {
    result: tryResult,
    loading: tryLoading,
    error: tryError,
  } = useSpecTryIt(row.spec_key, rules, trySource);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);

  const setRules = (next: SpecDerivationRule[]) => setDraft((d) => ({ ...d, rules: next }));

  const openAdd = () => {
    setEditingIndex(null);
    setModalOpen(true);
  };
  const openEdit = (index: number) => {
    setEditingIndex(index);
    setModalOpen(true);
  };

  return (
    <div className="flex flex-col gap-4">
      {mode === 'view' && (
        <SpecTryItPanel
          source={trySource}
          onSourceChange={setTrySource}
          description={tryResult?.description ?? null}
          loading={tryLoading}
          error={tryError}
        />
      )}

      <SpecRulesGrid
        rules={rules}
        spec={row}
        registry={registry}
        mode={mode}
        onChange={setRules}
        onEdit={openEdit}
        onAdd={openAdd}
        reads={mode === 'view' ? tryResult?.reads : null}
        winnerIndex={mode === 'view' ? tryResult?.winner_index : null}
      />

      {mode === 'edit' && (
        <SpecRuleModal
          open={modalOpen}
          onOpenChange={setModalOpen}
          spec={row}
          registry={registry}
          rules={rules}
          editingIndex={editingIndex}
          onSave={(rule, index) => {
            if (index === null) setRules([...rules, rule]);
            else setRules(rules.map((r, i) => (i === index ? rule : r)));
          }}
        />
      )}
    </div>
  );
}

export default RulesTab;
