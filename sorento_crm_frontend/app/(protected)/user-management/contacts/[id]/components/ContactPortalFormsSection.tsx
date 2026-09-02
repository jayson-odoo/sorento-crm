'use client';

import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { portalFormKindLabel } from '@/lib/portal-form-kinds';

import {
  useContactPortalForms,
  useUpdateContactPortalForm,
} from '../hooks/useContactPortalForms';

type OverrideChoice = 'inherit' | 'show' | 'hide';

const CHOICE_OPTIONS: SearchableSelectOption[] = [
  { value: 'inherit', label: 'Inherit from access types' },
  { value: 'show', label: 'Always show' },
  { value: 'hide', label: 'Always hide' },
];

function choiceFor(override: boolean | null): OverrideChoice {
  if (override === true) return 'show';
  if (override === false) return 'hide';
  return 'inherit';
}

function isEnabledFor(choice: OverrideChoice): boolean | null {
  if (choice === 'show') return true;
  if (choice === 'hide') return false;
  return null;
}

/**
 * Contact Details -> Portal forms.
 *
 * Only GATED form kinds are listed (today: price_tag_request). The four legacy
 * submission kinds are always on the portal landing regardless of access type,
 * so they are never part of this control.
 */
export default function ContactPortalFormsSection({ contactId }: { contactId: string }) {
  const { data, isLoading, isError } = useContactPortalForms(contactId);
  const update = useUpdateContactPortalForm(contactId);

  const rows = data?.forms ?? [];

  if (isLoading) {
    return (
      <div>
        <p className="text-sm text-muted-foreground mb-1">Portal forms</p>
        <Skeleton className="h-6 w-48" />
      </div>
    );
  }

  if (isError) {
    return (
      <div>
        <p className="text-sm text-muted-foreground mb-1">Portal forms</p>
        <p className="text-sm text-destructive">
          Portal forms could not be loaded. Reload the page to try again.
        </p>
      </div>
    );
  }

  return (
    <div>
      <p className="text-sm text-muted-foreground mb-1">Portal forms</p>
      {rows.length === 0 ? (
        <p className="font-medium text-muted-foreground">No gated forms configured</p>
      ) : (
        <div className="flex flex-col gap-2">
          {rows.map((row) => {
            const choice = choiceFor(row.override);
            return (
              <div key={row.form_type} className="flex flex-col gap-1.5 rounded-md border p-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-medium break-words">{portalFormKindLabel(row.form_type)}</span>
                  <Badge variant={row.effective ? 'success' : 'secondary'} className="font-normal shrink-0">
                    {row.effective ? 'Visible' : 'Hidden'}
                  </Badge>
                </div>
                <SearchableSelect
                  value={choice}
                  onChange={(value) =>
                    update.mutate({
                      formType: row.form_type,
                      isEnabled: isEnabledFor(value as OverrideChoice),
                    })
                  }
                  options={CHOICE_OPTIONS}
                  disabled={update.isPending}
                  size="sm"
                  triggerClassName="w-full"
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
