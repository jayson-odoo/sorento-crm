# A Dealer is a `customers` row, never a `companies` row

Multi-company isolation looks like the obvious home for dealers: give each dealer a Company,
let consumers order from the dealer's Company, let the dealer order from Sorento's. It is the
wrong mechanism, and the reasons are worth writing down because the shape is so tempting.

**A dealer Company would start empty.** Products, brands, stock, warehouses, suppliers and
customers are all in the *Owned* bucket - hard-partitioned, deliberately, because AutoCount
masters are separate and Mocha `CHAIR-01` is a different row from Sorento `CHAIR-01`. A
dealer Company therefore has no catalogue and no stock. Fixing that means either duplicating
the catalogue per dealer or reclassifying products as global - which undoes the Sorento/Mocha
separation the partition exists to provide.

**The scope model has a documented "all companies" state.** When the resolver sees an
X-API-Key call with no contact parameters, the scope is `None` and *no predicate is added*  - 
an accepted risk, mitigated by auditing contact-facing n8n branches. Between two in-house
companies with shared users and one owner, that is a reasonable trade. With external dealers
in those partitions the same state is a cross-dealer leak of pricing and customer lists. The
filter was built as a data partition between friendly parties; it is not a hostile-tenant
boundary and should not be asked to become one by reclassification.

**The surrounding machinery assumes a handful of companies and staff logins.** Contact→company
tagging is manual and strict-empty by design (untagged resolves to zero rows). `user_companies`
grants, `last_active_company_id` and the switcher are staff concepts, and superadmin sees every
company in one list. Two companies: fine. Two hundred dealers: a provisioning queue and an
unusable switcher.

**And the commercial objection outranks all three.** A consumer order stored in Sorento's
database exposes each dealer's retail margin and end-customer list to their own supplier.
That is the fastest way to make dealers refuse the Kit.

So: a Dealer is the `customers` row it already is - Sorento's counterparty on a normal order.
The consumer-facing document is a Dealer-owned Quote inside the Kit's own schema; the
Sorento-facing document is an ordinary draft order with `customer_id` = the dealer, entering
the existing pipeline unchanged. Kit rows carry a dealer scope of their own rather than
inheriting one from the company filter.

Two things this leaves open, deliberately. The dealer scope column is **deferred** until the
dealer-facing surface ships - while the Kit is staff-only, RBAC is the whole access story and
there is nothing to scope. And `respond_contacts` has **no link to `customers`** today: the
Kit's principal is a portal-token contact, the order counterparty is a customer, and nothing
joins them. That link is a prerequisite of the dealer surface, seedable by phone match but
requiring admin confirmation - `customers` allows one code across multiple debtor names, so a
phone match can be ambiguous.

This flips only if Sorento decides to sell dealers their own CRM - own products, own stock,
own staff logins. That is a different product, and it needs a real tenant boundary at the
schema or database level, not this partition stretched over external parties.
