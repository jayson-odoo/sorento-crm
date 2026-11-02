"""PS-REGISTRATION-V3: party contacts, party links, lead source, district lists

* ``projects.party_contacts``: the people at a party (rule 4), company scoped.
* ``projects.party_links``: a party playing a role on a project beyond the three single
  columns, several per role (subcontractor, trading house, consultant, interior designer,
  tender party; Q5).
* ``projects.sales_profile.lead_source`` (rule 8) and ``projects.stakeholders.party_contact_id``
  (rule 6, SET NULL).
* Lookup set ``project_lead_source`` (Q4, shared with leads) and one district set per state,
  ``my_district_<state>`` (Q3), seeded; both editable in Settings afterwards. Existing free-text
  areas are left as typed.

Card: documentation/plans/projects/CARD-ps-registration-v3-02nov.md. Additive and guarded, so a
re-run, or a dev DB built by create_all, is harmless.

Revision ID: psr3_0001_party_contacts
Revises: qcp_0001_cover_page_fields
"""
import sqlalchemy as sa
from alembic import op

revision = "psr3_0001_party_contacts"
down_revision = "qcp_0001_cover_page_fields"
branch_labels = None
depends_on = None

LEAD_SOURCES = (
    ("site_visit", "Site visit"),
    ("architect", "Architect"),
    ("contractor", "Contractor"),
    ("dealer", "Dealer"),
    ("inbound", "Inbound (call, walk-in, web)"),
    ("bci", "BCI / data provider"),
    ("referral", "Referral"),
    ("tender_notice", "Tender notice"),
    ("existing_customer", "Existing customer"),
    ("interior_designer", "Interior designer (ID)"),
    ("other", "Other"),
)

# Administrative districts (daerah) per state; Sarawak by division, Kuala Lumpur by area.
DISTRICTS = {
    "Johor": ("Batu Pahat", "Johor Bahru", "Kluang", "Kota Tinggi", "Kulai", "Mersing", "Muar",
              "Pontian", "Segamat", "Tangkak"),
    "Kedah": ("Baling", "Bandar Baharu", "Kota Setar", "Kuala Muda", "Kubang Pasu", "Kulim",
              "Langkawi", "Padang Terap", "Pendang", "Pokok Sena", "Sik", "Yan"),
    "Kelantan": ("Bachok", "Gua Musang", "Jeli", "Kota Bharu", "Kuala Krai", "Machang",
                 "Pasir Mas", "Pasir Puteh", "Tanah Merah", "Tumpat"),
    "Melaka": ("Alor Gajah", "Jasin", "Melaka Tengah"),
    "Negeri Sembilan": ("Jelebu", "Jempol", "Kuala Pilah", "Port Dickson", "Rembau", "Seremban",
                        "Tampin"),
    "Pahang": ("Bentong", "Bera", "Cameron Highlands", "Jerantut", "Kuantan", "Lipis", "Maran",
               "Pekan", "Raub", "Rompin", "Temerloh"),
    "Perak": ("Bagan Datuk", "Batang Padang", "Hilir Perak", "Hulu Perak", "Kampar", "Kerian",
              "Kinta", "Kuala Kangsar", "Larut, Matang dan Selama", "Manjung", "Muallim",
              "Perak Tengah"),
    "Perlis": ("Arau", "Kangar", "Padang Besar"),
    "Pulau Pinang": ("Barat Daya", "Seberang Perai Selatan", "Seberang Perai Tengah",
                     "Seberang Perai Utara", "Timur Laut"),
    "Sabah": ("Beaufort", "Beluran", "Kalabakan", "Keningau", "Kinabatangan", "Kota Belud",
              "Kota Kinabalu", "Kota Marudu", "Kuala Penyu", "Kudat", "Kunak", "Lahad Datu",
              "Nabawan", "Papar", "Penampang", "Pitas", "Putatan", "Ranau", "Sandakan", "Semporna",
              "Sipitang", "Tambunan", "Tawau", "Telupid", "Tenom", "Tongod", "Tuaran"),
    "Sarawak": ("Betong", "Bintulu", "Kapit", "Kuching", "Limbang", "Miri", "Mukah", "Samarahan",
                "Sarikei", "Serian", "Sibu", "Sri Aman"),
    "Selangor": ("Gombak", "Hulu Langat", "Hulu Selangor", "Klang", "Kuala Langat",
                 "Kuala Selangor", "Petaling", "Sabak Bernam", "Sepang"),
    "Terengganu": ("Besut", "Dungun", "Hulu Terengganu", "Kemaman", "Kuala Nerus",
                   "Kuala Terengganu", "Marang", "Setiu"),
    "Kuala Lumpur": ("Bandar Tun Razak", "Batu", "Bukit Bintang", "Cheras", "Kepong",
                     "Lembah Pantai", "Segambut", "Seputeh", "Setiawangsa", "Titiwangsa",
                     "Wangsa Maju"),
    "Labuan": ("Labuan",),
    "Putrajaya": ("Putrajaya",),
}


def district_set_key(state: str) -> str:
    """`my_district_<state>`: the FE builds the same key from the picked state's value."""
    return "my_district_" + "_".join(state.lower().split())


def _seed_lookup(bind, set_key: str, name: str, options) -> None:
    bind.execute(
        sa.text(
            """
            INSERT INTO lookup_sets (id, tenant_id, set_key, name, description, is_active)
            SELECT gen_random_uuid(), NULL, :k, :n, NULL, TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM lookup_sets WHERE tenant_id IS NULL AND set_key = :k
            )
            """
        ),
        {"k": set_key, "n": name},
    )
    for order, (value, label) in enumerate(options, start=1):
        bind.execute(
            sa.text(
                """
                INSERT INTO lookup_options (id, set_id, value, label, sort_order, is_active)
                SELECT gen_random_uuid(), s.id, :v, :l, :o, TRUE
                  FROM lookup_sets s
                 WHERE s.tenant_id IS NULL AND s.set_key = :k
                ON CONFLICT (set_id, lower(value)) DO NOTHING
                """
            ),
            {"k": set_key, "v": value, "l": label, "o": order * 10},
        )


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS projects.party_contacts (
            id uuid PRIMARY KEY,
            company_id uuid NOT NULL REFERENCES public.companies (id),
            party_id uuid NOT NULL REFERENCES projects.parties (id) ON DELETE CASCADE,
            name varchar(255) NOT NULL,
            job_title varchar(120),
            phone varchar(50),
            email varchar(150),
            is_active boolean NOT NULL DEFAULT true,
            created_at timestamp NOT NULL DEFAULT now(),
            updated_at timestamp NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_project_party_contacts_party ON projects.party_contacts (party_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_party_contacts_company_id ON projects.party_contacts (company_id)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS projects.party_links (
            project_id uuid NOT NULL REFERENCES projects.projects (id) ON DELETE CASCADE,
            role varchar(32) NOT NULL,
            party_id uuid NOT NULL REFERENCES projects.parties (id) ON DELETE RESTRICT,
            created_at timestamp NOT NULL DEFAULT now(),
            PRIMARY KEY (project_id, role, party_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_project_party_links_party ON projects.party_links (party_id)"
    )
    op.execute(
        "ALTER TABLE projects.sales_profile ADD COLUMN IF NOT EXISTS lead_source varchar(32)"
    )
    op.execute(
        """
        ALTER TABLE projects.stakeholders ADD COLUMN IF NOT EXISTS party_contact_id uuid
            REFERENCES projects.party_contacts (id) ON DELETE SET NULL
        """
    )

    bind = op.get_bind()
    _seed_lookup(bind, "project_lead_source", "Project - Lead source", LEAD_SOURCES)
    for state, districts in DISTRICTS.items():
        _seed_lookup(
            bind,
            district_set_key(state),
            f"Malaysia - Districts of {state}",
            [(d, d) for d in districts],
        )


def downgrade() -> None:
    op.execute("ALTER TABLE projects.stakeholders DROP COLUMN IF EXISTS party_contact_id")
    op.execute("ALTER TABLE projects.sales_profile DROP COLUMN IF EXISTS lead_source")
    op.execute("DROP TABLE IF EXISTS projects.party_links")
    op.execute("DROP TABLE IF EXISTS projects.party_contacts")
    keys = ["project_lead_source"] + [district_set_key(s) for s in DISTRICTS]
    op.get_bind().execute(
        sa.text("DELETE FROM lookup_sets WHERE tenant_id IS NULL AND set_key = ANY(:k)"),
        {"k": keys},
    )
