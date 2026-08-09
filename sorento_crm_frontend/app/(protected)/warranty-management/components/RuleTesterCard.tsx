'use client';

import { useState } from 'react';
import { CircleSlash, FlaskConical } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useTestKindRules } from '../hooks/useWarrantyConfig';
import {
  KIND_RULE_MATCH_TYPES,
  KIND_RULE_MATCH_TYPE_LABEL,
  type KindRuleMatchType,
  type KindRuleTestResponse,
  type WarrantyKindRef,
} from '../types/warranty-config.types';

/**
 * The rule tester (AC-P6, P6b, P6c).
 *
 * Shaped after `master-data-management/lookup-sets/TestResolveCard` - inputs on
 * top, the answer under them, the error in the same place - and differs from it
 * only where this question is bigger: three inputs instead of one, an optional
 * unsaved candidate rule, and EVERY match in rank order rather than the winner
 * alone. A mapping that wins by one tie-break is a different fact from a mapping
 * that is the only match, and only the second is safe to stop thinking about.
 */
export function RuleTesterCard({ kinds }: { kinds: WarrantyKindRef[] }) {
  const [productCode, setProductCode] = useState('');
  const [categoryCode, setCategoryCode] = useState('');
  const [productName, setProductName] = useState('');

  const [useCandidate, setUseCandidate] = useState(false);
  const [candidateKindId, setCandidateKindId] = useState('');
  const [candidateMatchType, setCandidateMatchType] = useState<KindRuleMatchType>('model_prefix');
  const [candidateValue, setCandidateValue] = useState('');
  const [candidatePriority, setCandidatePriority] = useState('0');

  const [result, setResult] = useState<KindRuleTestResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const tester = useTestKindRules();

  const hasInput = !!(productCode.trim() || categoryCode.trim() || productName.trim());
  const candidateReady = !useCandidate || (!!candidateKindId && !!candidateValue.trim());

  async function run() {
    setErr(null);
    setResult(null);
    try {
      const response = await tester.mutateAsync({
        product_code: productCode.trim() || null,
        category_code: categoryCode.trim() || null,
        product_name: productName.trim() || null,
        candidate_rule:
          useCandidate && candidateKindId && candidateValue.trim()
            ? {
                kind_id: candidateKindId,
                match_type: candidateMatchType,
                match_value: candidateValue.trim(),
                priority: Number(candidatePriority) || 0,
              }
            : null,
      });
      setResult(response);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Test failed');
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FlaskConical className="size-4" />
          Rule tester
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor="tester-product-code">Product code</Label>
            <Input
              id="tester-product-code"
              value={productCode}
              onChange={(e) => setProductCode(e.target.value)}
              placeholder="SRTMCB6071-BL"
              autoComplete="off"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="tester-category-code">Category code</Label>
            <Input
              id="tester-category-code"
              value={categoryCode}
              onChange={(e) => setCategoryCode(e.target.value)}
              autoComplete="off"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="tester-product-name">Product name</Label>
            <Input
              id="tester-product-name"
              value={productName}
              onChange={(e) => setProductName(e.target.value)}
              autoComplete="off"
            />
          </div>
        </div>

        <div className="rounded-lg border border-border p-3">
          <div className="flex items-center gap-2">
            <Checkbox
              id="tester-candidate"
              checked={useCandidate}
              onCheckedChange={(v) => setUseCandidate(v === true)}
            />
            <Label htmlFor="tester-candidate">Include an unsaved rule</Label>
          </div>
          {useCandidate ? (
            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="space-y-1.5">
                <Label htmlFor="tester-candidate-kind">Kind</Label>
                <SearchableSelect
                  id="tester-candidate-kind"
                  value={candidateKindId}
                  onChange={setCandidateKindId}
                  placeholder="Select a kind"
                  options={kinds.map((k) => ({ value: k.id, label: k.name, searchText: k.code }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="tester-candidate-type">Match type</Label>
                <SearchableSelect
                  id="tester-candidate-type"
                  value={candidateMatchType}
                  onChange={(v) => setCandidateMatchType(v as KindRuleMatchType)}
                  options={KIND_RULE_MATCH_TYPES.map((t) => ({
                    value: t,
                    label: KIND_RULE_MATCH_TYPE_LABEL[t],
                  }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="tester-candidate-value">Value</Label>
                <Input
                  id="tester-candidate-value"
                  value={candidateValue}
                  onChange={(e) => setCandidateValue(e.target.value)}
                  placeholder="SRTMCB"
                  autoComplete="off"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="tester-candidate-priority">Priority</Label>
                <Input
                  id="tester-candidate-priority"
                  type="number"
                  value={candidatePriority}
                  onChange={(e) => setCandidatePriority(e.target.value)}
                />
              </div>
            </div>
          ) : null}
        </div>

        <div className="flex flex-wrap gap-2">
          <Button onClick={run} disabled={!hasInput || !candidateReady || tester.isPending}>
            {tester.isPending ? 'Resolving...' : 'Resolve'}
          </Button>
          {result || err ? (
            <Button
              variant="outline"
              onClick={() => {
                setResult(null);
                setErr(null);
              }}
            >
              Clear
            </Button>
          ) : null}
        </div>

        {err ? <div className="text-sm text-destructive">{err}</div> : null}

        {result ? (
          <div className="space-y-3">
            {result.resolved_kind ? (
              <div className="rounded-lg border border-border bg-muted/30 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm text-muted-foreground">Resolved kind</span>
                  <Badge variant="success" appearance="light" size="md">
                    {result.resolved_kind.name}
                  </Badge>
                  {result.deciding_rule?.is_candidate ? (
                    <Badge variant="warning" appearance="light" size="md">
                      Decided by the unsaved rule
                    </Badge>
                  ) : null}
                </div>
                {result.deciding_rule ? (
                  <div className="mt-2 text-sm">
                    <span className="text-muted-foreground">Deciding rule</span>{' '}
                    <span className="font-medium">
                      {KIND_RULE_MATCH_TYPE_LABEL[result.deciding_rule.match_type]}
                    </span>{' '}
                    <span className="font-mono text-xs break-all">
                      {result.deciding_rule.match_value}
                    </span>{' '}
                    <span className="text-muted-foreground">
                      (priority {result.deciding_rule.priority})
                    </span>
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm">
                <CircleSlash className="mt-0.5 size-4 shrink-0 text-destructive" />
                <span>No rule reached a kind for this product.</span>
              </div>
            )}

            <div>
              <div className="mb-1.5 text-sm font-medium">
                Matched rules{' '}
                <span className="text-muted-foreground">({result.matches.length})</span>
              </div>
              {result.matches.length === 0 ? (
                <div className="rounded-lg border border-dashed border-border p-3 text-sm text-muted-foreground">
                  Nothing matched. Add a rule for the kind this product belongs to.
                </div>
              ) : (
                <ol className="space-y-1.5">
                  {result.matches.map((m) => (
                    <li
                      key={`${m.rank}-${m.rule.id ?? 'candidate'}`}
                      className="flex flex-wrap items-center gap-2 rounded-md border border-border px-3 py-2 text-sm"
                    >
                      <Badge variant="secondary" appearance="light" size="sm">
                        #{m.rank}
                      </Badge>
                      <span className="font-medium">{m.kind.name}</span>
                      <span className="text-muted-foreground">
                        {KIND_RULE_MATCH_TYPE_LABEL[m.rule.match_type]}
                      </span>
                      <span className="font-mono text-xs break-all" title={m.rule.match_value}>
                        {m.rule.match_value}
                      </span>
                      <span className="text-muted-foreground">priority {m.rule.priority}</span>
                      <span className="text-muted-foreground">matched {m.matched_length}</span>
                      {m.is_candidate ? (
                        <Badge variant="warning" appearance="light" size="sm">
                          Unsaved
                        </Badge>
                      ) : null}
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
