now that we have the fundamental of the frontend of the system in terms of master and configuration data, we need to move on to the operational data side

For operational data, we have 2 modules yet
- Complaint management
    - complaints (table complaints) - should be able to create / edit / view, this is a menu for user to manage complaints
- Procurement
    - Packing List (table inbound_shipments and inbound_shipment_lines) - should be able to create / edit / view - this is a menu for user to manage incoming shipments from oversea
    - SPO (table spo_allocations) - should be able to create / edit / view - this is a menu for user to manage the allocation of packing list items to each warehouses
    - GRN (table picking_headers and picking_lines) - should be able to create / edit / view - this is a menu for user to manage the goods receiving of the allocated items to close the loop

Packing List, SPO, GRN is a streamlines process where they are linked sequentially, so make sure I can navigate from 1 to another easily by clicking on the hyperlinks

For database schema, is available in database_schema.sql

Follow design principle of reusing existing components as much as possible, and use similar theme, interaction as existing codebase as much as possible

