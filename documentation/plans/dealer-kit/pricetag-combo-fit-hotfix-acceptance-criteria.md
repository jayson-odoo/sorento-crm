# UAC: PRICETAG-COMBO-FIT-HOTFIX

1. A template with no combo position field is selectable for any combo in "Price tag templates" (no "Does not fit").
2. Saving that link succeeds (no 422 TAG_TEMPLATE_DOES_NOT_FIT).
3. The link is offered on a request line for that combo (not filtered at read).
4. Approving a request line with that template and combo is not refused with TEMPLATE_POSITIONS_MISSING.
5. A template that reads some positions but fewer fixed parts than the combo has is still disabled
   with "Prints k of this combo's N fixed parts", and its save is still refused.
