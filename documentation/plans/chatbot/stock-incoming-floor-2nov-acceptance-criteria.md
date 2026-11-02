# UAC: STOCK-INCOMING-FLOOR (Fix A)

Plan: `PLAN-stock-incoming-floor-2nov.md`. Fake codes and dates only.

- **AC-SIF1** A dealer with padding on asks a product with no stock and a quantity. Its shipment is
  promised 20/10/2026, its category pads 14 days, today is 02/11/2026. The stock check answers
  incoming with ETA 03/11/2026 (not "No stock and no incoming").
- **AC-SIF2** The same dealer asks the ETA of the same product: the ETA ask tells 03/11/2026 first,
  the date the stock check told.
- **AC-SIF3** A told date equal to today counts as incoming.
- **AC-SIF4** With two shipments, the earliest whose TOLD date is today or later answers; a shipment
  whose told date is past does not.
- **AC-SIF5** A contact with padding off is floored on the real date and is told the real date of the
  next shipment, never a padded one.
- **AC-SIF6** A code carried by two companies is padded by the larger of their offsets on the stock
  check, as the ETA ask already does.
- **AC-SIF7** Unchanged: staff and no-contact reads, the packing-list requirement on the stock check,
  and every reply wording. A shipment whose told date has passed is out of scope (Fix B, owner).
