# UAC: SO page Transfers tab sort

- **AC-1** Opening a sales order from the Sales Orders list (any sort, page or search) and
  opening its Transfers tab shows no error toast; the tab lists that order's transfers newest
  proposal first, page 1, unsearched.
- **AC-2** Same on the sales-agent detail page's Transfers tab.
- **AC-3** The standalone Transfers page still restores its own page, sort, search and filters
  when the user comes Back from a transfer.
- **AC-4** The transfers list endpoint still refuses a sort key outside its set with 422.
