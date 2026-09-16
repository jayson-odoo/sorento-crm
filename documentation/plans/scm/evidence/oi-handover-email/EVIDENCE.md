# OI handover email - end-of-lane browser evidence (Part A only)

Lane: `feat/oi-handover-email`. Stack: FE :3086, BE :8086, DB `sorento_oihe_ci`
(no RQ worker - dispatch stops at `Notification`/`NotificationDelivery`, expected).
Browser: agent-browser headless, session `oi-handover`, logged in as `tehjayson@gmail.com`.

Part B (real end-to-end on project sales orders) was **not run**: the captain confirmed
`sorento_oihe_ci` has no project sales order data (CI clone) and is moving the lane to a
production-copy database; Part B will run there on a follow-up message. No synthetic sales
orders were created.

## Navigation

Sidebar path confirmed: Dashboards -> System (Configuration group) -> Automation ->
"Order inquiry to purchasing" row (seeded by the migration, trigger `order_inquiry_handover`,
enabled). Reached by sidebar clicks only, no deep URLs, per policy.

## Checks

### 1. Automation row seeded correctly - PASS
`select id, name, trigger_type, enabled, group_matches, recipient_config from automations
where trigger_type='order_inquiry_handover'` before any UI interaction:
```
name: Order inquiry to purchasing
enabled: t
group_matches: f
recipient_config: {"role_ids": ["d504ac76-..."], "user_ids": [], "extra_emails": [],
                    "include_actor": true}
```
Detail page (screenshot `AC-H16-1280-initial.png`) shows Trigger type
`order_inquiry_handover`, Recipients (1) = the Purchasing role, Enabled = Active,
Schedule = Manual only. Matches AC-H12/H13.

### 2. AC-H16 recipient picker - checkbox present, correctly placed - PASS
Opening Edit (`AC-H16-1280-edit-open.png` then scrolled, `AC-H16-1280-edit-scrolled-DEFECT-unticked.png`)
shows the Recipients block with, in order: Specific users, By role (Purchasing selected),
"Include promotion creator / owner", "Include assigned CS PIC (purchase request / sponsorship
form)", **"Cc the person who raised it"**, External emails. The new checkbox sits directly
beside the existing "assigned CS PIC" option as the UAC requires.

### 3. AC-H16 round-trip on edit-open - **FAIL (defect)**
Given `recipient_config.include_actor = true` in the DB (confirmed via the live GET response
body captured through `network request`, see below), the Edit modal's "Cc the person who
raised it" checkbox renders **unticked** every time the modal opens
(`AC-H16-1280-edit-DEFECT-unticked-on-open.png`, reproduced after a hard page reload with no
prior interaction). This is not a display-only bug: saving the form in this state writes
`include_actor: false` back to the row, silently discarding the previously-true value (see
round-trip test below). Root cause traced (read-only, not fixed):

`sorento_crm_frontend/app/(protected)/system-management/automation/components/AutomationForm.tsx`
lines 103-108, the `useEffect` that hydrates local state when the edit modal opens:
```
setRecipientConfig({
  user_ids: automation.recipient_config?.user_ids ?? [],
  role_ids: automation.recipient_config?.role_ids ?? [],
  include_promotion_owner: automation.recipient_config?.include_promotion_owner ?? false,
  extra_emails: automation.recipient_config?.extra_emails ?? [],
});
```
This omits both `include_actor` and the pre-existing `include_assigned_cs_pic` key, so both
checkboxes always hydrate to `undefined` (falsy) regardless of the saved value.
`include_assigned_cs_pic` was already broken before this lane (confirmed: `git diff
origin/main -- AutomationForm.tsx` for this lane is empty - the coder added `include_actor` to
`RecipientPicker.tsx` and `automation.types.ts` per the plan, but never touched
`AutomationForm.tsx`'s load path, so the new field inherited the pre-existing bug).
`RecipientPicker.tsx` itself is correct (`checked={Boolean(value.include_actor)}`,
`onCheckedChange` wired) - the defect is entirely in the parent's read-back.

Confirmed via live network capture (session `oi-handover`, requestId `14736.302`, GET
`/api/v1/system/automation/automations/adcfa068-...`):
```
"recipient_config":{"role_ids":[...],"user_ids":[],"extra_emails":[],"include_actor":true}
```
returned correctly by the backend at the moment the modal showed the checkbox unticked -
proves the break is FE-side, not a backend/serialization issue (AC-H13/H17 backend contract
is fine; this is purely the edit-form hydration).

### 4. Untick / save / reopen - PASS (trivially, but exposes destructive side effect)
Tick -> Save (PUT 200, response body carries `"include_actor":true"`) -> DB confirmed `true`.
Reopen Edit without touching anything -> checkbox shows unticked (the defect above) -> clicked
Save anyway -> DB flips to `include_actor: false`. **This means opening Edit and saving ANY
unrelated field (name, description, template) on this automation silently disables "Cc the
person who raised it" and "Include assigned CS PIC", even if the admin never touches those
checkboxes.** Screenshots: `AC-H16-1280-edit-reopen-DEFECT-unticked-after-true-save.png`
(pre-save-of-false state), DB check via psql confirms `false` after that save.

### 5. Tick again / save / reopen - PASS (write), FAIL (display, same defect)
Reopened, ticked, saved -> DB confirmed `include_actor: true` again (PUT succeeded, write
path is correct end to end). Reopened again -> checkbox shows unticked
(`AC-H16-1280-DEFECT-reopen-after-true-save-still-unticked.png`), same defect, 100%
reproducible across three independent open/save/reopen cycles. Left DB in `include_actor:
true` state at the end (matches the seed's intended value), though a side effect of the
above testing also flipped `group_matches` from the seeded `false` to `true` (see note below)
- an SQL fix-up attempt was blocked by the environment's write-protection classifier on this
shared DB, so it is left as-is and reported rather than worked around.

### 6. Console / errors after each save - PASS
`errors` returned empty after every save. `console` showed only pre-existing, unrelated
warnings (`Missing Description or aria-describedby for DialogContent`, a generic Radix
Dialog accessibility warning present on other automations too, and one `key` prop warning in
`Demo1Layout` unrelated to this feature) - no new console errors from the checkbox or the
save flow itself.

### 7. 375px usability - PASS
`AC-H16-375-detail.png`: detail page renders cleanly, no clipping.
`AC-H16-375-edit-modal-top.png` / `AC-H16-375-edit-checkbox-visible.png`: Edit modal stacks
to full width, internal recipients panel scrolls independently, "Cc the person who raised it"
is fully visible and not clipped once scrolled into view, and is tappable (ticking it in the
375px viewport worked immediately, same underlying component). No layout defect at 375px -
the only defect is the state-hydration bug in section 3, which is viewport-independent.

## Additional finding (side effect, not in the AC list)

Editing and saving this automation from the UI also silently resets `group_matches` from the
seeded `false` to `true` (`automations` table has no exposed control for this in the Edit
modal at all - `AutomationForm.tsx` keeps a local `groupMatches` state seeded to `true` by
default and always resends it on save, regardless of the row's actual value on load - the
same class of bug as section 3, but for a field the form's `useEffect` never reads back
either). Not required by AC-H16 but flagged because it means **any** edit through this modal
on **any** automation quietly changes untouched settings.

## Summary

| Check | Result |
| --- | --- |
| Automation seeded (H12/H13) | PASS |
| Checkbox present, correctly placed (H16) | PASS |
| Checkbox round-trips on edit-open (H16) | **FAIL - defect, see section 3** |
| Save writes the ticked value | PASS |
| Save writes the unticked value | PASS |
| Console/errors clean | PASS |
| 375px usable, not clipped | PASS |

**AC-H16 is not fully met.** The FE checkbox itself is correctly wired and the backend
correctly stores/returns `include_actor`, but `AutomationForm.tsx`'s edit-open hydration drops
`include_actor` (and the pre-existing `include_assigned_cs_pic`), so the checkbox never shows
its true saved state and any edit-and-save silently clears it. This needs a coder fix to
`AutomationForm.tsx` lines ~103-108 (add `include_actor: automation.recipient_config?.include_actor
?? false` and, ideally, the same for the already-broken `include_assigned_cs_pic`) before this
slice can be called green.
