#!/usr/bin/env python3
"""DEV ONLY: seed the data the PRICETAG-UPGRADE-VARIANTS hand test / browser pass uses.

Under one company (default SRT) it makes, matched on code or name so a re-run changes nothing:

* Products SRTKS2432 (LP 1150), SRTKT1862SS (LP 285), SRTKT71SS (LP 440, two feature icons: steel
  grade 304 and a pull-out mixer), and a combo "1 TAP + UPGRADE" on SRTKS2432: SRTKT1862SS fixed,
  SRTKT71SS an upgrade with top-up 150, combo LP 1150 / SP 949, free items DRAINER + CHOPPING BOARD.
* The SRTWC8354-SH family (-SH LP 1750 and seven variants under it through variant_of_id; -SH-UF is
  priced 1800 so the "prices differently" warning shows), with the specs trap_length / trap_type /
  seat_material.
* Spec registry rows for those keys, and icon assets mapped on trap_length 150/200/250/300, trap_type
  p_trap, seat_material uf, steel_grade 304 and mixer_type pull_out.
* A portal contact "Hand Test Dealer" in a market segment that may file price tag requests, tagged
  into the company, so the portal's lines table can be walked (CRM > Contacts > Impersonate).
* Two published templates: "Combo + Upgrade" (free items box, Upgrades box, main feature icons) and
  "WC family" (feature icons on All variants), linked to the combo and to SRTWC8354-SH.
* One submitted request with a family line (SRTWC8354-SH-UF-300 unticked) and a combo line with the
  upgrade picked at SP, so the staff designer and the PDF export have something to open.

Icon and photo bytes: the sandbox has no object storage, so the PNGs are drawn into --asset-dir and
the attachment rows point at --asset-base-url with provider --storage-provider. Serve the folder
with a CORS-enabled static server. With provider r2 the backend (started with dummy R2_* env and
R2_CDN_DOMAIN set to the static server's host:port) signs a presigned URL offline, always https, so
the static server must speak https (self-signed is fine with a browser that ignores cert errors).

Refuses to run unless the database host is local, unless `--yes`. Dry run by default; `--apply` writes.

USAGE
-----
    cd sorento_crm_backend
    SORENTO_ENV_FILE=.env.ci-tests venv/bin/python scripts/seed_pricetag_upgrade_variants_handtest.py --apply \
        --asset-dir /path/to/dir --asset-base-url https://localhost:8099
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from decimal import Decimal
from typing import Optional, Sequence, TextIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func  # noqa: E402

from app.audit_context import AuditActor, clear_actor, stamp_actor  # noqa: E402
from app.models.base import company_scope  # noqa: E402
from app.models.company import Company  # noqa: E402

JOB_ID = "seed_pricetag_upgrade_variants_handtest"
LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1"}
HOST_CODE, FIXED_CODE, UPGRADE_CODE = "SRTKS2432", "SRTKT1862SS", "SRTKT71SS"
COMBO_NAME = "1 TAP + UPGRADE"
BASE = "SRTWC8354-SH"
#: code -> (parent code, trap_length, trap_type, seat_material, list price)
FAMILY = {
    "SRTWC8354-SH": (None, 250, "s_trap", None, "1750.00"),
    "SRTWC8354-SH-150": (BASE, 150, "s_trap", None, "1750.00"),
    "SRTWC8354-SH-200": (BASE, 200, "s_trap", None, "1750.00"),
    "SRTWC8354-SH-P": (BASE, 180, "p_trap", None, "1750.00"),
    "SRTWC8354-SH-UF": (BASE, 250, "s_trap", "uf", "1800.00"),
    "SRTWC8354-SH-UF-150": ("SRTWC8354-SH-UF", 150, "s_trap", "uf", "1750.00"),
    "SRTWC8354-SH-UF-200": ("SRTWC8354-SH-UF", 200, "s_trap", "uf", "1750.00"),
    "SRTWC8354-SH-UF-300": ("SRTWC8354-SH-UF", 300, "s_trap", "uf", "1750.00"),
}
#: key -> (label, data_type, allowed, unit, icon_order, {value: icon name})
REGISTRY = {
    "steel_grade": ("Steel grade", "enum", ["304"], None, 1, {"304": "SUS 304"}),
    "mixer_type": ("Mixer type", "enum", ["pull_out"], None, 2, {"pull_out": "Pull-out mixer"}),
    "trap_length": (
        "Trap outlet length", "numeric", [], "mm", 3,
        {"150": '6" S-trap 150mm', "200": '8" S-trap 200mm', "250": '10" S-trap 250mm', "300": '12" S-trap 300mm'},
    ),
    "trap_type": ("Trap type", "enum", ["s_trap", "p_trap"], None, 4, {"p_trap": "P-trap 180mm"}),
    "seat_material": ("Seat material", "enum", ["uf", "pp"], None, 5, {"uf": "UF seat cover"}),
}


def _png(label: str, colour: tuple[int, int, int], size: tuple[int, int]) -> bytes:
    import io

    from PIL import Image, ImageDraw

    image = Image.new("RGBA", size, (255, 255, 255, 0) if size[0] == size[1] else (235, 238, 242, 255))
    draw = ImageDraw.Draw(image)
    if size[0] == size[1]:
        draw.ellipse([2, 2, size[0] - 3, size[1] - 3], fill=colour)
    else:
        draw.rectangle([6, 6, size[0] - 7, size[1] - 7], outline=colour, width=4)
    draw.text((size[0] // 2 - 4 * min(len(label), 12), size[1] // 2 - 5), label[:12], fill=(255, 255, 255) if size[0] == size[1] else colour)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class Seeder:
    def __init__(self, db, company_id: str, asset_dir: str, base_url: str, provider: str, out: TextIO):
        self.db, self.company_id, self.out, self.provider = db, company_id, out, provider
        self.asset_dir, self.base_url = asset_dir, base_url.rstrip("/")
        os.makedirs(asset_dir, exist_ok=True)

    def say(self, text: str) -> None:
        self.out.write(text + "\n")

    # ---------------------------------------------------------------- bytes
    def _attachment(self, filename: str, content: bytes):
        from app.models.resources import Attachment

        with open(os.path.join(self.asset_dir, filename), "wb") as handle:
            handle.write(content)
        url = f"{self.base_url}/{filename}"
        row = self.db.query(Attachment).filter(Attachment.stored_filename == filename, Attachment.company_id == self.company_id).first()
        if row is None:
            row = Attachment(
                id=str(uuid.uuid4()), original_filename=filename, stored_filename=filename,
                file_path=url, mime_type="image/png", storage_provider=self.provider,
                company_id=self.company_id, is_deleted=False,
            )
            self.db.add(row)
        row.file_path, row.storage_provider = url, self.provider
        self.db.flush()
        return row

    def asset(self, name: str, colour: tuple[int, int, int]):
        from app.models.dealer_kit import Asset

        slug = "".join(c if c.isalnum() else "-" for c in name.lower())
        attachment = self._attachment(f"icon-{slug}.png", _png(name.split()[0], colour, (96, 96)))
        row = self.db.query(Asset).filter(Asset.name == name, Asset.company_id == self.company_id).first()
        if row is not None:
            return row
        row = Asset(id=str(uuid.uuid4()), attachment_id=attachment.id, name=name, kind="icon", company_id=self.company_id)
        self.db.add(row)
        self.db.flush()
        self.say(f"asset {name}")
        return row

    # ------------------------------------------------------------- products
    def product(self, code: str, list_price: str, *, parent=None):
        from app.models.product import Brand, Product, ProductCategory, UnitOfMeasure

        row = (
            self.db.query(Product)
            .filter(func.upper(Product.product_code) == code.upper(), Product.company_id == self.company_id)
            .first()
        )
        if row is None:
            category = self.db.query(ProductCategory).filter(ProductCategory.category_code == "HANDTEST").first()
            if category is None:
                category = ProductCategory(id=str(uuid.uuid4()), category_code="HANDTEST", category_name="Hand test")
                self.db.add(category)
            brand = self.db.query(Brand).filter(Brand.brand_code == "HANDTEST").first()
            if brand is None:
                brand = Brand(id=str(uuid.uuid4()), brand_code="HANDTEST", brand_name="Hand test")
                self.db.add(brand)
            uom = self.db.query(UnitOfMeasure).filter(UnitOfMeasure.uom_code == "HTEA").first()
            if uom is None:
                uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code="HTEA", uom_name="Each")
                self.db.add(uom)
            self.db.flush()
            row = Product(
                id=str(uuid.uuid4()), product_code=code, product_name=code, category_id=category.id,
                brand_id=brand.id, base_uom_id=uom.id, list_price=Decimal(list_price), is_active=True,
                company_id=self.company_id,
            )
            self.db.add(row)
            self.db.flush()
            self.say(f"product {code}")
        row.list_price = Decimal(list_price)
        if parent is not None:
            row.variant_of_id = parent.id
        self._photo(row)
        self.db.flush()
        return row

    def _photo(self, product) -> None:
        from app.models.product import ProductAttachment

        attachment = self._attachment(f"photo-{product.product_code}.png", _png(product.product_code[3:], (31, 77, 54), (240, 160)))
        if self.db.query(ProductAttachment).filter(ProductAttachment.product_id == product.id).first():
            return
        self.db.add(
            ProductAttachment(
                product_id=product.id, attachment_id=attachment.id, is_primary=True, sort_order=0,
                access_levels=["dealer"], company_id=self.company_id,
            )
        )

    def specs(self, product, **values) -> None:
        from app.models.product_spec import ProductSpecifications

        # The catalogue's own shape: {key: {"value": ...}} (the spec pages read `["value"]`).
        entries = {key: {"value": value} for key, value in values.items()}
        row = self.db.query(ProductSpecifications).filter_by(product_id=product.id).first()
        if row is None:
            self.db.add(ProductSpecifications(id=str(uuid.uuid4()), product_id=product.id, values=entries))
        else:
            row.values = entries
        self.db.flush()

    # ------------------------------------------------------------- registry
    def registry(self) -> None:
        from app.models.product_spec import ProductSpecRegistry

        palette = [(31, 77, 54), (180, 83, 9), (29, 78, 216), (126, 34, 206), (185, 28, 28), (15, 118, 110)]
        index = 0
        for key, (label, data_type, allowed, unit, order, icons) in REGISTRY.items():
            row = self.db.query(ProductSpecRegistry).filter_by(spec_key=key).first()
            if row is None:
                row = ProductSpecRegistry(
                    id=str(uuid.uuid4()), spec_key=key, label=label, data_type=data_type,
                    allowed_values=allowed, unit=unit, is_active=True, source="user",
                )
                self.db.add(row)
            row.icon_order = order
            mapping = {}
            for value, name in icons.items():
                mapping[value] = [self.asset(name, palette[index % len(palette)]).id]
                index += 1
            row.value_icons = mapping
            self.db.flush()

    # ---------------------------------------------------------------- combo
    def combo(self, host, fixed, upgrade):
        from app.models.accessory import Accessory  # noqa: F401
        from app.models.product_combo import ProductCombo, ProductComboPart
        from app.services.accessory_service import AccessoryService
        from app.services.product_combo_service import ProductComboService

        service = ProductComboService(self.db)
        row = (
            self.db.query(ProductCombo)
            .filter(ProductCombo.host_product_id == host.id, func.lower(ProductCombo.name) == COMBO_NAME.lower())
            .first()
        )
        if row is None:
            made = service.create(host.id, COMBO_NAME, created_by=None)
            row = self.db.query(ProductCombo).filter(ProductCombo.id == made["id"]).one()
            self.say(f"combo {COMBO_NAME}")
        have = {p.part_product_id: p for p in self.db.query(ProductComboPart).filter(ProductComboPart.combo_id == row.id)}
        if fixed.id not in have:
            service.add_part(row.id, fixed.id, None)
        if upgrade.id not in have:
            service.add_part(row.id, upgrade.id, None, is_upgrade=True)
        part = self.db.query(ProductComboPart).filter_by(combo_id=row.id, part_product_id=upgrade.id).one()
        part.is_upgrade, part.topup_amount = True, Decimal("150.00")
        row.list_price, row.sell_price = Decimal("1150.00"), Decimal("949.00")
        self.db.flush()
        accessories = AccessoryService(self.db)
        items = [{"accessory_id": accessories.find_or_create(name, self.company_id).id} for name in ("DRAINER", "CHOPPING BOARD")]
        accessories.set_combo_list(row.id, items)
        self.db.commit()
        return row

    # --------------------------------------------------------------- portal
    def portal_contact(self) -> None:
        from app.models.access import RespondContact
        from app.models.company import RespondContactCompany
        from app.models.access import MarketSegment, respond_contact_market_segments

        code = "handtest-ptag"
        if self.db.query(MarketSegment).filter(MarketSegment.code == code).first() is None:
            self.db.add(MarketSegment(code=code, name="Hand test price tags", is_active=True, portal_form_types=["price_tag_request"]))
            self.db.flush()
        from app.models.respond_workspace import RespondWorkspace

        workspace = self.db.query(RespondWorkspace).filter(RespondWorkspace.space_id == "handtest").first()
        if workspace is None:  # impersonation resolves the portal space through the contact's workspace
            workspace = RespondWorkspace(
                id=str(uuid.uuid4()), space_id="handtest", name="Hand test", api_key_ciphertext="unused", is_active=True,
            )
            self.db.add(workspace)
            self.db.flush()
        contact = self.db.query(RespondContact).filter(RespondContact.name == "Hand Test Dealer").first()
        if contact is None:
            contact = RespondContact(
                id=str(uuid.uuid4()), phone_number="+60123450001", name="Hand Test Dealer", workspace_id=workspace.id,
            )
            self.db.add(contact)
            self.db.flush()
            self.db.execute(respond_contact_market_segments.insert().values(contact_id=contact.id, segment_code=code))
            self.db.add(RespondContactCompany(respond_contact_id=contact.id, company_id=self.company_id))
            self.db.flush()
            self.say("portal contact Hand Test Dealer")

    def request(self, combo, members: dict, upgrade) -> None:
        """One submitted request the staff side can open: the family line with SRTWC8354-SH-UF-300
        unticked (LP) and the combo line with its upgrade picked (SP). Marked by its debtor name."""
        from datetime import date, timedelta

        from app.models.access import RespondContact
        from app.models.price_tag import PriceTagRequest
        from app.services.price_tag_request_service import PriceTagRequestService

        debtor = "Hand Test Dealer (upgrade + variants)"
        if self.db.query(PriceTagRequest).filter(PriceTagRequest.debtor_name == debtor).first() is not None:
            return
        contact = self.db.query(RespondContact).filter(RespondContact.name == "Hand Test Dealer").one()
        base = members[BASE]
        PriceTagRequestService.submit_request(
            self.db, contact_id=contact.id, company_id=self.company_id,
            data={
                "debtor_name": debtor, "price_mode": "list",
                "needed_by_date": date.today() + timedelta(days=7),
                "lines": [
                    {"line_type": "product", "product_id": base.id, "quantity": 1, "parts": [],
                     "excluded_variant_ids": [members["SRTWC8354-SH-UF-300"].id]},
                    {"line_type": "product", "product_id": combo.host_product_id, "combo_id": combo.id, "quantity": 1,
                     "price_type": "selling", "parts": [{"product_id": upgrade.id, "role": "Upgrade"}]},
                ],
            },
        )
        self.say("request " + debtor)

    # ------------------------------------------------------------ templates
    @staticmethod
    def _layer(layer_id, kind, x, y, w, h, z, props, slot=None):
        return {
            "id": layer_id, "type": kind, "x_mm": x, "y_mm": y, "width_mm": w, "height_mm": h,
            "rotation_deg": 0, "z_index": z, "locked": False, "visible": True, "slot_binding": slot,
            "text_override": None, "props": props,
        }

    @staticmethod
    def _text(size=12, weight=400, **extra):
        return {
            "kind": "text", "text": "", "fontFamily": "DM Sans", "fontSize": size, "fontWeight": weight,
            "color": "#000000", "align": "left", "lineHeight": 1.2, "letterSpacing": 0, **extra,
        }

    @staticmethod
    def _box(header, **extra):
        return {
            "kind": "accessories", "direction": "vertical", "itemLayout": "stacked", "showHeader": True,
            "showFrame": True, "headerOnBorder": True, "headerBackground": "#ffffff",
            "nameStyle": {"fontWeight": 700}, "specStyle": {"fontWeight": 400}, "headerText": header,
            "headerFontSize": 9, "headerColor": "#1f4d36", "showBadge": False, "badgeColor": "#c2410c",
            "fill": "#f3f7f4", "stroke": "#1f4d36", "strokeWidth_mm": 0.4, "cornerRadius_mm": 3,
            "cardFill": "#ffffff", "textColor": "#111827", "imageSize_mm": 10, "nameFontSize": 8,
            "specFontSize": 6.5, "gap_mm": 1.5, "cardWidth_mm": 26, **extra,
        }

    @staticmethod
    def _upgrade_card() -> dict:
        def text(element_id, field, y, **extra):
            return {
                "id": element_id, "kind": "text", "field": field, "x_mm": 17, "y_mm": y, "width_mm": 53,
                "height_mm": 3.4, "fontSize": 7, "fontWeight": 400, "align": "left", "lineHeight": 1.1, **extra,
            }

        return {
            "width_mm": 71, "height_mm": 21.5,
            "elements": [
                {"id": "picture", "kind": "picture", "field": "picture", "x_mm": 1, "y_mm": 1.5, "width_mm": 14, "height_mm": 19, "fit": "contain"},
                text("topup", "topup", 1, prefix="TOPUP ", fontSize=10.8, fontWeight=700, color="#B91C1C", height_mm=4.6),
                text("code", "code", 5.6, fontWeight=700, fontSize=8),
                text("name", "name", 9.2),
                text("price", "price", 12.2),
                {"id": "icons", "kind": "feature_icons", "x_mm": 17, "y_mm": 15.2, "width_mm": 50, "height_mm": 5, "iconSize_mm": 4.6, "gap_mm": 0.8, "align": "left"},
            ],
        }

    def template(self, name: str, family: str, layers: list) -> object:
        from app.models.dealer_kit import TagTemplate
        from app.services.dealer_kit import tag_template_service

        row = self.db.query(TagTemplate).filter(TagTemplate.name == name, TagTemplate.archived_at.is_(None)).first()
        doc = {"width_mm": 95, "height_mm": 130, "layers": layers}
        if row is not None:
            if row.doc != doc:  # the layout changed: republish it as the next version
                row.doc = doc
                tag_template_service.publish(self.db, row, note="hand-test seed")
                self.say(f"template {name} republished")
            return row
        row = tag_template_service.create_and_publish(
            self.db, name=name, family=family, doc=doc, print_size={"width_mm": 95, "height_mm": 130}
        )
        row.company_id = self.company_id
        self.db.commit()
        self.say(f"template {name}")
        return row

    def templates(self, combo, family_host) -> None:
        from app.services.dealer_kit import product_tag_template_service as links

        L, T = self._layer, self._text
        combo_layers = [
            L("name", "text", 4, 4, 87, 8, 0, T(14, 700), "combo_name"),
            L("sp", "text", 4, 14, 87, 8, 1, T(16, 700, showCurrency=True), "sell_price"),
            L("free", "accessories", 4, 26, 87, 40, 2, self._box("FREE", direction="horizontal")),
            L("upg", "accessories", 4, 74, 87, 28, 3, self._box("UPGRADE", list="upgrades", card=self._upgrade_card())),
            L("icons", "feature_icons", 4, 106, 87, 10, 4,
              {"kind": "feature_icons", "iconSize_mm": 8, "gap_mm": 1.5, "align": "left"}),
        ]
        family_layers = [
            L("name", "text", 4, 4, 87, 8, 0, T(14, 700), "name"),
            L("code", "text", 4, 14, 87, 6, 1, T(10), "code"),
            L("lp", "text", 4, 22, 87, 8, 2, T(14, 700, showCurrency=True), "list_price"),
            L("icons", "feature_icons", 4, 34, 87, 24, 3,
              {"kind": "feature_icons", "iconSize_mm": 8, "gap_mm": 1.5, "align": "left", "subjectSlot": {"kind": "variants"}}),
        ]
        combo_template = self.template("Combo + Upgrade", "sink_combo", combo_layers)
        family_template = self.template("WC family", "wc", family_layers)
        try:
            links.set_combo_templates(self.db, combo.id, [combo_template.id], user_id=None)
            links.set_product_templates(self.db, family_host.id, [family_template.id], user_id=None)
            self.db.commit()
        except Exception as exc:  # noqa: BLE001 - report, the template can still be picked by hand
            self.db.rollback()
            self.say(f"template links not set ({exc}); link them on the product page")


def database_host(db) -> str:
    bind = db.get_bind()
    url = getattr(bind, "url", None) or bind.engine.url
    return url.host or ""


def main(argv: Optional[Sequence[str]] = None, db=None, out: Optional[TextIO] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--company", default="SRT")
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    parser.add_argument("--yes", action="store_true", help="allow a non-local database host")
    parser.add_argument("--asset-dir", default=os.path.join(os.environ.get("TMPDIR", "/tmp"), "ptag-handtest-assets"))
    parser.add_argument("--asset-base-url", default="https://localhost:8099")
    parser.add_argument("--storage-provider", default="r2", choices=["s3", "r2"])
    args = parser.parse_args(list(argv) if argv is not None else None)
    out = out or sys.stdout

    owns_session = db is None
    if owns_session:
        from app.database import SessionLocal

        db = SessionLocal()
    try:
        host = database_host(db)
        out.write(f"database host: {host or '(socket)'}\n")
        if host not in LOCAL_HOSTS and not args.yes:
            out.write("refusing: the database is not local (pass --yes to override)\n")
            return 1
        if not args.apply:
            out.write("DRY RUN: would seed the upgrade/variants hand-test data. Run with --apply.\n")
            return 0
        with company_scope(db, None):
            company = db.query(Company).filter(func.upper(Company.code) == args.company.upper()).first()
            company_id = company.id if company else None
        if company_id is None:
            out.write(f"unknown company code: {args.company}\n")
            return 1

        from app.services.audit_service import register_audit_listeners

        register_audit_listeners()
        stamp_actor(AuditActor(actor_type="system", job_id=JOB_ID), db=db)
        try:
            with company_scope(db, frozenset({company_id})):
                seeder = Seeder(db, company_id, args.asset_dir, args.asset_base_url, args.storage_provider, out)
                seeder.registry()
                sink = seeder.product(HOST_CODE, "1150.00")
                fixed = seeder.product(FIXED_CODE, "285.00")
                upgrade = seeder.product(UPGRADE_CODE, "440.00")
                seeder.specs(upgrade, steel_grade="304", mixer_type="pull_out")
                db.commit()
                combo = seeder.combo(sink, fixed, upgrade)
                members: dict[str, object] = {}
                for code, (parent, length, trap, seat, price) in FAMILY.items():
                    members[code] = seeder.product(code, price, parent=members.get(parent) if parent else None)
                    values = {"trap_length": length, "trap_type": trap}
                    if seat:
                        values["seat_material"] = seat
                    seeder.specs(members[code], **values)
                db.commit()
                seeder.templates(combo, members[BASE])
                seeder.portal_contact()
                db.commit()
                seeder.request(combo, members, upgrade)
                db.commit()
        finally:
            clear_actor(db)
        out.write("done\n")
        return 0
    finally:
        if owns_session:
            db.close()


if __name__ == "__main__":
    sys.exit(main())
