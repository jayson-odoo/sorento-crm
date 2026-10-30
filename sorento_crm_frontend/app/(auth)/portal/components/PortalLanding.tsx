'use client';

/**
 * Portal landing content - shared by the stable slug tree
 * (`/portal/c/{slug}`) and the legacy `/portal` tree (impersonation + old
 * links). All navigation goes through lib/portal-paths so links stay inside
 * the active tree. The list under the kind picker is `SubmissionList`, the
 * same body a salesperson's CRM list page renders for one kind (L2).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { AlertCircle, LogOut, MessageCircle, Star } from 'lucide-react';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from '@/lib/toast';
import { orderLandingKinds } from '@/lib/portal-form-kinds';
import {
  LANDING_KINDS,
  LANDING_LABELS,
  PortalContact,
  PortalLandingKind,
  PortalSubmissionSummary,
  PortalUnauthorizedError,
  clearPortalToken,
  fetchMeWithGrace,
  isLandingKind,
  portalLogout,
  readPortalToken,
} from '../lib/portal-client';
import { useSubmissionClient } from '../lib/submission-client';
import { MyTargetPanel } from './MyTargetPanel';
import { portalVerifyPath, waMeUrl } from '../lib/portal-paths';
import { SubmissionList, listKindSummaries, usePortalListView } from './SubmissionList';
import { CustomerAsksList } from './CustomerAsksList';
import { listCustomerAsks } from '../lib/customer-asks-service';
import { ConversationList } from './ConversationList';
import { listConversations } from '../lib/conversations-service';
import {
  DEFAULT_LANDING_SORT,
  type LandingFilters,
  type LandingSort,
} from '../lib/landing-fields';

// AC-L3: a contact whose overrides hide every kind gets a WhatsApp escape
// hatch rather than a blank landing.
const WA_NO_FORMS_TEXT = 'Hi, I would like to submit a form.';

/**
 * The dropdown's option list for THIS contact: every landing kind the
 * server's `visible_form_types` grants, in `LANDING_KINDS` order
 * (PLAN-portal-forms-market-segment D2/AC-L1). All five kinds are gated the
 * same way now - none is offered or fetched unconditionally. The server
 * enforces the same rule on every route regardless, so this only decides
 * what is offered, never what is allowed.
 */
function landingKindsFor(contact: PortalContact | null): PortalLandingKind[] {
  const visible = contact?.visible_form_types ?? [];
  return orderLandingKinds(visible);
}

const EMPTY_LISTS: Record<PortalLandingKind, PortalSubmissionSummary[]> = {
  complaint: [],
  stock_inquiry: [],
  purchase_request: [],
  sponsorship_form: [],
  project_registration: [],
  price_tag_request: [],
  sample_request: [],
  new_product_application: [],
  sales_opportunity: [],
  customer_asks: [],
  conversation: [],
};


export function PortalLanding({ slug, embedded = false }: { slug?: string; embedded?: boolean }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const client = useSubmissionClient();
  const [contact, setContact] = useState<PortalContact | null>(null);
  const [submissions, setSubmissions] =
    useState<Record<PortalLandingKind, PortalSubmissionSummary[]>>(EMPTY_LISTS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openAskCount, setOpenAskCount] = useState(0);
  const [conversationCount, setConversationCount] = useState(0);
  const {
    value: search,
    setValue: setSearch,
    debouncedValue: debouncedSearch,
    isSettling: searchSettling,
  } = useDebouncedSearch();
  const initialTabFromUrl = (() => {
    const t = searchParams?.get('type');
    return isLandingKind(t) ? t : null;
  })();
  // N1: null, not a hardcoded kind - a kind picked before `visible_form_types`
  // is known could be one this contact cannot see, and the fallback effect
  // below corrects it the moment `landingKinds` resolves. Seeding a value
  // absent from `options` for that one frame is worse than seeding none.
  const [activeTab, setActiveTab] =
    useState<PortalLandingKind | null>(initialTabFromUrl);
  // Filter + sort are component state that resets whenever the type changes
  // (D-L4) - the field set differs per kind, so a status or field value
  // picked for one kind has no business surviving a tab switch. The view
  // choice (cards vs list) is the one thing that persists, per device,
  // across both a reload and a type switch (AC-L7).
  const [filters, setFilters] = useState<LandingFilters>({});
  const [sort, setSort] = useState<LandingSort>(DEFAULT_LANDING_SORT);
  useEffect(() => {
    setFilters({});
    setSort(DEFAULT_LANDING_SORT);
  }, [activeTab]);
  // Cards is the default at EVERY width (R3-2, AC-R9) - the old viewport-based
  // default (list on `md:` and up) is gone. A stored choice still wins.
  const [view, setView] = usePortalListView();
  const userPickedTabRef = useRef<boolean>(Boolean(searchParams?.get('type')));
  // Mirror current URL `?type=` so loadAll's expired-token redirect can read it
  // without depending on `searchParams` (which would re-create loadAll and
  // break the debounced search).
  const typeQueryRef = useRef<string | null>(searchParams?.get('type') ?? null);
  useEffect(() => {
    typeQueryRef.current = searchParams?.get('type') ?? null;
  }, [searchParams]);

  const landingKinds = useMemo(() => landingKindsFor(contact), [contact]);

  // A `?type=` deep link, or a starred default, can name a kind this contact
  // does not hold - a link forwarded by a colleague, or a grant since
  // withdrawn. Fall back to the first visible kind rather than showing an
  // option whose list the server would refuse (AC-L2). An empty visible set
  // leaves nothing to fall back to - the empty state renders instead.
  useEffect(() => {
    if (!contact) return;
    if (landingKinds.length === 0) return;
    if (activeTab && landingKinds.includes(activeTab)) return;
    setActiveTab(landingKinds[0]);
  }, [contact, landingKinds, activeTab]);

  // Once the contact is known (and the URL has no `?type=` deep-link, and the
  // user hasn't manually switched tabs in this session), apply any default
  // tab the contact previously starred.
  useEffect(() => {
    if (!contact?.contact_id) return;
    if (userPickedTabRef.current) return;
    if (searchParams?.get('type')) return;
    if (typeof window === 'undefined') return;
    const stored = window.localStorage.getItem(
      `sorento.portalDefaultTab.${contact.contact_id}`,
    );
    if (isLandingKind(stored) && landingKinds.includes(stored)) {
      setActiveTab(stored);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contact?.contact_id, landingKinds]);

  // Embedded in the CRM with no `?type=`: put the kind shown into the URL, so the sidebar can
  // highlight exactly one MY REQUESTS item.
  const urlTypeSyncedRef = useRef(false);
  useEffect(() => {
    if (!embedded || urlTypeSyncedRef.current || !activeTab) return;
    urlTypeSyncedRef.current = true;
    if (searchParams?.get('type')) return;
    router.replace(`/my-requests?type=${activeTab}`);
  }, [embedded, activeTab, searchParams, router]);

  const handleTabChange = useCallback(
    (next: PortalLandingKind) => {
      userPickedTabRef.current = true;
      setActiveTab(next);
      // Embedded in the CRM: the URL names the kind shown, so the sidebar highlight follows.
      if (embedded) router.replace(`/my-requests?type=${next}`);
    },
    [embedded, router],
  );

  const defaultTabKey = useMemo(() => {
    if (!contact?.contact_id) return null;
    return `sorento.portalDefaultTab.${contact.contact_id}`;
  }, [contact?.contact_id]);

  const [savedDefaultTab, setSavedDefaultTab] =
    useState<PortalLandingKind | null>(null);
  useEffect(() => {
    if (!defaultTabKey || typeof window === 'undefined') {
      setSavedDefaultTab(null);
      return;
    }
    const stored = window.localStorage.getItem(defaultTabKey);
    setSavedDefaultTab(isLandingKind(stored) ? stored : null);
  }, [defaultTabKey]);

  const handleSetDefaultTab = useCallback(() => {
    if (!activeTab || !defaultTabKey || typeof window === 'undefined') return;
    window.localStorage.setItem(defaultTabKey, activeTab);
    setSavedDefaultTab(activeTab);
    toast.success(`${LANDING_LABELS[activeTab]} is now your default tab.`);
  }, [activeTab, defaultTabKey]);

  // Track whether the very first load has finished. Subsequent search
  // refetches must NOT flip `loading` back to true, otherwise the skeleton
  // remounts and the search Input loses focus on every keystroke.
  const initialLoadDone = useRef(false);

  // Keep tab in sync if the user navigates back with a different ?type=.
  useEffect(() => {
    const t = searchParams?.get('type');
    // `landingKinds.includes` too (the same guard the default-tab effect above uses):
    // `isLandingKind` only proves `t` is a valid tab kind at all (reviewer should-fix 9,
    // Phase 3: it does NOT match `sales_opportunity`, which has no tab here to begin
    // with) - `landingKinds` is the narrower, per-contact set this contact was actually
    // granted, which a `?type=` query param can name without ever having been offered.
    if (isLandingKind(t) && landingKinds.includes(t) && t !== activeTab) setActiveTab(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const loadAll = useCallback(
    async (q?: string) => {
      const existing = readPortalToken();
      if (!existing) {
        router.replace(portalVerifyPath({ slug: slug ?? null }));
        return;
      }
      const isInitial = !initialLoadDone.current;
      if (isInitial) setLoading(true);
      try {
        // fetchMeWithGrace absorbs the post-verify commit-visibility race
        // (fresh token transiently 401s) before bouncing back to verify.
        const me = await fetchMeWithGrace();
        setContact(me);
        // Every kind is gated the same way now (AC-L1): only ask for a list
        // the resolved `visible_form_types` actually grants, in canonical
        // order. Each kind answers its own endpoint in its own shape, so a
        // gated form beyond the four legacy ones brings its own adapter.
        const kinds = landingKindsFor(me);
        // allSettled, not all: the legs are independent lists and one of them
        // answering 403 or 500 used to reject the whole load, so the landing
        // showed its error screen and the rest of the kinds that answered
        // perfectly well were unreachable. A leg that fails is that kind empty.
        // Customer asks (fix round 5) is not a list of submissions: its body pages its own
        // rows (`CustomerAsksList`), so this leg only reads the open count for the badge.
        // A request kind's list is `listKindSummaries`, the call a CRM list page makes too (L2).
        const legs = await Promise.allSettled(
          kinds.map((k) =>
            k === 'customer_asks'
              ? listCustomerAsks({ page: 1, limit: 1, state: 'open', q }).then((page) => {
                  setOpenAskCount(page.pagination?.total ?? 0);
                  return [] as PortalSubmissionSummary[];
                })
              : k === 'conversation'
                // Same shape as Customer asks: the body (`ConversationList`) reads its own
                // rows, this leg only reads the count for the picker badge.
                ? listConversations({ page: 1, limit: 1, q }).then((page) => {
                    setConversationCount(page.pagination?.total ?? 0);
                    return [] as PortalSubmissionSummary[];
                  })
                : listKindSummaries(client, k, q),
          ),
        );

        // An expired token is not one kind failing - every leg would fail and
        // the answer is to re-verify - so it is rethrown to the handler below.
        const dead = legs.find(
          (leg) =>
            leg.status === 'rejected' &&
            leg.reason instanceof PortalUnauthorizedError,
        );
        if (dead && dead.status === 'rejected') throw dead.reason;

        // N4: derived from the canonical list rather than spreading the
        // module-level EMPTY_LISTS - a kind LANDING_KINDS gains cannot be
        // forgotten here the way a manually-enumerated copy could be.
        const next = Object.fromEntries(
          LANDING_KINDS.map((k) => [k, [] as PortalSubmissionSummary[]]),
        ) as Record<PortalLandingKind, PortalSubmissionSummary[]>;
        kinds.forEach((k, index) => {
          const leg = legs[index];
          if (leg.status === 'fulfilled') {
            next[k] = leg.value;
          } else {
            console.warn('Portal landing: one list failed to load', leg.reason);
          }
        });
        setSubmissions(next);
        setError(null);
        // Token validated - clear the freshness stamp so subsequent transient
        // 401s (e.g. real expiry) bounce back immediately without retry.
        if (typeof window !== 'undefined') {
          window.sessionStorage.removeItem('sorento.portalTokenWrittenAt');
        }
      } catch (e) {
        if (e instanceof PortalUnauthorizedError) {
          // Token expired/revoked. The slug tree recovers identity from the
          // slug itself; the legacy tree forwards the dead token so
          // /portal/verify can look up contact/space via /token-info.
          router.replace(
            portalVerifyPath({
              slug: slug ?? null,
              reason: 'expired',
              token: existing,
              type: typeQueryRef.current,
            }),
          );
          return;
        }
        setError(e instanceof Error ? e.message : 'Failed to load portal.');
      } finally {
        if (isInitial) {
          setLoading(false);
          initialLoadDone.current = true;
        }
      }
    },
    [router, slug, client],
  );

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  // Debounced refetch when the user types in the search box (M6-06:
  // useDebouncedSearch, the shared 200ms standard); backend now does the
  // field-spanning search so the result reflects every column (product,
  // metadata, doc number, etc.).
  useEffect(() => {
    void loadAll(debouncedSearch);
  }, [debouncedSearch, loadAll]);

  const totals = useMemo(() => {
    const out: Record<PortalLandingKind, number> = {
      complaint: 0,
      stock_inquiry: 0,
      purchase_request: 0,
      sponsorship_form: 0,
      project_registration: 0,
      price_tag_request: 0,
      sample_request: 0,
      new_product_application: 0,
      sales_opportunity: 0,
      customer_asks: 0,
      conversation: 0,
    };
    for (const t of landingKinds) out[t] = submissions[t]?.length ?? 0;
    // Its badge is the open count, not a row count (asks are paged server-side).
    out.customer_asks = openAskCount;
    out.conversation = conversationCount;
    return out;
  }, [submissions, landingKinds, openAskCount, conversationCount]);

  const handleLogout = useCallback(async () => {
    const t = readPortalToken();
    // Revoke server-side first (best-effort) - clearing storage alone would
    // leave a copied token valid until expiry.
    try {
      await portalLogout();
    } catch {
      // best-effort
    }
    clearPortalToken();
    const qs = !slug && t ? t : null;
    router.replace(
      portalVerifyPath({ slug: slug ?? null, reason: 'logout', token: qs }),
    );
  }, [router, slug]);

  if (loading) {
    return (
      <div className="w-full max-w-3xl mx-auto px-3 pt-4 pb-4 space-y-3">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-full max-w-3xl mx-auto px-3 pt-4 pb-4 space-y-3">
        <Alert variant="destructive">
          <AlertIcon>
            <AlertCircle />
          </AlertIcon>
          <AlertTitle>{error}</AlertTitle>
        </Alert>
        <Button
          variant="outline"
          onClick={() =>
            router.replace(portalVerifyPath({ slug: slug ?? null }))
          }
        >
          Verify with OTP
        </Button>
      </div>
    );
  }

  // The tab actually rendered below: `activeTab` can be null for the one
  // frame before the fallback effect above corrects it (N1); `landingKinds[0]`
  // is always defined once this render reaches the non-empty branch, so the
  // final `?? 'complaint'` is a type satisfier only, never actually reached.
  const currentTab: PortalLandingKind = activeTab ?? landingKinds[0] ?? 'complaint';

  return (
    <div className="w-full max-w-3xl mx-auto px-3 pt-3 pb-4 space-y-3">
      {/* Header - Welcome centered, Log out anchored to top-right. Not shown inside the CRM shell. */}
      {!embedded && (
        <div className="relative flex items-center justify-center min-h-[2.75rem]">
          <h1 className="text-lg font-semibold text-center break-words px-12">
            Welcome{contact?.name ? `, ${contact.name}` : ''}
          </h1>
          <Button
            variant="outline"
            size="sm"
            onClick={handleLogout}
            className="absolute right-0 top-1/2 -translate-y-1/2 h-9 px-2.5"
            aria-label="Log out"
            title="Log out"
          >
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      )}

      {landingKinds.length === 0 ? (
        // AC-L3/AC-L5: no picker, toolbar, list or search box - just the one
        // next step this contact has left. Same shape as the per-kind empty
        // card below (icon, py-8).
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground space-y-2">
            <MessageCircle className="h-8 w-8 mx-auto" />
            <p>No forms are available for your account.</p>
            {contact?.whatsapp_number ? (
              <Button asChild>
                <a
                  href={waMeUrl(contact.whatsapp_number, WA_NO_FORMS_TEXT)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <MessageCircle className="h-4 w-4 mr-2" />
                  Chat with us on WhatsApp
                </a>
              </Button>
            ) : (
              // No WhatsApp number on file - Log out (already the header's
              // own action) is the only next step left to offer, rather than
              // nothing.
              <Button variant="outline" onClick={handleLogout}>
                <LogOut className="h-4 w-4 mr-2" />
                Log out
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Search input only (D-L3) - the status filter now lives in the
              toolbar's Filter popover, alongside every other filterable field. */}
          <ListSearchInput
            value={search}
            onChange={setSearch}
            isSettling={searchSettling}
            placeholder="Search..."
            aria-label="Search submissions"
            className="w-full"
            inputClassName="h-12 text-base"
          />

          <div className="flex items-stretch gap-2">
            <SearchableSelect
              value={currentTab}
              onChange={(v) => handleTabChange(v as PortalLandingKind)}
              options={landingKinds.map((t) => ({
                value: t,
                label: LANDING_LABELS[t],
              }))}
              size="lg"
              triggerClassName="flex-1 min-h-12 text-base"
              renderTriggerLabel={(opt) => {
                const t = opt.value as PortalLandingKind;
                return (
                  <span className="flex items-center gap-2">
                    {LANDING_LABELS[t]}
                    <Badge variant="secondary" className="px-1.5 py-0 text-xs">
                      {totals[t]}
                    </Badge>
                    {savedDefaultTab === t && (
                      <Star
                        className="h-3.5 w-3.5 fill-yellow-400 text-yellow-500 shrink-0"
                        aria-label="default"
                      />
                    )}
                  </span>
                );
              }}
              renderOption={(opt) => {
                const t = opt.value as PortalLandingKind;
                return (
                  <span className="flex items-center gap-2">
                    {LANDING_LABELS[t]}
                    <Badge variant="secondary" className="px-1.5 py-0 text-xs">
                      {totals[t]}
                    </Badge>
                    {savedDefaultTab === t && (
                      <Star
                        className="h-3.5 w-3.5 fill-yellow-400 text-yellow-500 shrink-0"
                        aria-label="default"
                      />
                    )}
                  </span>
                );
              }}
            />
            <Button
              type="button"
              variant="outline"
              onClick={handleSetDefaultTab}
              disabled={!contact || savedDefaultTab === currentTab}
              aria-label={
                savedDefaultTab === currentTab
                  ? `${LANDING_LABELS[currentTab]} is your default tab`
                  : `Set ${LANDING_LABELS[currentTab]} as default tab`
              }
              title={
                savedDefaultTab === currentTab
                  ? 'Default tab'
                  : 'Set as default for this contact'
              }
              className="h-12 px-3"
            >
              <Star
                className={`h-4 w-4 ${
                  savedDefaultTab === currentTab
                    ? 'fill-yellow-400 text-yellow-500'
                    : ''
                }`}
              />
            </Button>
          </div>

          {/* F2: the logging agent's own target progress, at the top of the kind. */}
          {currentTab === 'sales_opportunity' ? <MyTargetPanel slug={slug} /> : null}

          {currentTab === 'customer_asks' ? (
            <CustomerAsksList
              search={debouncedSearch}
              contactId={contact?.contact_id}
              view={view}
              onViewChange={setView}
            />
          ) : currentTab === 'conversation' ? (
            <ConversationList
              search={debouncedSearch}
              contactId={contact?.contact_id}
              view={view}
              onViewChange={setView}
            />
          ) : (
            <SubmissionList
              kind={currentTab}
              items={submissions[currentTab] ?? []}
              filters={filters}
              onFiltersChange={setFilters}
              sort={sort}
              onSortChange={setSort}
              view={view}
              onViewChange={setView}
              slug={slug}
              search={search}
              onClearSearch={() => setSearch('')}
              embedded={embedded}
            />
          )}
        </>
      )}
    </div>
  );
}
