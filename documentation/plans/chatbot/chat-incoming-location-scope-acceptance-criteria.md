# UAC: CHAT-INCOMING-LOCATION-SCOPE

Contact C's stock-visibility policy names BRW and MWH (include list).

- AC-1: Container K1, product P, remaining 100, allocations BRW 30 / BRW-BB 50, 20 unallocated.
  C's incoming answer for P reads Incoming 30, Warehouse Allocations BRW (30), no unallocated
  quantity, no BRW-BB. Same on `/list`, `/by-product`, `/shipments/{id}/products`.
- AC-2: A line allocated only to locations outside C's scope (BRW-NTC 40) is not returned; a
  shipment or product left with no line is not returned (so the reply says no incoming).
- AC-3: A line with no allocation at all is not returned to C.
- AC-4: Exclusion lists and merged access-type policies decide it through the same
  `scope_warehouse_ids` the stock lines and PO rung use; BRW does not include BRW-BB.
- AC-5: `/shipments` totals count only C's in-scope quantity; pagination totals count only the
  shipments C may see.
- AC-6: A dealer (`availability`) is told every shipment's ETA, wherever it is allocated (owner
  26 Oct: location scoping does not apply to ETA); the stock ask's ETA and the incoming answer agree.
- AC-7: Last-in ("last 2 in") for P with SPO lines at BRW-BB (newest), MWH, BRW returns the MWH
  and BRW lines; `availability` withholds `warehouse`.
- AC-8: An unresolvable contact gets no incoming rows and no last-in rows.
- AC-9: No `contact_id` (staff, n8n), or a policy naming no location list: today's output exactly,
  allocations and unallocated quantity included.
- AC-11: On the incoming routes and last-in, the location policy is read for the same contact the
  ETA rules and field reveals resolved (NULL-workspace fallback included), never the raw id. The PO
  placed route is out of this lane (crew, 26 Oct; hotfix lane closed).
- AC-12: C cannot fetch the packing list of a shipment with no in-scope line (`/attachment` and
  `/shipments/{id}/products`, every mode, dealers included).
- AC-10: The parser's LOCATION lookup list offers C only BRW and MWH.
