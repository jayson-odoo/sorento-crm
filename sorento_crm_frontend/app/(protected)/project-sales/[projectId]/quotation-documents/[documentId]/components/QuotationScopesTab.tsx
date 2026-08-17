'use client';

import * as React from 'react';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useQuotationDocumentMutations } from '../../../../_shared/hooks/useQuotationDocuments';
import { useQuotations } from '../../../../_shared/hooks/useProjects';
import { OutcomePill } from '../../../../_shared/components/OutcomePill';
import { QuotationDialog } from '../../../components/QuotationDialog';
import { QuotationOutcomeDialog } from '../../../components/QuotationOutcomeDialog';
import {
  QuotationVersionEditor,
  type QuotationScopeEditing,
} from '../../../components/QuotationVersionEditor';
import { useQuotationDocumentScreen } from './QuotationDocumentContext';
import { QuotationNameDialog } from './QuotationNameDialog';
import { QuotationScopeTabs } from './QuotationScopeTabs';

/**
 * The Scopes tab: the scope strip and the priced lines under whichever scope is open.
 *
 * Unchanged from the single-scroll screen it came out of, apart from where it now sits. The
 * document itself is not fetched here - it comes from the layout, so the tabs cannot end up with
 * two answers about the same quotation.
 *
 * The scope's LINES are not rebuilt here either. Lines hang off a version, the version editor
 * already owns that, and a second line table would eventually disagree with it about what is
 * frozen.
 */
export function QuotationScopesTab() {
  const {
    projectId,
    documentId,
    document: record,
    project,
    canEdit,
    activeScopeId,
    selectScope,
    edit,
  } = useQuotationDocumentScreen();
  // A scope IS a quotation row, and the line editor takes the full record. The project's quotation
  // list is already cached by the tab the user clicked in from, so resolving the open scope through
  // it costs nothing on the usual path.
  const quotations = useQuotations(projectId);
  const mutations = useQuotationDocumentMutations(projectId, documentId);

  const [decidingScopeId, setDecidingScopeId] = React.useState<string | null>(null);
  const [editingScopeId, setEditingScopeId] = React.useState<string | null>(null);
  const [addingScope, setAddingScope] = React.useState(false);

  const scopes = record.scopes ?? [];
  const activeScope = scopes.find((scope) => scope.id === activeScopeId) ?? scopes[0] ?? null;
  const activeQuotation =
    (quotations.data ?? []).find((row) => row.id === activeScope?.id) ?? null;

  /**
   * The open scope's edit handles, bound to its id.
   *
   * Nothing is held here. The staged lines live in the shell, because this panel unmounts the
   * moment the reader opens the terms tab and the work has to still be there when they come back.
   */
  const { isEditing, scopes: stagedScopes, seedScope, stageScope, toggleRemoved } = edit;
  const activeScopeIdForEdit = activeScope?.id ?? null;
  // Off the session's individual pieces rather than off the session object, which is rebuilt on
  // every render of the shell: an identity that churns per render would push a new `staging` into
  // the line table on every keystroke anywhere on the page.
  const scopeEditing = React.useMemo<QuotationScopeEditing | null>(() => {
    if (!isEditing || !activeScopeIdForEdit) return null;
    const scopeId = activeScopeIdForEdit;
    return {
      staged: stagedScopes[scopeId]?.lines ?? null,
      seed: (versionId, lines) => seedScope(scopeId, versionId, lines),
      stage: (lines) => stageScope(scopeId, lines),
      toggleRemoved: (key) => toggleRemoved(scopeId, key),
    };
  }, [activeScopeIdForEdit, isEditing, seedScope, stageScope, stagedScopes, toggleRemoved]);

  if (scopes.length === 0) {
    // Rendered, never hidden: a quotation with no scopes is a real state on the way to a priced
    // one. The way in is the empty state's own CTA now that adding lives at the end of the tab
    // strip - with no strip on screen there is nowhere else for it to be.
    return (
      <>
        <Card>
          <CardContent className="px-6 py-10 text-center">
            <h3 className="text-sm font-semibold">No scopes on this quotation yet</h3>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
              A scope is a part of the development priced on its own - the townhouses, the guard
              house, the reception.
            </p>
            {canEdit && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-4"
                onClick={() => setAddingScope(true)}
              >
                <Plus className="size-4" aria-hidden />
                Add a scope
              </Button>
            )}
          </CardContent>
        </Card>

        <AddScopeDialog
          open={addingScope}
          onOpenChange={setAddingScope}
          isSaving={mutations.addScope.isPending}
          onAdd={async (label) => {
            const scope = await mutations.addScope.mutateAsync({
              id: documentId,
              scopeLabel: label,
            });
            setAddingScope(false);
            selectScope(scope.id);
          }}
        />
      </>
    );
  }

  return (
    <div className="space-y-5">
      <QuotationScopeTabs
        scopes={scopes}
        activeScopeId={activeScope?.id ?? ''}
        onSelect={selectScope}
        canEdit={canEdit}
        onAddScope={() => setAddingScope(true)}
      />

      {activeQuotation ? (
        <Card>
          {/* The scope's own commercial result, beside the lines it applies to.
              Outcome is per SCOPE and the project's outcome is derived from it, so losing this
              control would leave a project permanently open with no way to say the townhouse was
              won. It used to live on the per-scope page, which the document screen replaced as the
              way in. */}
          <CardHeader className="flex flex-col items-start gap-3 border-b border-border sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <CardTitle className="min-w-0 break-words text-sm">
                {activeQuotation.scope_label}
              </CardTitle>
              <OutcomePill outcome={activeQuotation.outcome} />
              {/* Which series this scope is quoted from, stated rather than assumed.
                  Without it there is no way to tell a scope that IS being checked from one
                  that names no series and is therefore checking nothing - and every line in
                  both cases looks identically clean. A fact, not an explanation. */}
              <span className="text-xs text-muted-foreground">
                {activeQuotation.series_name || 'No series'}
              </span>
              {activeQuotation.loss_reason_label && (
                <span className="text-xs text-muted-foreground">
                  {activeQuotation.loss_reason_label}
                </span>
              )}
            </div>
            {canEdit && (
              <div className="flex flex-wrap items-center gap-2">
                {/* The SERIES this scope is quoted from, reachable from where the work
                    happens.

                    It was only ever editable on the per-scope page, and nothing in the app
                    links to that page any more - this document screen replaced it as the way
                    in. So the one control that decides whether a line counts as standard was
                    unreachable by clicking, which is why not one quotation in the database
                    has a series bound and every Non-standard flag on screen was stale. */}
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setEditingScopeId(activeQuotation.id)}
                >
                  Edit scope
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setDecidingScopeId(activeQuotation.id)}
                >
                  Record outcome
                </Button>
              </div>
            )}
          </CardHeader>
          {/* min-w-0 is load-bearing. CardContent is a flex item, and a flex item defaults to
              min-width:auto, so it refuses to shrink below its content: the 1,900px line table
              then stretched this Card and the whole PAGE scrolled sideways at phone width, instead
              of the table scrolling inside its own gutter. */}
          <CardContent className="min-w-0 py-5">
            {/* Keyed by scope so switching tabs gives the editor a clean instance rather than one
                still holding the previous scope's selected version. Nothing refetches: the
                versions and lines are already in the query cache, and the staged edits live in
                the shell, so a remount costs nothing and loses nothing. */}
            <QuotationVersionEditor
              key={activeQuotation.id}
              project={project}
              quotation={activeQuotation}
              edit={scopeEditing}
            />
          </CardContent>
        </Card>
      ) : quotations.isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <Card>
          <CardContent className="px-6 py-10 text-center">
            <h3 className="text-sm font-semibold">This scope could not be opened</h3>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
              Its lines are not available right now. Reload the page to try again.
            </p>
          </CardContent>
        </Card>
      )}

      {decidingScopeId && activeQuotation && (
        <QuotationOutcomeDialog
          project={project}
          quotation={activeQuotation}
          onDone={() => setDecidingScopeId(null)}
        />
      )}

      {/* The same dialog the orphaned per-scope page used, not a second copy of the form:
          the series picker is the thing that decides what counts as standard, and two
          implementations of it would eventually offer different lists. */}
      {editingScopeId && activeQuotation && (
        <QuotationDialog
          project={project}
          quotation={activeQuotation}
          onDone={() => setEditingScopeId(null)}
        />
      )}

      <AddScopeDialog
        open={addingScope}
        onOpenChange={setAddingScope}
        isSaving={mutations.addScope.isPending}
        onAdd={async (label) => {
          const scope = await mutations.addScope.mutateAsync({
            id: documentId,
            scopeLabel: label,
          });
          setAddingScope(false);
          // Land on what was just added rather than on whichever tab was open before.
          selectScope(scope.id);
        }}
      />
    </div>
  );
}

/** The strip's + and the empty state's CTA open the same dialog, so it is written once. */
function AddScopeDialog({
  open,
  onOpenChange,
  isSaving,
  onAdd,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isSaving: boolean;
  onAdd: (label: string) => Promise<void>;
}) {
  return (
    <QuotationNameDialog
      open={open}
      onOpenChange={onOpenChange}
      initialLabel={null}
      addTitle="Add a scope"
      renameTitle="Rename scope"
      fieldLabel="Scope name"
      placeholder="e.g. Townhouse, Guard house"
      hint="A part of the development priced on its own."
      isSaving={isSaving}
      onSave={async (label) => {
        try {
          await onAdd(label);
        } catch {
          // The mutation already toasted the reason. The dialog stays open holding the typed name,
          // so a rejected label can be corrected rather than retyped.
        }
      }}
    />
  );
}
