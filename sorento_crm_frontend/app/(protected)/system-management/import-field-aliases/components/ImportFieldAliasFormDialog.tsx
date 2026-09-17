'use client';

import { useCallback, useEffect, useState } from 'react';
import { LoaderCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { getFulfilmentSuppliers } from '@/app/(protected)/scm/services/fulfilmentService';
import { useCreateImportFieldAlias, useImportFieldAliasFields } from '../hooks/useImportFieldAliases';
import type { ImportFieldAliasDocType } from '../types/importFieldAlias.types';

//: The word list is per-supplier (D6, `PLAN-stock-list-bare-model-codes.md`); every other
//: doc type's mapping is shared, so this select is scoped to that one doc type alone.
const WORD_DOC_TYPE: ImportFieldAliasDocType = 'supplier_inventory_word';

//: A word row's field is an OPEN, shape-validated token (review round 1, item 4) - not a
//: closed list - so the owner can type `HP` for a newly-named word without a code change.
//: Uppercased on write, mirroring the backend's own `WORD_TOKEN_RE`.
const WORD_TOKEN_INPUT_RE = /[^A-Z0-9]/g;

/**
 * Server-searched, paged supplier lookup for the word doc type's Supplier field (review
 * round 1, item 5) - the bare `/select` endpoint caps at 100 of the 743 live suppliers.
 * `getFulfilmentSuppliers` already matches `SearchableSelect`'s own `fetchOptions(query,
 * pageIndex)` contract; wrapped in a hook so this dialog can gate it off `enabled` (`false`
 * outside the word doc type resolves to no options with no request - other doc types must
 * never call the procurement route at all).
 */
function useSupplierWordFetchOptions(enabled: boolean) {
  return useCallback(
    (query: string, pageIndex: number): Promise<SearchableSelectOption[]> =>
      enabled ? getFulfilmentSuppliers(query, pageIndex) : Promise.resolve([]),
    [enabled],
  );
}

/**
 * Add mapping (AC-E3): the field is a `SearchableSelect` over E1's field list, the alias
 * is the header text as the supplier wrote it, locale is optional. Doc type is locked to
 * whatever the page's own filter is showing - a mapping always belongs to one reader.
 */
export function ImportFieldAliasFormDialog({
  open,
  onOpenChange,
  docType,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  docType: ImportFieldAliasDocType;
}) {
  const fields = useImportFieldAliasFields(docType);
  const create = useCreateImportFieldAlias(docType);
  const isWordDocType = docType === WORD_DOC_TYPE;
  const supplierFetchOptions = useSupplierWordFetchOptions(isWordDocType);
  const [field, setField] = useState('');
  const [alias, setAlias] = useState('');
  const [locale, setLocale] = useState('');
  const [supplierId, setSupplierId] = useState('');
  const [supplierOption, setSupplierOption] = useState<SearchableSelectOption | null>(null);

  useEffect(() => {
    if (open) {
      setField('');
      setAlias('');
      setLocale('');
      setSupplierId('');
      setSupplierOption(null);
    }
  }, [open]);

  const fieldOptions = (fields.data ?? []).map((f) => ({ value: f.field, label: f.label }));
  const canSave = !!field && alias.trim().length > 0;

  const submit = async () => {
    if (!canSave) return;
    try {
      await create.mutateAsync({
        field,
        alias: alias.trim(),
        locale: locale.trim() || null,
        // NULL = a shared row, answering for every supplier (D6) - only meaningful for the
        // word doc type, so every other doc type's create call carries no such key at all.
        ...(isWordDocType ? { supplier_id: supplierId || null } : {}),
      });
      onOpenChange(false);
    } catch {
      // The mutation hook already toasts the message (409 on a header already mapped).
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add mapping</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div>
            <Label htmlFor="import-field-alias-field" className="mb-1 block text-xs">
              System field
            </Label>
            {isWordDocType ? (
              // Open vocabulary (review round 1, item 4): a plain uppercase text input, not
              // a select over a closed list - the owner types a NEW token (`HP` for 高压)
              // here, on the row that names it, with no code change.
              <Input
                id="import-field-alias-field"
                value={field}
                onChange={(e) => setField(e.target.value.toUpperCase().replace(WORD_TOKEN_INPUT_RE, ''))}
                placeholder="e.g. SRT"
                maxLength={10}
              />
            ) : (
              <SearchableSelect
                id="import-field-alias-field"
                value={field}
                onChange={setField}
                options={fieldOptions}
                placeholder="Choose a field"
                disabled={fields.isLoading}
              />
            )}
          </div>
          <div>
            <Label htmlFor="import-field-alias-header" className="mb-1 block text-xs">
              Header
            </Label>
            <Input
              id="import-field-alias-header"
              value={alias}
              onChange={(e) => setAlias(e.target.value)}
              placeholder="e.g. 箱数"
            />
          </div>
          <div>
            <Label htmlFor="import-field-alias-locale" className="mb-1 block text-xs">
              Locale
            </Label>
            <Input
              id="import-field-alias-locale"
              value={locale}
              onChange={(e) => setLocale(e.target.value)}
              placeholder="zh, en (optional)"
              className="w-32"
            />
          </div>
          {isWordDocType && (
            <div>
              <Label htmlFor="import-field-alias-supplier" className="mb-1 block text-xs">
                Supplier
              </Label>
              <SearchableSelect
                id="import-field-alias-supplier"
                clearable
                value={supplierId}
                onChange={setSupplierId}
                onOptionChange={setSupplierOption}
                selectedOption={supplierOption ?? undefined}
                fetchOptions={supplierFetchOptions}
                paginated
                placeholder="Shared - every supplier"
                emptyMessage="No suppliers found."
              />
            </div>
          )}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => void submit()} disabled={!canSave || create.isPending}>
            {create.isPending ? <LoaderCircle className="size-4 animate-spin" /> : null}
            Add mapping
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default ImportFieldAliasFormDialog;
