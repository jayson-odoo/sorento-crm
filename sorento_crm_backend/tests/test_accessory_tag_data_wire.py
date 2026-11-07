"""PRICETAG-ACCESSORY-DESIGNER fix round: remark / images / colours reach the wire.

`response_model` drops any field the schema does not declare, so the product tag-data route is asserted
ON THE WIRE (the service-level payload test cannot see this).
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests.test_dealer_kit_tag_data_routes import SORENTO, _product, _signing_works, api  # noqa: F401
from tests._pg_fixture import unique_code


def _picture(db, accessory, order, name, hex_):
    from app.models.accessory import AccessoryImage
    from app.models.resources import Attachment

    stem = unique_code("zztacc")
    attachment = Attachment(
        id=str(uuid.uuid4()),
        original_filename=f"{stem}.jpg",
        stored_filename=f"{stem}.jpg",
        file_path=f"https://cdn.example.test/accessory_image/{stem}.jpg",
        mime_type="image/jpeg",
        storage_provider="s3",
        company_id=SORENTO,
        is_deleted=False,
    )
    db.add(attachment)
    db.flush()
    db.add(
        AccessoryImage(
            accessory_id=accessory.id, attachment_id=attachment.id, sort_order=order,
            colour_name=name, colour_hex=hex_,
        )
    )
    db.flush()


def test_product_tag_data_carries_accessory_remark_images_and_colours(api):  # noqa: F811
    from app.models.accessory import Accessory, ProductAccessory

    db, _as = api
    product = _product(db)
    item = Accessory(
        id=str(uuid.uuid4()), company_id=SORENTO, name=unique_code("COLANDER").upper(), remark="Follows sink"
    )
    db.add(item)
    db.flush()
    _picture(db, item, 0, "Black", "#1f2937")
    _picture(db, item, 1, "Grey", "#9ca3af")
    db.add(ProductAccessory(id=str(uuid.uuid4()), product_id=product.id, accessory_id=item.id, sort_order=0))
    db.flush()

    with TestClient(app) as client:
        res = client.get(f"/api/v1/dealer-kit/products/{product.id}/tag-data")

    assert res.status_code == 200, res.text
    (entry,) = res.json()["accessories"]
    assert entry["remark"] == "Follows sink"
    assert [i["colour_hex"] for i in entry["images"]] == ["#1f2937", "#9ca3af"]
    assert [i["colour_name"] for i in entry["images"]] == ["Black", "Grey"]
    assert all(i["url"] for i in entry["images"])
    assert entry["colours"] == [{"name": "Black", "hex": "#1f2937"}, {"name": "Grey", "hex": "#9ca3af"}]
