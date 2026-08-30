'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { FileText, ListOrdered, LoaderCircleIcon, Move, SquarePen } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardHeader,
  CardHeading,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { StockTransfersPanel } from '@/app/(protected)/inventory-management/stock-transfers/components/StockTransfersPanel';
import { Textarea } from '@/components/ui/textarea';
import {
  SearchableSelect,
  type SearchableSelectOption,
} from '@/components/common/SearchableSelect';
import SalesOrdersGrid from '@/app/(protected)/scm/sales-orders/components/SalesOrdersGrid';
import { getContactSelect } from '../../services/salesAgentService';
import { useAnnotateSalesAgent, useSalesAgent } from '../../hooks/useSalesAgents';
import { DEMAND_CLASS_OPTIONS, demandClassLabel } from '../../lib/demandClass';
import { salesAgentSourceLabel } from '../../lib/salesAgentSource';
import DetailActions from '@/components/common/DetailActions';
import BackToList from '@/components/common/BackToList';
import { salesAgentsPagerQuery } from '../../hooks/useSalesAgents';
import type { SalesAgent } from '../../types/salesAgent.types';

/**
 * The sales-agent record, built to mirror `SalesOrderDetail` section for section: the same
 * header card (subject, status pill, prev/next, the primary action, the way out), the same
 * `variant="line"` tab strip below it, the same two-column cards, and the same "every section
 * is rendered, with an explicit empty state" rule.
 *
 * Mirrored deliberately. An agent is read from the same menu as an order and answers the
 * neighbouring question, so a reader who has learnt where a field lives on one has learnt it
 * on the other.
 *
 * VIEW AND EDIT ARE THE SAME SCREEN. Editing swaps a read-only value for an input IN PLACE -
 * same tabs, same cards, same fields, same order. Editable: Person, Demand class, Location
 * group, Linked portal contact, Active, Follow up, Internal note. The agent CODE is not: it is what the documents
 * state, and changing it would strand every order that names it. Source is not either: it is
 * a record of how the row got here.
 *
 * THERE IS NO CREATE AND NO DELETE, here as on the list. A row appears when an upload meets a
 * code nobody holds, and deleting one would orphan the orders that name it.
 */

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  /** Set while editing, so the label associates with the input it now wraps - the same
   *  label text either way. */
  htmlFor?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      {htmlFor ? (
        <label htmlFor={htmlFor} className="text-xs text-muted-foreground">
          {label}
        </label>
      ) : (
        <span className="text-xs text-muted-foreground">{label}</span>
      )}
      <span className="text-sm font-medium">{children}</span>
    </div>
  );
}

export function SalesAgentDetail({ id }: { id: string }) {
  const { data, isLoading, isError } = useSalesAgent(id);
  const searchParams = useSearchParams();

  const annotate = useAnnotateSalesAgent();

  const [isEditing, setIsEditing] = useState(false);
  const [personLabel, setPersonLabel] = useState('');
  const [demandClass, setDemandClass] = useState('');
  const [locationGroup, setLocationGroup] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [followUp, setFollowUp] = useState(false);
  const [internalNote, setInternalNote] = useState('');
  const [contactId, setContactId] = useState('');
  const [tab, setTab] = useState('general');

  // Contacts, searched on the server rather than capped at a page: the book runs to
  // thousands of people and the salesperson being linked is rarely in the first 20.
  const fetchContacts = useCallback(async (query: string) => {
    const items = await getContactSelect(query);
    return items.map((c) => ({
      value: c.id,
      label: c.name,
      description: c.masked_phone ?? undefined,
    }));
  }, []);

  const beginEdit = (agent: SalesAgent) => {
    setPersonLabel(agent.person_label ?? '');
    setDemandClass(agent.demand_class ?? '');
    setLocationGroup(agent.location_group ?? '');
    setIsActive(agent.is_active);
    setFollowUp(agent.follow_up);
    setInternalNote(agent.internal_note ?? '');
    setContactId(agent.contact_id ?? '');
    setIsEditing(true);
  };

  const cancelEdit = () => setIsEditing(false);

  // `?edit=1` opens the session on arrival, so a link and a bookmark land in the same place.
  // Fired once: re-running it after Cancel would put the user straight back into the session
  // they just left.
  const wantsEdit = searchParams.get('edit') === '1';
  const opened = useRef(false);
  useEffect(() => {
    if (!wantsEdit || opened.current || !data) return;
    opened.current = true;
    beginEdit(data);
  }, [wantsEdit, data]);

  // Back carries the list query the row click wrote (S3-01).
  const backLink = (
    <BackToList
      listPath="/master-data-management/sales-agents"
      label="Back to sales agents"
    />
  );

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="flex justify-end">{backLink}</div>
        <Skeleton className="h-32 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="space-y-4">
        <div className="flex justify-end">{backLink}</div>
        <Card className="flex flex-col items-center gap-3 p-10 text-center">
          <div className="text-sm font-semibold">Sales agent not found</div>
          <p className="max-w-md text-sm text-muted-foreground">
            This sales agent doesn&apos;t exist, or it was removed after this link was made.
            Head back to the list to pick another.
          </p>
        </Card>
      </div>
    );
  }

  const agent = data;

  const selectedContact: SearchableSelectOption | undefined =
    agent.contact_id && agent.contact_id === contactId
      ? { value: agent.contact_id, label: agent.contact_name ?? 'Linked contact' }
      : undefined;

  const handleSave = async () => {
    const trimmedLabel = personLabel.trim();
    const trimmedGroup = locationGroup.trim();
    const trimmedNote = internalNote.trim();
    try {
      await annotate.mutateAsync({
        id: agent.id,
        data: {
          person_label: trimmedLabel ? trimmedLabel : null,
          demand_class: demandClass ? demandClass : null,
          // Upper-cased on save so a typed `bb` still compares equal to the suffix a
          // warehouse code like `BRW-BB` carries.
          location_group: trimmedGroup ? trimmedGroup.toUpperCase() : null,
          is_active: isActive,
          follow_up: followUp,
          internal_note: trimmedNote ? trimmedNote : null,
          // Which debtors this salesperson may pick from on a price tag request.
          contact_id: contactId ? contactId : null,
        },
      });
      setIsEditing(false);
    } catch {
      // The mutation already toasted the reason; leave the session open so nothing typed
      // is lost and the refused field can be corrected in place.
    }
  };

  return (
    <div className="space-y-4">
      {/* The record header - what the agent IS, and what can be done to it. Above the tabs,
          because it belongs to the whole record rather than to any one of its concerns. */}
      <Card>
        <CardHeader className="block py-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              <CardTitle className="text-lg">{agent.sales_agent}</CardTitle>
              <Badge
                variant={agent.is_active ? 'success' : 'secondary'}
                appearance="light"
                size="md"
              >
                {agent.is_active ? 'Active' : 'Inactive'}
              </Badge>
            </div>
            {/* In an edit session the header states ONE intent: Save or Cancel. Nav and the
                way out act on the record as it is STORED, and offering them over a screen of
                unsaved changes is offering to act on something nobody is reading. */}
            {isEditing ? (
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <span className="text-xs text-muted-foreground">
                  Nothing is written until you press Save.
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={cancelEdit}
                  disabled={annotate.isPending}
                >
                  Cancel
                </Button>
                <Button size="sm" onClick={handleSave} disabled={annotate.isPending}>
                  {annotate.isPending ? (
                    <LoaderCircleIcon className="me-2 size-4 animate-spin" />
                  ) : null}
                  Save
                </Button>
              </div>
            ) : (
              <DetailActions
                pager={{
                  ...salesAgentsPagerQuery,
                  detailPath: '/master-data-management/sales-agents',
                  currentId: id,
                  ariaLabel: 'sales agent',
                }}
                primary={
                  <Button
                    variant="primary"
                    size="sm"
                    className="gap-1.5"
                    onClick={() => beginEdit(agent)}
                  >
                    <SquarePen className="size-4" />
                    Edit
                  </Button>
                }
              />
            )}
          </div>
        </CardHeader>
      </Card>

      {/* One tab per concern of the record, the same shape as the sales-order page. The tab
          set is the SAME in view and in edit. */}
      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList variant="line" className="mb-4 w-full justify-start overflow-x-auto">
          <TabsTrigger value="general">
            <FileText />
            <span>General</span>
          </TabsTrigger>
          <TabsTrigger value="sales-orders">
            <ListOrdered />
            <span>Sales orders</span>
          </TabsTrigger>
          <TabsTrigger value="transfers">
            <Move />
            <span>Transfers</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="general" className="mt-0 space-y-4 focus-visible:outline-none">
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Agent</CardTitle>
              </CardHeading>
            </CardHeader>
            <section aria-label="Agent" className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2">
              {/* Not editable, in either view: the code is what the documents state, and
                  changing it would strand every order that names it. */}
              <Field label="Agent code">{agent.sales_agent}</Field>
              <Field label="Person" htmlFor={isEditing ? 'sa-edit-person' : undefined}>
                {isEditing ? (
                  <Input
                    id="sa-edit-person"
                    value={personLabel}
                    onChange={(e) => setPersonLabel(e.target.value)}
                    // The column is varchar(100) and the backend refuses more; stop it here
                    // so the limit is felt while typing rather than as a rejected save.
                    maxLength={100}
                    placeholder="Who this code belongs to"
                    className="h-8"
                  />
                ) : (
                  agent.person_label || <span className="text-muted-foreground">Not set</span>
                )}
              </Field>
              <Field label="Demand class" htmlFor={isEditing ? 'sa-edit-demand-class' : undefined}>
                {isEditing ? (
                  <SearchableSelect
                    id="sa-edit-demand-class"
                    value={demandClass}
                    onChange={setDemandClass}
                    options={DEMAND_CLASS_OPTIONS}
                    // Unset is a real choice - "not a project" and "nobody said" mean
                    // opposite things - so the select must be able to get back to it.
                    clearable
                    placeholder="Not set"
                    emptyMessage="No demand classes."
                    size="sm"
                  />
                ) : agent.demand_class ? (
                  <Badge variant="info" appearance="light" size="md">
                    {demandClassLabel(agent.demand_class)}
                  </Badge>
                ) : (
                  <span className="text-muted-foreground">Not set</span>
                )}
              </Field>
              <Field
                label="Location group"
                htmlFor={isEditing ? 'sa-edit-location-group' : undefined}
              >
                {isEditing ? (
                  // Free text, not a closed vocabulary like the class: a new ownership group
                  // is a warehouse-code suffix somebody starts using, not a word the policy
                  // has to already know.
                  <Input
                    id="sa-edit-location-group"
                    value={locationGroup}
                    onChange={(e) => setLocationGroup(e.target.value)}
                    maxLength={16}
                    placeholder="Not set"
                    className="h-8"
                  />
                ) : agent.location_group ? (
                  <Badge variant="secondary" appearance="light" size="md">
                    {agent.location_group}
                  </Badge>
                ) : (
                  <span className="text-muted-foreground">Not set</span>
                )}
              </Field>
              <Field
                label="Linked portal contact"
                htmlFor={isEditing ? 'sa-edit-contact' : undefined}
              >
                {isEditing ? (
                  <SearchableSelect
                    id="sa-edit-contact"
                    value={contactId}
                    onChange={setContactId}
                    fetchOptions={fetchContacts}
                    // The row already carries the linked person's NAME, so the trigger
                    // reads it without a round trip and keeps reading it while the search
                    // is showing some other page.
                    selectedOption={selectedContact}
                    clearable
                    placeholder="Not linked"
                    emptyMessage="No contacts match."
                    size="sm"
                  />
                ) : (
                  agent.contact_name || (
                    <span className="text-muted-foreground">Not linked</span>
                  )
                )}
              </Field>
              {/* How the row got here. A record of what happened, so it reads the same in
                  both views and nothing moves between them. */}
              <Field label="Source">
                <Badge variant="secondary" appearance="light" size="md">
                  {salesAgentSourceLabel(agent.source)}
                </Badge>
              </Field>
              <Field label="Active" htmlFor={isEditing ? 'sa-edit-active' : undefined}>
                {isEditing ? (
                  <Switch id="sa-edit-active" checked={isActive} onCheckedChange={setIsActive} />
                ) : (
                  <span>{agent.is_active ? 'Active' : 'Inactive'}</span>
                )}
              </Field>
              <Field label="Follow up" htmlFor={isEditing ? 'sa-edit-follow-up' : undefined}>
                {isEditing ? (
                  <Switch
                    id="sa-edit-follow-up"
                    checked={followUp}
                    onCheckedChange={setFollowUp}
                  />
                ) : (
                  <span>{agent.follow_up ? 'Yes' : 'No'}</span>
                )}
              </Field>
            </section>
          </Card>

          {/* Always rendered, because a blank panel says "there is no note" where a missing
              panel says nothing at all. */}
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Notes</CardTitle>
              </CardHeading>
            </CardHeader>
            <section aria-label="Notes" className="grid grid-cols-1 gap-4 p-4">
              <Field label="Internal note" htmlFor={isEditing ? 'sa-edit-note' : undefined}>
                {isEditing ? (
                  <Textarea
                    id="sa-edit-note"
                    value={internalNote}
                    onChange={(e) => setInternalNote(e.target.value)}
                    rows={4}
                    placeholder="Not set"
                  />
                ) : agent.internal_note ? (
                  <span className="whitespace-pre-wrap font-normal">{agent.internal_note}</span>
                ) : (
                  <span className="text-muted-foreground">Not set</span>
                )}
              </Field>
            </section>
          </Card>
        </TabsContent>

        <TabsContent value="sales-orders" className="mt-0 focus-visible:outline-none">
          {/* THE sales-order table, pinned to this agent - the same component the Sales
              Orders list is, so the two cannot word a status or total two ways. Its own
              search, filters, columns and footer come with it. */}
          <SalesOrdersGrid
            salesAgentId={agent.id}
            // A real key, not the route: the path carries the agent's id, so keying off it
            // would give every agent their own saved column layout.
            listingKey="master_data.sales_agents.view::sales-orders"
          />
        </TabsContent>

        {/* AC-E6: every stock movement raised for this agent's orders. The SAME grid the
            Transfers page is, pinned to this agent, so the two cannot word a state twice. */}
        <TabsContent value="transfers" className="mt-0 focus-visible:outline-none">
          <StockTransfersPanel
            salesAgentId={agent.id}
            listingKey="master_data.sales_agents.view::stock-transfers"
            showFilters={false}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default SalesAgentDetail;
