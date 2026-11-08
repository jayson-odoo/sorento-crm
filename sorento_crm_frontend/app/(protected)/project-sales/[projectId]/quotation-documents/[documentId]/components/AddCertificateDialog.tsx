'use client';

import * as React from 'react';

import { FormDialogScaffold } from '@/components/common/FormDialogScaffold';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Label } from '@/components/ui/label';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useCertificates } from '@/app/(protected)/master-data-management/certificates/hooks/useCertificates';

import { useQuotationCertificateMutations } from '../../../../_shared/hooks/useQuotationCertificates';

const PAGE_SIZE = 50;

/** Add certificate: one pick from the certificate register. */
export function AddCertificateDialog({
  open,
  onOpenChange,
  projectId,
  documentId,
  listed,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  documentId: string;
  /** Certificates already on the list: left out of the options. */
  listed: Set<string>;
}) {
  const [picked, setPicked] = React.useState('');
  // The register is searched on the server as the user types, so no certificate is out of reach.
  const search = useDebouncedSearch();
  const register = useCertificates({
    pageIndex: 0,
    pageSize: PAGE_SIZE,
    sorting: [],
    searchQuery: search.debouncedValue,
    status: 'active',
  });
  const { add } = useQuotationCertificateMutations(projectId, documentId);
  const id = React.useId();

  const options = React.useMemo(
    () =>
      (register.data?.data ?? [])
        .filter((c) => !listed.has(c.id))
        .map((c) => ({
          value: c.id,
          label: `${c.scheme} ${c.certificate_number}`,
          description: c.title ?? undefined,
        })),
    [register.data, listed],
  );

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!picked) return;
    add.mutate(picked, {
      onSuccess: () => {
        setPicked('');
        onOpenChange(false);
      },
    });
  };

  return (
    <FormDialogScaffold
      open={open}
      onOpenChange={onOpenChange}
      title="Add certificate"
      submitLabel="Add"
      isPending={add.isPending}
      error={register.error ? 'Could not load the certificates' : null}
      onSubmit={submit}
    >
      <div className="flex flex-col gap-1">
        <Label htmlFor={id}>Certificate</Label>
        <SearchableSelect
          id={id}
          value={picked}
          onChange={setPicked}
          options={options}
          onSearchChange={search.setValue}
          placeholder="Pick a certificate"
          clearable
        />
      </div>
    </FormDialogScaffold>
  );
}
