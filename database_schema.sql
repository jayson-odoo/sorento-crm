-- public.picking_headers definition

-- Drop table

-- DROP TABLE public.picking_headers;

CREATE TABLE public.picking_headers (
	id uuid DEFAULT gen_random_uuid() NOT NULL,
	picking_number varchar(50) NOT NULL,
	picking_type varchar(50) NOT NULL,
	source_entity_type varchar(50) NULL,
	source_entity_id uuid NULL,
	picking_date date DEFAULT CURRENT_DATE NOT NULL,
	picked_by_user_id uuid NULL,
	inspection_status varchar(50) DEFAULT 'pending'::character varying NULL,
	quality_remarks text NULL,
	inspected_by_user_id uuid NULL,
	inspection_date timestamptz NULL,
	picking_status varchar(50) DEFAULT 'draft'::character varying NULL,
	total_items_picked int4 NULL,
	total_items_discrepancy int4 NULL,
	total_cost numeric(15, 2) NULL,
	notes text NULL,
	created_at timestamptz DEFAULT now() NULL,
	updated_at timestamptz DEFAULT now() NULL,
	CONSTRAINT picking_headers_inspection_status_check CHECK (((inspection_status)::text = ANY (ARRAY[('pending'::character varying)::text, ('passed'::character varying)::text, ('failed'::character varying)::text, ('partial_pass'::character varying)::text]))),
	CONSTRAINT picking_headers_picking_number_key UNIQUE (picking_number),
	CONSTRAINT picking_headers_picking_status_check CHECK (((picking_status)::text = ANY (ARRAY[('draft'::character varying)::text, ('submitted'::character varying)::text, ('approved'::character varying)::text, ('posted'::character varying)::text, ('rejected'::character varying)::text, ('closed'::character varying)::text]))),
	CONSTRAINT picking_headers_picking_type_check CHECK (((picking_type)::text = ANY (ARRAY[('goods_received'::character varying)::text, ('warehouse_transfer'::character varying)::text, ('sales_picking'::character varying)::text, ('stock_return'::character varying)::text, ('inventory_adjustment'::character varying)::text]))),
	CONSTRAINT picking_headers_pkey PRIMARY KEY (id)
);
CREATE INDEX idx_picking_headers_type ON public.picking_headers USING btree (picking_type);


-- public.complaints definition

-- Drop table

-- DROP TABLE public.complaints;

CREATE TABLE public.complaints (
	id uuid DEFAULT gen_random_uuid() NOT NULL,
	complaint_number varchar(100) NOT NULL,
	order_id uuid NULL,
	customer_id uuid NOT NULL,
	complaint_category_id uuid NOT NULL,
	complaint_status_id uuid NOT NULL,
	severity_level int4 NULL,
	subject varchar(255) NOT NULL,
	description text NOT NULL,
	reported_by uuid NOT NULL,
	assigned_to uuid NULL,
	reported_at timestamptz DEFAULT now() NULL,
	resolved_at timestamptz NULL,
	resolution_notes text NULL,
	created_at timestamptz DEFAULT now() NULL,
	updated_at timestamptz DEFAULT now() NULL,
	deleted_at timestamptz NULL,
	CONSTRAINT complaints_complaint_number_key UNIQUE (complaint_number),
	CONSTRAINT complaints_pkey PRIMARY KEY (id),
	CONSTRAINT complaints_severity_level_check CHECK ((severity_level = ANY (ARRAY[1, 2, 3, 4, 5])))
);
CREATE INDEX idx_complaints_complaint_number ON public.complaints USING btree (complaint_number);
CREATE INDEX idx_complaints_customer_id ON public.complaints USING btree (customer_id);
CREATE INDEX idx_complaints_order_id ON public.complaints USING btree (order_id);
CREATE INDEX idx_complaints_reported_at ON public.complaints USING btree (reported_at);
CREATE INDEX idx_complaints_status_id ON public.complaints USING btree (complaint_status_id);


-- public.inbound_shipment_lines definition

-- Drop table

-- DROP TABLE public.inbound_shipment_lines;

CREATE TABLE public.inbound_shipment_lines (
	id uuid DEFAULT gen_random_uuid() NOT NULL,
	shipment_id uuid NOT NULL,
	product_id uuid NOT NULL,
	quantity_shipped int4 NOT NULL,
	uom_id uuid NULL,
	batch_number varchar(100) NULL,
	serial_number_range_from varchar(100) NULL,
	serial_number_range_to varchar(100) NULL,
	carton_number varchar(50) NULL,
	cartons_count int4 DEFAULT 1 NULL,
	weight_per_carton numeric(10, 2) NULL,
	unit_cost numeric(12, 2) NULL,
	created_at timestamptz DEFAULT now() NULL,
	synced_to_excel bool DEFAULT false NULL,
	last_synced_to_excel timestamptz NULL,
	updated_at timestamptz NULL,
	CONSTRAINT inbound_shipment_lines_pkey PRIMARY KEY (id)
);
CREATE INDEX idx_inbound_shipment_lines ON public.inbound_shipment_lines USING btree (shipment_id);


-- public.inbound_shipments definition

-- Drop table

-- DROP TABLE public.inbound_shipments;

CREATE TABLE public.inbound_shipments (
	id uuid DEFAULT gen_random_uuid() NOT NULL,
	shipment_number varchar(50) NOT NULL,
	supplier_id uuid NOT NULL,
	shipment_date date NOT NULL,
	expected_arrival_date date NULL,
	actual_arrival_date date NULL,
	bill_of_lading_number varchar(100) NULL,
	shipping_container_number varchar(100) NULL,
	invoice_number varchar(100) NULL,
	shipment_status varchar(50) DEFAULT 'in_transit'::character varying NULL,
	total_items_shipped int4 NULL,
	total_cartons int4 NULL,
	notes text NULL,
	created_at timestamptz DEFAULT now() NULL,
	created_by uuid NULL,
	updated_at timestamptz DEFAULT now() NULL,
	attachment_id uuid NOT NULL,
	synced_to_excel bool DEFAULT false NULL,
	last_synced_to_excel timestamptz NULL,
	CONSTRAINT inbound_shipments_pkey PRIMARY KEY (id),
	CONSTRAINT inbound_shipments_shipment_number_key UNIQUE (shipment_number),
	CONSTRAINT inbound_shipments_shipment_status_check CHECK (((shipment_status)::text = ANY (ARRAY[('in_transit'::character varying)::text, ('arrived_at_port'::character varying)::text, ('at_warehouse'::character varying)::text, ('partially_received'::character varying)::text, ('fully_received'::character varying)::text, ('closed'::character varying)::text])))
);
CREATE INDEX idx_inbound_shipments_supplier ON public.inbound_shipments USING btree (supplier_id);


-- public.picking_lines definition

-- Drop table

-- DROP TABLE public.picking_lines;

CREATE TABLE public.picking_lines (
	id uuid DEFAULT gen_random_uuid() NOT NULL,
	picking_header_id uuid NOT NULL,
	spo_allocation_id uuid NULL,
	product_id uuid NOT NULL,
	quantity_expected int4 NOT NULL,
	quantity_picked int4 NOT NULL,
	quantity_discrepancy int4 GENERATED ALWAYS AS (quantity_picked - quantity_expected) STORED NULL,
	uom_id uuid NULL,
	picked_condition varchar(50) DEFAULT 'good'::character varying NULL,
	condition_remarks text NULL,
	batch_number_picked varchar(100) NULL,
	expiry_date date NULL,
	unit_cost numeric(12, 2) NULL,
	line_total numeric(15, 2) NULL,
	created_at timestamptz DEFAULT now() NULL,
	source_warehouse_id uuid NULL,
	destination_warehouse_id uuid NULL,
	synced_to_excel bool DEFAULT false NULL,
	last_synced_to_excel timestamptz NULL,
	updated_at timestamptz NULL,
	CONSTRAINT picking_lines_picked_condition_check CHECK (((picked_condition)::text = ANY (ARRAY[('good'::character varying)::text, ('damaged'::character varying)::text, ('defective'::character varying)::text, ('shortfall'::character varying)::text]))),
	CONSTRAINT picking_lines_pkey PRIMARY KEY (id)
);
CREATE INDEX idx_picking_lines_picking_header ON public.picking_lines USING btree (picking_header_id);
CREATE INDEX idx_picking_lines_product ON public.picking_lines USING btree (product_id);
CREATE INDEX idx_picking_lines_spo ON public.picking_lines USING btree (spo_allocation_id);


-- public.spo_allocations definition

-- Drop table

-- DROP TABLE public.spo_allocations;

CREATE TABLE public.spo_allocations (
	id uuid DEFAULT gen_random_uuid() NOT NULL,
	spo_number varchar(50) NULL,
	inbound_shipment_lines_id uuid NULL,
	inbound_shipment_id uuid NOT NULL,
	warehouse_id uuid NOT NULL,
	storage_zone_id uuid NULL,
	allocated_quantity int4 NOT NULL,
	uom_id uuid NULL,
	receipt_status varchar(50) DEFAULT 'pending'::character varying NULL,
	quantity_received int4 DEFAULT 0 NULL,
	quantity_rejected int4 DEFAULT 0 NULL,
	allocation_notes text NULL,
	created_at timestamptz DEFAULT now() NULL,
	created_by uuid NULL,
	spo_line_number int4 NULL,
	product_id uuid NOT NULL,
	synced_to_excel bool DEFAULT false NULL,
	updated_at timestamptz NULL,
	last_synced_to_excel timestamptz NULL,
	CONSTRAINT spo_allocations_pkey PRIMARY KEY (id),
	CONSTRAINT spo_allocations_receipt_status_check CHECK (((receipt_status)::text = ANY (ARRAY[('pending'::character varying)::text, ('partial_received'::character varying)::text, ('fully_received'::character varying)::text, ('rejected'::character varying)::text]))),
	CONSTRAINT uk_spo_allocations_spo_number_line_number UNIQUE (spo_number, spo_line_number)
);
CREATE INDEX idx_spo_allocations_shipment ON public.spo_allocations USING btree (inbound_shipment_id);
CREATE INDEX idx_spo_allocations_warehouse ON public.spo_allocations USING btree (warehouse_id);


-- public.complaints foreign keys

ALTER TABLE public.complaints ADD CONSTRAINT complaints_complaint_category_id_fkey FOREIGN KEY (complaint_category_id) REFERENCES public.complaint_categories(id);
ALTER TABLE public.complaints ADD CONSTRAINT complaints_complaint_status_id_fkey FOREIGN KEY (complaint_status_id) REFERENCES public.complaint_statuses(id);
ALTER TABLE public.complaints ADD CONSTRAINT complaints_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id);
ALTER TABLE public.complaints ADD CONSTRAINT complaints_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id);


-- public.inbound_shipment_lines foreign keys

ALTER TABLE public.inbound_shipment_lines ADD CONSTRAINT inbound_shipment_lines_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE RESTRICT;
ALTER TABLE public.inbound_shipment_lines ADD CONSTRAINT inbound_shipment_lines_shipment_id_fkey FOREIGN KEY (shipment_id) REFERENCES public.inbound_shipments(id) ON DELETE CASCADE;
ALTER TABLE public.inbound_shipment_lines ADD CONSTRAINT inbound_shipment_lines_uom_id_fkey FOREIGN KEY (uom_id) REFERENCES public.units_of_measure(id);


-- public.inbound_shipments foreign keys

ALTER TABLE public.inbound_shipments ADD CONSTRAINT inbound_shipments_attachment_id_fkey FOREIGN KEY (attachment_id) REFERENCES public.attachments(id);
ALTER TABLE public.inbound_shipments ADD CONSTRAINT inbound_shipments_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES public.suppliers(id) ON DELETE RESTRICT;


-- public.picking_lines foreign keys

ALTER TABLE public.picking_lines ADD CONSTRAINT picking_lines_destination_warehouse_id_fkey FOREIGN KEY (destination_warehouse_id) REFERENCES public.warehouses(id) ON DELETE RESTRICT;
ALTER TABLE public.picking_lines ADD CONSTRAINT picking_lines_picking_header_id_fkey FOREIGN KEY (picking_header_id) REFERENCES public.picking_headers(id) ON DELETE CASCADE;
ALTER TABLE public.picking_lines ADD CONSTRAINT picking_lines_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE RESTRICT;
ALTER TABLE public.picking_lines ADD CONSTRAINT picking_lines_source_warehouse_id_fkey FOREIGN KEY (source_warehouse_id) REFERENCES public.warehouses(id) ON DELETE RESTRICT;
ALTER TABLE public.picking_lines ADD CONSTRAINT picking_lines_spo_allocation_id_fkey FOREIGN KEY (spo_allocation_id) REFERENCES public.spo_allocations(id);
ALTER TABLE public.picking_lines ADD CONSTRAINT picking_lines_uom_id_fkey FOREIGN KEY (uom_id) REFERENCES public.units_of_measure(id);


-- public.spo_allocations foreign keys

ALTER TABLE public.spo_allocations ADD CONSTRAINT spo_allocations_inbound_shipment_id_fkey FOREIGN KEY (inbound_shipment_id) REFERENCES public.inbound_shipments(id) ON DELETE CASCADE;
ALTER TABLE public.spo_allocations ADD CONSTRAINT spo_allocations_inbound_shipment_lines_id_fkey FOREIGN KEY (inbound_shipment_lines_id) REFERENCES public.inbound_shipment_lines(id) ON DELETE CASCADE;
ALTER TABLE public.spo_allocations ADD CONSTRAINT spo_allocations_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id) ON DELETE CASCADE;
ALTER TABLE public.spo_allocations ADD CONSTRAINT spo_allocations_storage_zone_id_fkey FOREIGN KEY (storage_zone_id) REFERENCES public.storage_zones(id);
ALTER TABLE public.spo_allocations ADD CONSTRAINT spo_allocations_uom_id_fkey FOREIGN KEY (uom_id) REFERENCES public.units_of_measure(id);
ALTER TABLE public.spo_allocations ADD CONSTRAINT spo_allocations_warehouse_id_fkey FOREIGN KEY (warehouse_id) REFERENCES public.warehouses(id) ON DELETE RESTRICT;