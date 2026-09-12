"""Countries master (S1, `PLAN-local-supplier-oi-routing.md`).

Copies `Country(Base, CompanyScopedMixin)`'s shape (`app/models/country.py`): a
migration-seeded, shared reference table (`__company_shared__ = True`) a supplier's
Country FK points at (S2), and later a customer's or a user's. Seeds the full ISO
3166-1 alpha-2 list (249 rows) and grants the four `master_data.countries.*` slugs to
every role already holding the matching `master_data.units_of_measure.<action>` -
same `_create_if_absent` / SELECT-driven grant shape as
`alembic/versions/445_autocount_grant_sweep.py`, for the same reason: a blank scratch
schema built by `Base.metadata.create_all` never runs this migration, so
`_seed_countries`/`_grant_countries_permissions` are exercised directly by
`tests/test_countries.py` against a rolled-back connection or a `blank_session`.

Revision ID: 510_countries
Revises: 511_so_project_label
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "510_countries"
down_revision = "511_so_project_label"
branch_labels = None
depends_on = None


#: The full ISO 3166-1 alpha-2 list, English short names. 249 rows, ("MY", "Malaysia")
#: among them (AC-2.1).
ISO_COUNTRIES = (
    ("AD", "Andorra"), ("AE", "United Arab Emirates"), ("AF", "Afghanistan"),
    ("AG", "Antigua and Barbuda"), ("AI", "Anguilla"), ("AL", "Albania"),
    ("AM", "Armenia"), ("AO", "Angola"), ("AQ", "Antarctica"), ("AR", "Argentina"),
    ("AS", "American Samoa"), ("AT", "Austria"), ("AU", "Australia"), ("AW", "Aruba"),
    ("AX", "Aland Islands"), ("AZ", "Azerbaijan"),
    ("BA", "Bosnia and Herzegovina"), ("BB", "Barbados"), ("BD", "Bangladesh"),
    ("BE", "Belgium"), ("BF", "Burkina Faso"), ("BG", "Bulgaria"), ("BH", "Bahrain"),
    ("BI", "Burundi"), ("BJ", "Benin"), ("BL", "Saint Barthelemy"), ("BM", "Bermuda"),
    ("BN", "Brunei Darussalam"), ("BO", "Bolivia"),
    ("BQ", "Bonaire, Sint Eustatius and Saba"), ("BR", "Brazil"), ("BS", "Bahamas"),
    ("BT", "Bhutan"), ("BV", "Bouvet Island"), ("BW", "Botswana"), ("BY", "Belarus"),
    ("BZ", "Belize"),
    ("CA", "Canada"), ("CC", "Cocos (Keeling) Islands"),
    ("CD", "Congo (Democratic Republic of the)"), ("CF", "Central African Republic"),
    ("CG", "Congo"), ("CH", "Switzerland"), ("CI", "Cote d'Ivoire"),
    ("CK", "Cook Islands"), ("CL", "Chile"), ("CM", "Cameroon"), ("CN", "China"),
    ("CO", "Colombia"), ("CR", "Costa Rica"), ("CU", "Cuba"), ("CV", "Cabo Verde"),
    ("CW", "Curacao"), ("CX", "Christmas Island"), ("CY", "Cyprus"), ("CZ", "Czechia"),
    ("DE", "Germany"), ("DJ", "Djibouti"), ("DK", "Denmark"), ("DM", "Dominica"),
    ("DO", "Dominican Republic"), ("DZ", "Algeria"),
    ("EC", "Ecuador"), ("EE", "Estonia"), ("EG", "Egypt"), ("EH", "Western Sahara"),
    ("ER", "Eritrea"), ("ES", "Spain"), ("ET", "Ethiopia"),
    ("FI", "Finland"), ("FJ", "Fiji"), ("FK", "Falkland Islands"),
    ("FM", "Micronesia"), ("FO", "Faroe Islands"), ("FR", "France"),
    ("GA", "Gabon"), ("GB", "United Kingdom"), ("GD", "Grenada"), ("GE", "Georgia"),
    ("GF", "French Guiana"), ("GG", "Guernsey"), ("GH", "Ghana"), ("GI", "Gibraltar"),
    ("GL", "Greenland"), ("GM", "Gambia"), ("GN", "Guinea"), ("GP", "Guadeloupe"),
    ("GQ", "Equatorial Guinea"), ("GR", "Greece"),
    ("GS", "South Georgia and the South Sandwich Islands"), ("GT", "Guatemala"),
    ("GU", "Guam"), ("GW", "Guinea-Bissau"), ("GY", "Guyana"),
    ("HK", "Hong Kong"), ("HM", "Heard Island and McDonald Islands"),
    ("HN", "Honduras"), ("HR", "Croatia"), ("HT", "Haiti"), ("HU", "Hungary"),
    ("ID", "Indonesia"), ("IE", "Ireland"), ("IL", "Israel"), ("IM", "Isle of Man"),
    ("IN", "India"), ("IO", "British Indian Ocean Territory"), ("IQ", "Iraq"),
    ("IR", "Iran"), ("IS", "Iceland"), ("IT", "Italy"),
    ("JE", "Jersey"), ("JM", "Jamaica"), ("JO", "Jordan"), ("JP", "Japan"),
    ("KE", "Kenya"), ("KG", "Kyrgyzstan"), ("KH", "Cambodia"), ("KI", "Kiribati"),
    ("KM", "Comoros"), ("KN", "Saint Kitts and Nevis"),
    ("KP", "Korea (Democratic People's Republic of)"), ("KR", "Korea (Republic of)"),
    ("KW", "Kuwait"), ("KY", "Cayman Islands"), ("KZ", "Kazakhstan"),
    ("LA", "Lao People's Democratic Republic"), ("LB", "Lebanon"),
    ("LC", "Saint Lucia"), ("LI", "Liechtenstein"), ("LK", "Sri Lanka"),
    ("LR", "Liberia"), ("LS", "Lesotho"), ("LT", "Lithuania"), ("LU", "Luxembourg"),
    ("LV", "Latvia"), ("LY", "Libya"),
    ("MA", "Morocco"), ("MC", "Monaco"), ("MD", "Moldova"), ("ME", "Montenegro"),
    ("MF", "Saint Martin (French part)"), ("MG", "Madagascar"),
    ("MH", "Marshall Islands"), ("MK", "North Macedonia"), ("ML", "Mali"),
    ("MM", "Myanmar"), ("MN", "Mongolia"), ("MO", "Macao"),
    ("MP", "Northern Mariana Islands"), ("MQ", "Martinique"), ("MR", "Mauritania"),
    ("MS", "Montserrat"), ("MT", "Malta"), ("MU", "Mauritius"), ("MV", "Maldives"),
    ("MW", "Malawi"), ("MX", "Mexico"), ("MY", "Malaysia"), ("MZ", "Mozambique"),
    ("NA", "Namibia"), ("NC", "New Caledonia"), ("NE", "Niger"),
    ("NF", "Norfolk Island"), ("NG", "Nigeria"), ("NI", "Nicaragua"),
    ("NL", "Netherlands"), ("NO", "Norway"), ("NP", "Nepal"), ("NR", "Nauru"),
    ("NU", "Niue"), ("NZ", "New Zealand"),
    ("OM", "Oman"),
    ("PA", "Panama"), ("PE", "Peru"), ("PF", "French Polynesia"),
    ("PG", "Papua New Guinea"), ("PH", "Philippines"), ("PK", "Pakistan"),
    ("PL", "Poland"), ("PM", "Saint Pierre and Miquelon"), ("PN", "Pitcairn"),
    ("PR", "Puerto Rico"), ("PS", "Palestine, State of"), ("PT", "Portugal"),
    ("PW", "Palau"), ("PY", "Paraguay"),
    ("QA", "Qatar"),
    ("RE", "Reunion"), ("RO", "Romania"), ("RS", "Serbia"), ("RU", "Russian Federation"),
    ("RW", "Rwanda"),
    ("SA", "Saudi Arabia"), ("SB", "Solomon Islands"), ("SC", "Seychelles"),
    ("SD", "Sudan"), ("SE", "Sweden"), ("SG", "Singapore"),
    ("SH", "Saint Helena, Ascension and Tristan da Cunha"), ("SI", "Slovenia"),
    ("SJ", "Svalbard and Jan Mayen"), ("SK", "Slovakia"), ("SL", "Sierra Leone"),
    ("SM", "San Marino"), ("SN", "Senegal"), ("SO", "Somalia"), ("SR", "Suriname"),
    ("SS", "South Sudan"), ("ST", "Sao Tome and Principe"), ("SV", "El Salvador"),
    ("SX", "Sint Maarten (Dutch part)"), ("SY", "Syrian Arab Republic"),
    ("SZ", "Eswatini"),
    ("TC", "Turks and Caicos Islands"), ("TD", "Chad"),
    ("TF", "French Southern Territories"), ("TG", "Togo"), ("TH", "Thailand"),
    ("TJ", "Tajikistan"), ("TK", "Tokelau"), ("TL", "Timor-Leste"),
    ("TM", "Turkmenistan"), ("TN", "Tunisia"), ("TO", "Tonga"), ("TR", "Turkey"),
    ("TT", "Trinidad and Tobago"), ("TV", "Tuvalu"), ("TW", "Taiwan"),
    ("TZ", "Tanzania"),
    ("UA", "Ukraine"), ("UG", "Uganda"), ("UM", "United States Minor Outlying Islands"),
    ("US", "United States of America"), ("UY", "Uruguay"), ("UZ", "Uzbekistan"),
    ("VA", "Holy See"), ("VC", "Saint Vincent and the Grenadines"),
    ("VE", "Venezuela"), ("VG", "Virgin Islands (British)"),
    ("VI", "Virgin Islands (U.S.)"), ("VN", "Viet Nam"), ("VU", "Vanuatu"),
    ("WF", "Wallis and Futuna"), ("WS", "Samoa"),
    ("YE", "Yemen"), ("YT", "Mayotte"),
    ("ZA", "South Africa"), ("ZM", "Zambia"), ("ZW", "Zimbabwe"),
)

_ACTIONS = ("view", "add", "edit", "delete")


def _seed_countries(bind) -> None:
    """Idempotent: a second call inserts nothing new (AC-2.1)."""
    for code, name in ISO_COUNTRIES:
        bind.execute(
            sa.text(
                """
                INSERT INTO countries (id, code, name, is_active, created_at, updated_at)
                VALUES (gen_random_uuid(), :code, :name, true, now(), now())
                ON CONFLICT (lower(code)) DO NOTHING
                """
            ),
            {"code": code, "name": name},
        )


def _create_if_absent(bind, slug: str, name: str, description: str) -> None:
    bind.execute(
        sa.text(
            """
            INSERT INTO user_permissions (id, slug, name, description, created_at)
            SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
            WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
            """
        ),
        {"slug": slug, "name": name, "descr": description},
    )


#: Owner ruling (S1/N5, Phase 3 fix round): `.view` is derived from BOTH readers who
#: already reach a country today - whoever lists units of measure, and whoever lists
#: suppliers (the FK this table exists for in the first place). `.add`/`.edit`/`.delete`
#: are derived from `user_management.reference_data.manage` - the SAME shared
#: reference-vocabulary write authority `s6b_reference_data_manage_perm` established,
#: not from the (read-only-flavoured) UoM write slugs a role might hold for an unrelated
#: reason.
_VIEW_SOURCES = (
    "master_data.units_of_measure.view",
    "procurement.suppliers.view",
)
_MANAGE_SOURCE = "user_management.reference_data.manage"


def _grant_from_sources(bind, target: str, sources: tuple[str, ...]) -> None:
    """Grant `target` to every role holding ANY of `sources` - SELECT-driven, so a
    database with none of them granted anywhere is a clean no-op."""
    placeholders = ", ".join(f":s{i}" for i in range(len(sources)))
    params = {f"s{i}": slug for i, slug in enumerate(sources)}
    params["target"] = target
    bind.execute(
        sa.text(
            f"""
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, rp.role_id, tgt.id, now()
            FROM user_role_permissions rp
            JOIN user_permissions src ON src.id = rp.permission_id AND src.slug IN ({placeholders})
            CROSS JOIN user_permissions tgt
            WHERE tgt.slug = :target
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        params,
    )


def _grant_countries_permissions(bind) -> None:
    """The four `master_data.countries.*` slugs, granted from two DERIVED sets (AC-2.6):
    `.view` from `_VIEW_SOURCES`, the three write actions from `_MANAGE_SOURCE`."""
    for action in _ACTIONS:
        target = f"master_data.countries.{action}"
        _create_if_absent(
            bind, target,
            f"{action.capitalize()} Countries",
            f"Permission to {action} Countries.",
        )
        sources = _VIEW_SOURCES if action == "view" else (_MANAGE_SOURCE,)
        _grant_from_sources(bind, target, sources)


def upgrade() -> None:
    op.create_table(
        "countries",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "company_id", UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=True
        ),
        sa.Column("code", sa.String(2), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_countries_company_id", "countries", ["company_id"])
    op.create_index(
        "uq_countries_code_lower", "countries", [sa.text("lower(code)")], unique=True
    )
    bind = op.get_bind()
    _seed_countries(bind)
    _grant_countries_permissions(bind)


def downgrade() -> None:
    # sec N3 (review nit): a downgrade that drops the table but leaves four permission
    # slugs, and every grant of them, pointing at nothing is exactly the half-reverted
    # state a downgrade exists to avoid.
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM user_role_permissions WHERE permission_id IN (
                SELECT id FROM user_permissions
                WHERE slug LIKE 'master_data.countries.%'
            )
            """
        )
    )
    bind.execute(
        sa.text("DELETE FROM user_permissions WHERE slug LIKE 'master_data.countries.%'")
    )
    op.drop_table("countries")
