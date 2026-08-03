/**
 * The builder must not offer to edit a document it cannot read.
 *
 * F0 replaced `workflow_form_versions.schema` with the `form_engine` document
 * (`{schemaVersion, pages[] -> sections[] -> fields[]}`) and named the cost up front: the
 * FE builder, deferred to F3. F3 is not built, so this screen still authors the retired
 * shape (`header_fields`, `header_sections`, `line_groups`, `states`, `transitions`,
 * `notification_rules`) - and the backend forbids every one of those keys, because
 * `_assert_document_shape` validates each draft save against a `FormDocument` configured
 * `extra="forbid"`.
 *
 * Verified in a browser before this test was written: the tabs rendered an EMPTY form over
 * a definition that really had fields, and "Save draft schema" returned a bare 422. The
 * stored document survived - the backend guard held - but an empty editor reads as "this
 * form has no fields" and invites somebody to rebuild it from scratch over a document that
 * was fine.
 *
 * These tests pin BOTH directions, so F3 cannot be called finished while a current-model
 * document still lands on the notice, and a legacy document does not lose its editor in the
 * meantime.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const useWorkflowDefinitionQuery = vi.fn();

vi.mock('../hooks/useWorkflowForms', () => ({
  useWorkflowDefinitionQuery: (...args: unknown[]) => useWorkflowDefinitionQuery(...args),
  useUpdateWorkflowDefinition: () => ({ mutate: vi.fn(), isPending: false }),
  usePublishWorkflowDefinition: () => ({ mutate: vi.fn(), isPending: false }),
  useWorkflowFlowGraphQuery: () => ({ data: null }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// Not the subject, and each pulls in its own data layer.
vi.mock('./RoleIdsPicker', () => ({ default: () => null }));
vi.mock('./WorkflowDynamicFields', () => ({ WorkflowHeaderFieldsForm: () => null }));
vi.mock('./WorkflowHeaderSectionsEditor', () => ({
  WorkflowHeaderSectionsEditor: () => <div>sections editor</div>,
}));

import WorkflowFormBuilder from './WorkflowFormBuilder';

function definition(draft_schema: unknown) {
  return {
    id: 'def-1',
    code: 'demo',
    name: 'Demo form',
    description: null,
    is_active: true,
    draft_schema,
    published_version_id: null,
  };
}

function renderBuilder(draft_schema: unknown) {
  useWorkflowDefinitionQuery.mockReturnValue({
    data: definition(draft_schema),
    isLoading: false,
  });
  return render(<WorkflowFormBuilder definitionId="def-1" />);
}

describe('WorkflowFormBuilder document-model gate', () => {
  it('refuses to edit a current-model document, and says why', async () => {
    renderBuilder({ schemaVersion: 1, pages: [{ id: 'p1', sections: [] }] });
    await waitFor(() =>
      expect(screen.getByText(/visual builder not available/i)).toBeInTheDocument(),
    );
    // The save that could only ever 422 is gone.
    expect(screen.queryByRole('button', { name: /save draft schema/i })).not.toBeInTheDocument();
  });

  it('reassures rather than alarms - nothing is broken or lost', async () => {
    // The form is fine; only this screen is out of date. Getting that wrong sends somebody
    // looking for a data problem that does not exist.
    renderBuilder({ schemaVersion: 1, pages: [] });
    await waitFor(() => expect(screen.getByText(/nothing has been lost/i)).toBeInTheDocument());
  });

  it('keeps the settings editable, because they are shape-independent', async () => {
    renderBuilder({ schemaVersion: 1, pages: [] });
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /save settings/i })).toBeInTheDocument(),
    );
  });

  it('still shows the editor for a legacy-shape document', async () => {
    // Turning the notice on for everything would remove the only working authoring path
    // from any definition still stored in the old shape.
    renderBuilder({ header_fields: [], header_sections: [], line_groups: [] });
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /save draft schema/i })).toBeInTheDocument(),
    );
    expect(screen.queryByText(/visual builder not available/i)).not.toBeInTheDocument();
  });

  it('treats an empty or absent draft as legacy, so a NEW form is still authorable', async () => {
    // A brand-new definition has no schema yet. Reading that as "current model" would make
    // every new form unauthorable from the moment it is created.
    for (const draft of [null, undefined, {}]) {
      const { unmount } = renderBuilder(draft);
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /save draft schema/i })).toBeInTheDocument(),
      );
      unmount();
    }
  });
});
