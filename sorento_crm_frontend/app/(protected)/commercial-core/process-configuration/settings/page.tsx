'use client';

import { useEffect, useState, type Dispatch, type SetStateAction } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { getProcessSettings, patchProcessSettings } from '../services/processSettingsService';

type CodeLabelRow = { code: string; label: string };

function normalizeRows(raw: unknown): CodeLabelRow[] {
  if (!Array.isArray(raw)) return [];
  const out: CodeLabelRow[] = [];
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue;
    const o = item as Record<string, unknown>;
    const code = String(o.code ?? '').trim();
    if (!code) continue;
    const label = String(o.label ?? code).trim() || code;
    out.push({ code, label });
  }
  return out;
}

function CodeLabelTable({
  title,
  hint,
  rows,
  setRows,
}: {
  title: string;
  hint: string;
  rows: CodeLabelRow[];
  setRows: Dispatch<SetStateAction<CodeLabelRow[]>>;
}) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <Label>{title}</Label>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setRows((r) => [...r, { code: '', label: '' }])}
        >
          <Plus className="size-4" />
          Add
        </Button>
      </div>
      <p className="text-muted-foreground mb-3 text-xs">{hint}</p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Code</TableHead>
            <TableHead>Label</TableHead>
            <TableHead className="w-12" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={3} className="text-muted-foreground text-sm">
                No rows. Add codes to show options in lead forms.
              </TableCell>
            </TableRow>
          ) : (
            rows.map((row, idx) => (
              <TableRow key={idx}>
                <TableCell>
                  <Input
                    value={row.code}
                    onChange={(e) =>
                      setRows((prev) =>
                        prev.map((x, i) => (i === idx ? { ...x, code: e.target.value } : x)),
                      )
                    }
                    className="font-mono text-sm"
                  />
                </TableCell>
                <TableCell>
                  <Input
                    value={row.label}
                    onChange={(e) =>
                      setRows((prev) =>
                        prev.map((x, i) => (i === idx ? { ...x, label: e.target.value } : x)),
                      )
                    }
                  />
                </TableCell>
                <TableCell>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => setRows((prev) => prev.filter((_, i) => i !== idx))}
                    aria-label="Remove row"
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  );
}

export default function ProcessSettingsPage() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ['commercial-process-settings'],
    queryFn: getProcessSettings,
  });
  const [assignmentText, setAssignmentText] = useState('{}');
  const [remindersText, setRemindersText] = useState('{}');
  const [pricingPendingStage, setPricingPendingStage] = useState('review');
  const [paymentTermsRows, setPaymentTermsRows] = useState<CodeLabelRow[]>([]);
  const [taxRatesRows, setTaxRatesRows] = useState<CodeLabelRow[]>([]);
  const [leadStatesRows, setLeadStatesRows] = useState<CodeLabelRow[]>([]);
  const [leadCountriesRows, setLeadCountriesRows] = useState<CodeLabelRow[]>([]);
  const [leadPropertyTypesRows, setLeadPropertyTypesRows] = useState<CodeLabelRow[]>([]);
  const [leadBudgetRangesRows, setLeadBudgetRangesRows] = useState<CodeLabelRow[]>([]);
  const [leadClosureRows, setLeadClosureRows] = useState<CodeLabelRow[]>([]);
  const [leadSourcesRows, setLeadSourcesRows] = useState<CodeLabelRow[]>([]);
  const [leadContactMethodsRows, setLeadContactMethodsRows] = useState<CodeLabelRow[]>([]);
  const [leadIndustriesRows, setLeadIndustriesRows] = useState<CodeLabelRow[]>([]);

  useEffect(() => {
    if (!data) return;
    const ass = { ...(typeof data.assignment === 'object' && data.assignment ? data.assignment : {}) } as Record<
      string,
      unknown
    >;
    const pt = ass.payment_terms;
    const tr = ass.tax_rates;
    setPaymentTermsRows(normalizeRows(pt));
    setTaxRatesRows(normalizeRows(tr));
    setLeadStatesRows(normalizeRows(ass.lead_states));
    setLeadCountriesRows(normalizeRows(ass.lead_countries));
    setLeadPropertyTypesRows(normalizeRows(ass.lead_property_types));
    setLeadBudgetRangesRows(normalizeRows(ass.lead_budget_ranges));
    setLeadClosureRows(normalizeRows(ass.lead_sales_closure_confidence));
    setLeadSourcesRows(normalizeRows(ass.lead_sources));
    setLeadContactMethodsRows(normalizeRows(ass.lead_contact_methods));
    setLeadIndustriesRows(normalizeRows(ass.lead_industries));
    delete ass.payment_terms;
    delete ass.tax_rates;
    delete ass.lead_states;
    delete ass.lead_countries;
    delete ass.lead_property_types;
    delete ass.lead_budget_ranges;
    delete ass.lead_sales_closure_confidence;
    delete ass.lead_sources;
    delete ass.lead_contact_methods;
    delete ass.lead_industries;
    setAssignmentText(JSON.stringify(ass, null, 2));
    setRemindersText(JSON.stringify(data.reminders || {}, null, 2));
    const pc = data.pricing_controls || {};
    const code = (pc as { mq_pending_approval_stage_code?: string }).mq_pending_approval_stage_code;
    setPricingPendingStage(typeof code === 'string' && code.trim() ? code.trim() : 'review');
  }, [data]);

  const mut = useMutation({
    mutationFn: () => {
      let assignmentCore: Record<string, unknown> = {};
      let reminders: Record<string, unknown> = {};
      try {
        assignmentCore = JSON.parse(assignmentText || '{}') as Record<string, unknown>;
        reminders = JSON.parse(remindersText || '{}') as Record<string, unknown>;
      } catch {
        throw new Error('JSON must be valid');
      }
      const assignment: Record<string, unknown> = {
        ...assignmentCore,
        payment_terms: paymentTermsRows.filter((r) => r.code.trim()),
        tax_rates: taxRatesRows.filter((r) => r.code.trim()),
        lead_states: leadStatesRows.filter((r) => r.code.trim()),
        lead_countries: leadCountriesRows.filter((r) => r.code.trim()),
        lead_property_types: leadPropertyTypesRows.filter((r) => r.code.trim()),
        lead_budget_ranges: leadBudgetRangesRows.filter((r) => r.code.trim()),
        lead_sales_closure_confidence: leadClosureRows.filter((r) => r.code.trim()),
        lead_sources: leadSourcesRows.filter((r) => r.code.trim()),
        lead_contact_methods: leadContactMethodsRows.filter((r) => r.code.trim()),
        lead_industries: leadIndustriesRows.filter((r) => r.code.trim()),
      };
      const pricing_controls = {
        ...(typeof data?.pricing_controls === 'object' && data.pricing_controls ? data.pricing_controls : {}),
        mq_pending_approval_stage_code: pricingPendingStage.trim() || 'review',
      };
      return patchProcessSettings({ assignment, reminders, pricing_controls });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-process-settings'] });
      void qc.invalidateQueries({ queryKey: ['lead-assignment-select'] });
      toast.success('Saved');
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (isLoading && !data) {
    return <p className="text-muted-foreground text-sm">Loading…</p>;
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Process settings</CardTitle>
        </CardHeader>
        <CardContent className="max-w-4xl space-y-6">
          <div>
            <CardTitle className="mb-3 text-base">Quotation lists</CardTitle>
            <p className="text-muted-foreground mb-4 text-xs">
              Codes and labels are used in quotation forms (payment terms and tax rate selectors). Other assignment
              keys stay in JSON below.
            </p>
            <div className="space-y-6">
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <Label>Payment terms</Label>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setPaymentTermsRows((r) => [...r, { code: '', label: '' }])}
                  >
                    <Plus className="size-4" />
                    Add
                  </Button>
                </div>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Code</TableHead>
                      <TableHead>Label</TableHead>
                      <TableHead className="w-12" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {paymentTermsRows.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={3} className="text-muted-foreground text-sm">
                          No rows. Add at least one code for the quotation payment-term list.
                        </TableCell>
                      </TableRow>
                    ) : (
                      paymentTermsRows.map((row, idx) => (
                        <TableRow key={idx}>
                          <TableCell>
                            <Input
                              value={row.code}
                              onChange={(e) =>
                                setPaymentTermsRows((rows) =>
                                  rows.map((x, i) => (i === idx ? { ...x, code: e.target.value } : x)),
                                )
                              }
                              className="font-mono text-sm"
                            />
                          </TableCell>
                          <TableCell>
                            <Input
                              value={row.label}
                              onChange={(e) =>
                                setPaymentTermsRows((rows) =>
                                  rows.map((x, i) => (i === idx ? { ...x, label: e.target.value } : x)),
                                )
                              }
                            />
                          </TableCell>
                          <TableCell>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              onClick={() => setPaymentTermsRows((rows) => rows.filter((_, i) => i !== idx))}
                              aria-label="Remove row"
                            >
                              <Trash2 className="size-4" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <Label>Tax rates</Label>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setTaxRatesRows((r) => [...r, { code: '', label: '' }])}
                  >
                    <Plus className="size-4" />
                    Add
                  </Button>
                </div>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Code</TableHead>
                      <TableHead>Label</TableHead>
                      <TableHead className="w-12" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {taxRatesRows.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={3} className="text-muted-foreground text-sm">
                          No rows. Add codes for line-level tax selection (label can include the rate, e.g. SST 6%).
                        </TableCell>
                      </TableRow>
                    ) : (
                      taxRatesRows.map((row, idx) => (
                        <TableRow key={idx}>
                          <TableCell>
                            <Input
                              value={row.code}
                              onChange={(e) =>
                                setTaxRatesRows((rows) =>
                                  rows.map((x, i) => (i === idx ? { ...x, code: e.target.value } : x)),
                                )
                              }
                              className="font-mono text-sm"
                            />
                          </TableCell>
                          <TableCell>
                            <Input
                              value={row.label}
                              onChange={(e) =>
                                setTaxRatesRows((rows) =>
                                  rows.map((x, i) => (i === idx ? { ...x, label: e.target.value } : x)),
                                )
                              }
                            />
                          </TableCell>
                          <TableCell>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              onClick={() => setTaxRatesRows((rows) => rows.filter((_, i) => i !== idx))}
                              aria-label="Remove row"
                            >
                              <Trash2 className="size-4" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </div>
          </div>

          <div>
            <CardTitle className="mb-3 text-base">Lead qualification lists</CardTitle>
            <p className="text-muted-foreground mb-4 text-xs">
              Codes and labels populate dropdowns on the lead wizard and lead edit form (sources, industries, states,
              countries, property types, budget ranges, sales closure confidence). Use a stable code (e.g.{' '}
              <span className="font-mono">WEB</span>) and a display label (e.g. Website).
            </p>
            <div className="space-y-8">
              <CodeLabelTable
                title="Lead sources"
                hint="Referral channels (e.g. WEBSITE, REFERRAL, AGENT)."
                rows={leadSourcesRows}
                setRows={setLeadSourcesRows}
              />
              <CodeLabelTable
                title="Contact methods"
                hint="Preferred contact channels (e.g. PHONE, EMAIL, WHATSAPP)."
                rows={leadContactMethodsRows}
                setRows={setLeadContactMethodsRows}
              />
              <CodeLabelTable
                title="Industries"
                hint="Industry segments for qualification (e.g. CONSTRUCTION, PROPERTY)."
                rows={leadIndustriesRows}
                setRows={setLeadIndustriesRows}
              />
              <CodeLabelTable
                title="States"
                hint="Malaysian states / regions shown in address and property sections."
                rows={leadStatesRows}
                setRows={setLeadStatesRows}
              />
              <CodeLabelTable
                title="Countries"
                hint="Countries for lead address fields."
                rows={leadCountriesRows}
                setRows={setLeadCountriesRows}
              />
              <CodeLabelTable
                title="Property types"
                hint="e.g. Residential, Commercial, Land."
                rows={leadPropertyTypesRows}
                setRows={setLeadPropertyTypesRows}
              />
              <CodeLabelTable
                title="Budget ranges"
                hint="Ranges in RM or bands used for lead qualification."
                rows={leadBudgetRangesRows}
                setRows={setLeadBudgetRangesRows}
              />
              <CodeLabelTable
                title="Sales closure confidence"
                hint="Confidence levels for forecasting (e.g. Low, Medium, High)."
                rows={leadClosureRows}
                setRows={setLeadClosureRows}
              />
            </div>
          </div>

          <div>
            <Label>
              Assignment (JSON, excludes payment_terms, tax_rates, and lead qualification lists above)
            </Label>
            <Textarea
              value={assignmentText}
              onChange={(e) => setAssignmentText(e.target.value)}
              rows={8}
              className="font-mono text-sm"
            />
          </div>
          <div>
            <Label>Reminders aggregate (JSON)</Label>
            <Textarea
              value={remindersText}
              onChange={(e) => setRemindersText(e.target.value)}
              rows={6}
              className="font-mono text-sm"
            />
          </div>
          <div>
            <Label htmlFor="pricing-pending-stage">Pricing: pending approval stage code</Label>
            <p className="text-muted-foreground mb-2 text-xs">
              When a quotation is priced outside product tolerance and is moved toward a terminal stage, it is routed
              to this master-quotation stage code instead (must match an active stage in Master quotation stages).
            </p>
            <Input
              id="pricing-pending-stage"
              className="max-w-md"
              value={pricingPendingStage}
              onChange={(e) => setPricingPendingStage(e.target.value)}
            />
          </div>
          <Button onClick={() => mut.mutate()} disabled={mut.isPending}>
            Save
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
