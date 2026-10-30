'use client';

import * as React from 'react';
import { AIExtractDialog } from '@/components/common/ai-extract/AIExtractDialog';
import type { AIExtractResult } from '@/app/(auth)/portal/lib/portal-client';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { usePartyMutations, useProjectAiExtract } from '../hooks/useProjects';
import type {
  ProjectExtractFieldKey,
  ProjectExtractProposal,
  ProjectExtractResult,
} from '../services/projectService';
import type { PartyType } from '../types/project.types';

/** What the form fills in once the review is confirmed (new parties already created). */
export type ProjectExtractFill = {
  title?: string;
  developer?: { id: string; name: string };
  architect?: { id: string; name: string };
  main_contractor?: { id: string; name: string };
  project_type?: { id: string; name: string };
  state?: string;
  mukim?: string;
};

const FIELD_DEFS: { name: ProjectExtractFieldKey; label: string }[] = [
  { name: 'developer', label: 'Developer' },
  { name: 'architect', label: 'Architect' },
  { name: 'main_contractor', label: 'Main contractor' },
  { name: 'project_type', label: 'Project type' },
  { name: 'state', label: 'State' },
  { name: 'mukim', label: 'Area' },
  { name: 'title', label: 'Project title' },
];

const PARTY_FIELDS: ProjectExtractFieldKey[] = ['developer', 'architect', 'main_contractor'];

function proposalText(proposal: ProjectExtractProposal | string | undefined): string {
  if (typeof proposal === 'string') return proposal.trim();
  if (!proposal || (proposal.status !== 'match' && proposal.status !== 'new')) return '';
  return (proposal.value ?? proposal.name ?? '').trim();
}

function objectProposal(
  proposal: ProjectExtractProposal | string | undefined,
): ProjectExtractProposal | undefined {
  return typeof proposal === 'string' ? undefined : proposal;
}

/** The review table lists only match and new proposals (C7). */
function toExtractResult(result: ProjectExtractResult): AIExtractResult {
  const values: Record<string, unknown> = {};
  for (const { name } of FIELD_DEFS) {
    const text = proposalText(result[name]);
    if (text) values[name] = text;
  }
  return {
    values,
    products: [],
    per_field: {},
    usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
  };
}

/**
 * AI extract for the register form: the shared dialog with the title as its ready text source
 * (PROJECT-REGISTER-V2 C1), a Match / New pill per row (C7), and a confirm that first creates
 * the New parties (C8) before handing the values to the form.
 */
export function ProjectAIExtractDialog({
  open,
  onOpenChange,
  titleText,
  canCreateParties,
  onFill,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  titleText: string;
  canCreateParties: boolean;
  onFill: (fill: ProjectExtractFill) => void;
}) {
  const extractProject = useProjectAiExtract();
  const { create } = usePartyMutations();
  const [proposals, setProposals] = React.useState<ProjectExtractResult>({});

  const extract = React.useCallback(
    async (files: File[], text: string | null) => {
      const result = await extractProject(text, files);
      setProposals(result);
      return toExtractResult(result);
    },
    [extractProject],
  );

  async function handleApply({ values }: { values: Record<string, string | string[]> }) {
    const listed = (name: ProjectExtractFieldKey) => name in values;
    const fill: ProjectExtractFill = {};

    for (const name of PARTY_FIELDS) {
      const proposal = proposals[name];
      if (!listed(name) || !proposal || typeof proposal === 'string') continue;
      if (proposal.status === 'match' && proposal.id) {
        fill[name as 'developer'] = { id: proposal.id, name: proposal.name ?? '' };
      } else if (proposal.status === 'new' && canCreateParties && proposal.name) {
        // A user who may not create parties leaves the field blank (C8).
        const party = await create.mutateAsync({
          name: proposal.name,
          party_type: name as PartyType,
        });
        fill[name as 'developer'] = { id: party.id, name: party.name };
      }
    }
    const type = objectProposal(proposals.project_type);
    if (listed('project_type') && type?.status === 'match' && type.id) {
      fill.project_type = { id: type.id, name: type.name ?? '' };
    }
    if (listed('state')) fill.state = proposalText(proposals.state);
    if (listed('mukim')) fill.mukim = proposalText(proposals.mukim);
    if (listed('title')) fill.title = proposalText(proposals.title);
    onFill(fill);
  }

  return (
    <AIExtractDialog
      open={open}
      onOpenChange={onOpenChange}
      fieldDefs={FIELD_DEFS}
      extract={extract}
      canAttach={false}
      textSource={{ label: 'Project title', text: titleText }}
      renderFieldStatus={(name) => {
        const proposal = proposals[name as ProjectExtractFieldKey];
        const status = typeof proposal === 'string' ? undefined : proposal?.status;
        if (status !== 'match' && status !== 'new') return null;
        return (
          <span
            className={`${STATUS_PILL_BASE} ${statusPillClass(status === 'match' ? 'verified' : 'new')}`}
          >
            {status === 'match' ? 'Match' : 'New'}
          </span>
        );
      }}
      onApply={handleApply}
    />
  );
}
