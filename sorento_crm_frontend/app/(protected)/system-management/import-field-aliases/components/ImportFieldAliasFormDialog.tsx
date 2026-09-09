'use client';

import { useEffect, useState } from 'react';
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
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useCreateImportFieldAlias, useImportFieldAliasFields } from '../hooks/useImportFieldAliases';
import type { ImportFieldAliasDocType } from '../types/importFieldAlias.types';

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
  const [field, setField] = useState('');
  const [alias, setAlias] = useState('');
  const [locale, setLocale] = useState('');

  useEffect(() => {
    if (open) {
      setField('');
      setAlias('');
      setLocale('');
    }
  }, [open]);

  const fieldOptions = (fields.data ?? []).map((f) => ({ value: f.field, label: f.label }));
  const canSave = !!field && alias.trim().length > 0;

  const submit = async () => {
    if (!canSave) return;
    try {
      await create.mutateAsync({ field, alias: alias.trim(), locale: locale.trim() || null });
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
            <SearchableSelect
              id="import-field-alias-field"
              value={field}
              onChange={setField}
              options={fieldOptions}
              placeholder="Choose a field"
              disabled={fields.isLoading}
            />
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
