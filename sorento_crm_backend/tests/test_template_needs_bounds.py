"""M1: `template_needs` reads a stored document, so a hostile or damaged one must not crash or balloon."""
from app.services.dealer_kit.template_needs import template_needs


def _doc(*layers):
    return {"layers": list(layers)}


def _layer(slot):
    return {"id": "x", "type": "text", "props": {"kind": "text", "subjectSlot": slot}}


def test_a_huge_group_index_is_skipped_not_allocated():
    needs = template_needs(_doc(_layer({"kind": "pick", "group": 10**9, "index": 0})))
    assert needs == {"fixed": 0, "groups": [], "upgrades": 0}


def test_the_bounds_are_inclusive_of_the_last_allowed_position():
    needs = template_needs(
        _doc(
            _layer({"kind": "pick", "group": 31, "index": 63}),
            _layer({"kind": "fixed", "index": 63}),
            _layer({"kind": "upgrade", "index": 63}),
        )
    )
    assert len(needs["groups"]) == 32 and needs["groups"][31] == 64
    assert needs["fixed"] == 64 and needs["upgrades"] == 64


def test_a_huge_index_is_skipped():
    needs = template_needs(_doc(_layer({"kind": "fixed", "index": 64}), _layer({"kind": "upgrade", "index": 10**9})))
    assert needs == {"fixed": 0, "groups": [], "upgrades": 0}


def test_bools_and_non_ints_are_skipped():
    needs = template_needs(
        _doc(
            _layer({"kind": "fixed", "index": True}),
            _layer({"kind": "pick", "group": True, "index": 0}),
            _layer({"kind": "pick", "group": 0, "index": "2"}),
            _layer({"kind": "upgrade", "index": 1.5}),
        )
    )
    assert needs == {"fixed": 0, "groups": [], "upgrades": 0}


def test_a_non_dict_layer_or_props_is_skipped_without_a_crash():
    needs = template_needs(_doc("not a layer", None, 5, {"props": "nope"}, {"props": None}, _layer({"kind": "fixed", "index": 1})))
    assert needs == {"fixed": 2, "groups": [], "upgrades": 0}


def test_a_non_list_layers_or_doc_is_empty():
    assert template_needs({"layers": "x"}) == {"fixed": 0, "groups": [], "upgrades": 0}
    assert template_needs("x") == {"fixed": 0, "groups": [], "upgrades": 0}


def test_the_strict_doc_model_accepts_a_slot_and_refuses_an_out_of_range_one():
    import pytest
    from pydantic import ValidationError

    from app.schemas.price_tag import TagTemplateDocModel

    def doc(slot):
        layer = {
            "id": "a", "type": "text", "x_mm": 0, "y_mm": 0, "width_mm": 5, "height_mm": 5,
            "rotation_deg": 0, "z_index": 0, "locked": False, "visible": True,
            "slot_binding": "code", "text_override": None,
            "props": {
                "kind": "text", "text": "", "fontFamily": "x", "fontSize": 9, "fontWeight": 400,
                "color": "#000", "align": "left", "lineHeight": 1.2, "letterSpacing": 0, "subjectSlot": slot,
            },
        }
        return {"layers": [layer], "width_mm": 105, "height_mm": 148}

    TagTemplateDocModel.model_validate(doc({"kind": "pick", "group": 1, "index": 2}))
    TagTemplateDocModel.model_validate(doc({"kind": "main"}))
    with pytest.raises(ValidationError):
        TagTemplateDocModel.model_validate(doc({"kind": "pick", "group": 99, "index": 0}))
    with pytest.raises(ValidationError):
        TagTemplateDocModel.model_validate(doc({"kind": "wat"}))
