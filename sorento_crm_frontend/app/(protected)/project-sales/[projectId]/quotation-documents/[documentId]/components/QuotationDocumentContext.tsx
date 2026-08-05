'use client';

import * as React from 'react';
import type {
  QuotationDocument,
  QuotationIssue,
  QuotationSignatureRecord,
} from '../../../../_shared/services/quotationDocumentService';
import type { Project } from '../../../../_shared/types/project.types';

/**
 * Everything the tabs of one quotation document share.
 *
 * The document is fetched ONCE, by the layout shell, and handed down here. A tab that fetched it
 * again would be a second opinion about the same record, and two tabs disagreeing about a total is
 * exactly the kind of thing a customer notices before we do.
 *
 * This is also the home for state that must outlive a tab switch. Routing the tabs means the
 * panels unmount when the user leaves them, so anything held inside a panel dies with it: the open
 * scope, the signature just captured, and (next) the staged edits of the edit view all live here
 * instead.
 */
export type QuotationDocumentScreen = {
  projectId: string;
  documentId: string;
  /** The server's record, already resolved: the shell renders a skeleton until it is. */
  document: QuotationDocument;
  project: Project;
  canEdit: boolean;
  /** Newest first at source, so this is the revision the customer currently holds. */
  latestIssue: QuotationIssue | null;
  /** Our signature, from the record or from the one captured on this screen. */
  sorentoSignature: QuotationSignatureRecord | null;
  /** The scope the Scopes tab has open. Held here so leaving the tab does not lose it. */
  activeScopeId: string | null;
  selectScope: (scopeId: string) => void;
  /**
   * What the line editor reports as the open scope's uncommitted total, so the header outside it
   * cannot disagree with the footer inside it.
   */
  reportScopeTotal: (scopeId: string, total: string | null) => void;
  /** Drop the live figure: it belongs to a mounted editor and means nothing without one. */
  clearScopeTotal: () => void;
};

const QuotationDocumentContext = React.createContext<QuotationDocumentScreen | undefined>(
  undefined,
);

export function QuotationDocumentProvider({
  value,
  children,
}: {
  value: QuotationDocumentScreen;
  children: React.ReactNode;
}) {
  return (
    <QuotationDocumentContext.Provider value={value}>{children}</QuotationDocumentContext.Provider>
  );
}

export function useQuotationDocumentScreen(): QuotationDocumentScreen {
  const context = React.useContext(QuotationDocumentContext);
  if (!context) {
    throw new Error(
      'useQuotationDocumentScreen must be used inside the quotation document layout',
    );
  }
  return context;
}
