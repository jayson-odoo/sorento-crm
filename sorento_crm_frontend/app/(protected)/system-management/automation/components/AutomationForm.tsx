'use client';

import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { useEmailTemplates } from '../../email-templates/hooks/useEmailTemplates';
import {
  useCreateAutomation,
  useTriggerCatalog,
  useUpdateAutomation,
} from '../hooks/useAutomations';
import type {
  Automation,
  RecipientConfig,
} from '../types/automation.types';
import RecipientPicker from './RecipientPicker';

const TIMEZONES = [
  'Asia/Kuala_Lumpur',
  'Asia/Singapore',
  'Asia/Jakarta',
  'Asia/Bangkok',
  'Asia/Tokyo',
  'UTC',
];

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  automation?: Automation | null;
  onSaved?: () => void;
}

const emptyRecipients: RecipientConfig = {
  user_ids: [],
  role_ids: [],
  include_promotion_owner: false,
  extra_emails: [],
};

export default function AutomationForm({ open, onOpenChange, automation, onSaved }: Props) {
  const isEdit = !!automation;
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [enabled, setEnabled] = useState(true);
  const [triggerType, setTriggerType] = useState<string>('');
  const [daysBefore, setDaysBefore] = useState<number>(7);
  const [emailTemplateId, setEmailTemplateId] = useState<string>('');
  const [recipientConfig, setRecipientConfig] = useState<RecipientConfig>(emptyRecipients);
  const [groupMatches, setGroupMatches] = useState(true);
  const [scheduleType, setScheduleType] = useState<'manual' | 'daily'>('manual');
  const [runTime, setRunTime] = useState<string>('09:00');
  const [timezone, setTimezone] = useState<string>('Asia/Kuala_Lumpur');

  const triggers = useTriggerCatalog();
  const templates = useEmailTemplates({ limit: 100 });
  const createMut = useCreateAutomation();
  const updateMut = useUpdateAutomation(automation?.id ?? '');
  const saving = createMut.isPending || updateMut.isPending;

  const triggerSpecs = triggers.data?.triggers ?? [];

  useEffect(() => {
    if (!open) return;
    if (automation) {
      setName(automation.name);
      setDescription(automation.description ?? '');
      setEnabled(automation.enabled);
      setTriggerType(automation.trigger_type);
      const cfg = automation.trigger_config as { days_before?: number };
      setDaysBefore(typeof cfg?.days_before === 'number' ? cfg.days_before : 7);
      setEmailTemplateId(automation.email_template_id);
      setRecipientConfig({
        user_ids: automation.recipient_config?.user_ids ?? [],
        role_ids: automation.recipient_config?.role_ids ?? [],
        include_promotion_owner: automation.recipient_config?.include_promotion_owner ?? false,
        extra_emails: automation.recipient_config?.extra_emails ?? [],
      });
      setGroupMatches(automation.group_matches ?? true);
      setScheduleType(automation.schedule_type);
      setRunTime(automation.run_time ? automation.run_time.slice(0, 5) : '09:00');
      setTimezone(automation.timezone || 'Asia/Kuala_Lumpur');
    } else {
      setName('');
      setDescription('');
      setEnabled(true);
      setTriggerType(triggerSpecs[0]?.type ?? '');
      setDaysBefore(7);
      setEmailTemplateId('');
      setRecipientConfig(emptyRecipients);
      setGroupMatches(true);
      setScheduleType('manual');
      setRunTime('09:00');
      setTimezone('Asia/Kuala_Lumpur');
    }
  }, [open, automation, triggerSpecs.length]);

  const triggerSpec = useMemo(
    () => triggerSpecs.find((s) => s.type === triggerType),
    [triggerSpecs, triggerType],
  );

  async function onSubmit() {
    if (!name.trim()) {
      toast.error('Name is required');
      return;
    }
    if (!triggerType) {
      toast.error('Pick a trigger type');
      return;
    }
    if (!emailTemplateId) {
      toast.error('Pick an email template');
      return;
    }
    if (scheduleType === 'daily' && !runTime) {
      toast.error('Pick a run time');
      return;
    }
    const totalRecipients =
      recipientConfig.user_ids.length +
      recipientConfig.role_ids.length +
      recipientConfig.extra_emails.length +
      (recipientConfig.include_promotion_owner ? 1 : 0) +
      (recipientConfig.include_assigned_cs_pic ? 1 : 0);
    if (totalRecipients === 0) {
      toast.error('At least one recipient is required');
      return;
    }
    const body = {
      name: name.trim(),
      description: description.trim() || null,
      enabled,
      trigger_type: triggerType,
      trigger_config: triggerType === 'days_before_promotion_end' ? { days_before: daysBefore } : {},
      action_type: 'send_email',
      email_template_id: emailTemplateId,
      recipient_config: recipientConfig,
      group_matches: triggerType === 'days_before_promotion_end' ? groupMatches : true,
      schedule_type: scheduleType,
      run_time: scheduleType === 'daily' ? `${runTime}:00` : null,
      timezone,
    };
    try {
      if (isEdit && automation) {
        await updateMut.mutateAsync(body);
        toast.success('Automation updated');
      } else {
        await createMut.mutateAsync(body);
        toast.success('Automation created');
      }
      onSaved?.();
      onOpenChange(false);
    } catch (err) {
      toast.error((err as Error).message || 'Save failed');
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[90vh] max-w-3xl flex-col">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit automation' : 'New automation'}</DialogTitle>
        </DialogHeader>

        <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 overflow-y-auto px-1 md:grid-cols-2">
          <div className="space-y-1 md:col-span-2">
            <Label htmlFor="auto-name">Name</Label>
            <Input
              id="auto-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Promotion expiry reminder"
            />
          </div>
          <div className="space-y-1 md:col-span-2">
            <Label htmlFor="auto-desc">Description</Label>
            <Textarea
              id="auto-desc"
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <div className="space-y-1">
            <Label>Trigger</Label>
            <Select value={triggerType} onValueChange={setTriggerType}>
              <SelectTrigger>
                <SelectValue placeholder="Pick trigger" />
              </SelectTrigger>
              <SelectContent>
                {triggerSpecs.map((s) => (
                  <SelectItem key={s.type} value={s.type}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {triggerSpec && (
              <p className="text-xs text-muted-foreground">{triggerSpec.description}</p>
            )}
          </div>

          {triggerType === 'days_before_promotion_end' && (
            <div className="space-y-1">
              <Label htmlFor="auto-days">Days before end</Label>
              <Input
                id="auto-days"
                type="number"
                min={0}
                value={daysBefore}
                onChange={(e) => setDaysBefore(Number(e.target.value))}
              />
            </div>
          )}

          <div className="space-y-1 md:col-span-2">
            <Label>Email template</Label>
            <Select value={emailTemplateId} onValueChange={setEmailTemplateId}>
              <SelectTrigger>
                <SelectValue placeholder="Pick template" />
              </SelectTrigger>
              <SelectContent>
                {(templates.data?.data ?? []).map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    {t.name} ({t.code})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="md:col-span-2">
            <Label>Recipients</Label>
            <RecipientPicker value={recipientConfig} onChange={setRecipientConfig} />
          </div>

          {triggerType === 'days_before_promotion_end' && (
            <div className="md:col-span-2 rounded-md border p-3">
              <div className="flex items-start gap-3">
                <Switch
                  id="auto-group"
                  checked={groupMatches}
                  onCheckedChange={setGroupMatches}
                />
                <div className="space-y-0.5">
                  <Label htmlFor="auto-group">Combine into one email</Label>
                  <p className="text-xs text-muted-foreground">
                    When several promotions expire on the same day, send each recipient a
                    single email listing them all instead of one email per promotion.
                  </p>
                </div>
              </div>
            </div>
          )}

          <div className="space-y-2 md:col-span-2">
            <Label>Schedule</Label>
            <RadioGroup
              value={scheduleType}
              onValueChange={(v) => setScheduleType(v as 'manual' | 'daily')}
              className="flex gap-4"
            >
              <label className="flex items-center gap-2 cursor-pointer">
                <RadioGroupItem value="manual" id="sched-manual" />
                <span>Manual</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <RadioGroupItem value="daily" id="sched-daily" />
                <span>Daily</span>
              </label>
            </RadioGroup>
            {scheduleType === 'daily' && (
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label htmlFor="auto-runtime">Run time</Label>
                  <Input
                    id="auto-runtime"
                    type="time"
                    value={runTime}
                    onChange={(e) => setRunTime(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <Label>Timezone</Label>
                  <Select value={timezone} onValueChange={setTimezone}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {TIMEZONES.map((tz) => (
                        <SelectItem key={tz} value={tz}>
                          {tz}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}
          </div>

          <div className="flex items-center gap-2 md:col-span-2">
            <Switch id="auto-enabled" checked={enabled} onCheckedChange={setEnabled} />
            <Label htmlFor="auto-enabled">Enabled</Label>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={onSubmit} disabled={saving}>
            {saving ? 'Saving…' : isEdit ? 'Save changes' : 'Create automation'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
