"""The eight starter tag templates, as layer documents (S3b slice 5, D32).

One function per family, each returning a ``TagTemplateDoc``-shaped dict that
``app.schemas.price_tag.TagTemplateDocModel`` validates. Kept apart from
``seed_tag_templates.py`` so the layouts can be read, diffed and tested without
a database or a storage bucket anywhere near them.

**Where the numbers come from.** Every position is millimetres inside the tag
box, transcribed from ``documentation/plans/dealer-kit/seed-assets/pdf-geometry.json``
- which holds each text span, image box and filled rectangle of
``Sorento Pricetag Template.pdf`` in mm on A4. The tag box origin is subtracted,
so a layer at ``(4.5, 50.7)`` is at the same place on the tag as the span that
reads ``SRTKS2435`` on page 1. Point sizes are the PDF's own.

**The templates are UNBOUND.** Slots are present, ``binding`` is empty: a
template is the layout for a FAMILY, not for one product. Marketing drops a
product in and every still-linked layer resolves (ADR 0008 - a document holds
bindings and layout, never prices, names or image URLs).

**Fonts.** The originals are set in Century Gothic and Myriad Pro, which are
licensed; marketing uploads them as ``kind='font'`` assets later and the
templates pick them up by family NAME, so the string here is what has to change
then and nothing else. Until that happens the seed names the free stand-ins the
README chose: Bebas Neue for codes and prices, Jost (a Futura class face) for
the wordmark and body.
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional

# --------------------------------------------------------------------------- #
# Brand constants. Read off the PDF's own fills, not guessed.
# --------------------------------------------------------------------------- #

GREEN = "#445235"
PRICE_RED = "#ea2329"
INK = "#231f20"
MUTED = "#636466"
GREY_PANEL = "#f1f2f2"
WHITE = "#ffffff"

DISPLAY_FONT = "Bebas Neue"
BODY_FONT = "Jost"

#: Every asset name the eight documents can ask for. Names, never ids: an id is
#: minted by the upload and differs per environment, so the seed resolves the
#: name at run time and the layout stays a pure function.
BADGE_SUS304 = "Badge Sus304"
BADGE_ULTRASONIC = "Badge Ultrasonic Nano"
BADGE_25YR = "Badge 25Yr Warranty"
BADGE_ANTI_BACTERIA = "Badge Anti Bacteria"
BADGE_LIFETIME_CERAMIC = "Badge Lifetime Ceramic"
BADGE_5YR_FLUSH = "Badge 5Yr Flush Fittings"
BADGE_2YR_SEAT = "Badge 2Yr Seat Cover"
BADGE_TRAP_6IN = "Badge Trap 6In"
BADGE_TRAP_8IN = "Badge Trap 8In"
BADGE_TRAP_10IN = "Badge Trap 10In"
BADGE_TRAP_P = "Badge Trap P"
BADGE_UF_SEAT = "Badge Uf Seat Cover"
BADGE_STAINLESS_BODY = "Badge Stainless Steel Body"
DIAGRAM_WATER = "Diagram Water Inlet Outlet"
DIAGRAM_REMOTE = "Diagram Remote Control"
LOGO_TWISTER = "Logo Twister Flush"
LABEL_PULL_OUT = "Label Pull Out"
ICON_PLUS = "Icon Plus Connector"

#: The WC's smart-feature row, in the order page 8 prints them, with the caption
#: under each.
SMART_FEATURES = [
    ("Icon Smart Flushing", "Smart\nFlushing"),
    ("Icon Foot Flush Button", "Foot\nFlushing\nButton"),
    ("Icon Seat Auto Close", "Seat\nCover\nAuto\nClose / Open"),
    ("Icon Built In Nozzle", "Built-In\nNozzle"),
    ("Icon Warm Air Dryer", "Warm\nAir\nDryer"),
    ("Icon Uv Light", "Uv\nLight"),
]

#: How ``seed_tag_templates`` resolves a name to the id the upload minted.
AssetLookup = Callable[[str], str]


# --------------------------------------------------------------------------- #
# Layer construction
#
# A tiny builder rather than dict literals: eight documents of forty layers each
# written by hand is where a missing `rotation_deg` or a z_index collision comes
# from, and neither shows up until somebody opens the template.
# --------------------------------------------------------------------------- #


class _Doc:
    """Accumulates layers, minting stable ids and monotonic z-indexes.

    Ids are ``<family>-<slug>-<n>`` rather than uuids ON PURPOSE: a seed that
    is run twice, or run on staging and then on production, produces the same
    document byte for byte, so "did the seed change anything" is answerable by
    comparing documents instead of by trusting the idempotency check.
    """

    def __init__(self, family: str, width_mm: float, height_mm: float) -> None:
        self.family = family
        self.width_mm = width_mm
        self.height_mm = height_mm
        self.layers: list[dict] = []
        self._counter = 0

    # -- ids ---------------------------------------------------------------
    def _next_id(self, slug: str) -> str:
        self._counter += 1
        return f"{self.family}-{slug}-{self._counter}"

    # -- generic ------------------------------------------------------------
    def add(
        self,
        slug: str,
        layer_type: str,
        x: float,
        y: float,
        w: float,
        h: float,
        props: dict,
        *,
        slot: Optional[str] = None,
        rotation: float = 0,
    ) -> str:
        layer_id = self._next_id(slug)
        self.layers.append(
            {
                "id": layer_id,
                "type": layer_type,
                "x_mm": round(x, 2),
                "y_mm": round(y, 2),
                "width_mm": round(w, 2),
                "height_mm": round(h, 2),
                "rotation_deg": rotation,
                "z_index": len(self.layers),
                "locked": False,
                "visible": True,
                "slot_binding": slot,
                "text_override": None,
                "props": props,
            }
        )
        return layer_id

    # -- typed helpers ------------------------------------------------------
    def rect(
        self,
        slug: str,
        x: float,
        y: float,
        w: float,
        h: float,
        fill: str,
        *,
        radius: float = 0,
        stroke: str = "",
        stroke_width: float = 0,
        shape: str = "rect",
    ) -> str:
        return self.add(
            slug,
            "shape",
            x,
            y,
            w,
            h,
            {
                "kind": "shape",
                "shape": shape,
                "fill": fill,
                "stroke": stroke,
                "strokeWidth": stroke_width,
                "cornerRadius": radius,
            },
        )

    def text(
        self,
        slug: str,
        x: float,
        y: float,
        w: float,
        h: float,
        content: str,
        *,
        size: float,
        font: str = BODY_FONT,
        weight: int = 400,
        color: str = INK,
        align: str = "left",
        line_height: float = 1.25,
        letter_spacing: float = 0,
        slot: Optional[str] = None,
        rotation: float = 0,
    ) -> str:
        return self.add(
            slug,
            "text",
            x,
            y,
            w,
            h,
            {
                "kind": "text",
                "text": content,
                "fontFamily": font,
                "fontSize": size,
                "fontWeight": weight,
                "color": color,
                "align": align,
                "lineHeight": line_height,
                "letterSpacing": letter_spacing,
            },
            slot=slot,
            rotation=rotation,
        )

    def image(
        self,
        slug: str,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        slot: Optional[str] = None,
        mask: str = "none",
        fit: str = "contain",
        asset_id: Optional[str] = None,
    ) -> str:
        """An image layer. ``asset_id`` is library artwork; otherwise a SLOT.

        A slot with no source is the point of a template: the picture arrives
        when a product is bound, and until then the canvas draws the empty-image
        state rather than somebody else's photo baked into the layout.
        """
        return self.add(
            slug,
            "image",
            x,
            y,
            w,
            h,
            {
                "kind": "image",
                "source": {"type": "asset", "assetId": asset_id} if asset_id else None,
                "fit": fit,
                "maskShape": mask,
            },
            slot=slot,
        )

    def badge(self, slug: str, x: float, y: float, w: float, h: float, asset_id: str) -> str:
        return self.add(
            slug, "badge", x, y, w, h, {"kind": "badge", "assetId": asset_id}
        )

    def price_badge(
        self,
        slug: str,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        variant: str,
        fill: str = PRICE_RED,
        text_color: str = WHITE,
        radius: float = 1.5,
        show_nett: bool = True,
    ) -> str:
        return self.add(
            slug,
            "price_badge",
            x,
            y,
            w,
            h,
            {
                "kind": "price_badge",
                "variant": variant,
                "fill": fill,
                "textColor": text_color,
                "cornerRadius": radius,
                "showNett": show_nett,
            },
            slot="sell_price" if variant == "promo" else "list_price",
        )

    def group(self, slug: str, children: Iterable[str], *, bound: bool = True) -> str:
        """Wrap layers in a group so the whole block re-binds in one action.

        ``binding`` is present and EMPTY on a seeded block. Empty rather than
        absent because the block is meant to be bound - the inspector's binding
        panel is what the designer is looking for - and a template that binds to
        a product would print that product's tag for every request.
        """
        child_ids = list(children)
        boxes = [layer for layer in self.layers if layer["id"] in set(child_ids)]
        x = min(b["x_mm"] for b in boxes)
        y = min(b["y_mm"] for b in boxes)
        right = max(b["x_mm"] + b["width_mm"] for b in boxes)
        bottom = max(b["y_mm"] + b["height_mm"] for b in boxes)
        return self.add(
            slug,
            "group",
            x,
            y,
            right - x,
            bottom - y,
            {
                "kind": "group",
                "children": child_ids,
                "binding": {} if bound else None,
            },
        )

    # -- output -------------------------------------------------------------
    def build(self) -> dict:
        return {
            "layers": self.layers,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
        }


# --------------------------------------------------------------------------- #
# Shared pieces
# --------------------------------------------------------------------------- #


def _brand_band(doc: _Doc, *, height: float, wordmark_x: float, wordmark_w: float) -> None:
    """The green header band and the Sorento wordmark on it.

    The wordmark is vector artwork in the PDF (it is neither a text span nor an
    embedded image), so it is seeded as TEXT in the stand-in face. Marketing
    swapping in the real logo is an image layer over the same box.
    """
    doc.rect("band", 0, 0, doc.width_mm, height, GREEN)
    doc.text(
        "wordmark",
        wordmark_x,
        height / 2 - 4.5,
        wordmark_w,
        9,
        "Sorento",
        size=20,
        font=BODY_FONT,
        weight=600,
        color=WHITE,
        align="right",
        letter_spacing=0.4,
    )


def _empty_product_block(
    doc: _Doc,
    slug: str,
    x: float,
    y: float,
    *,
    width: float,
    image_h: float = 20.0,
    code_size: float = 6.6,
    spec_size: float = 3.2,
) -> str:
    """One unbound alternative: photo, code, name, spec lines, price badge.

    The same six layers ``buildProductBlock`` drops in the editor, at the size
    the flyer's alternatives columns use, with no product behind any of them.
    """
    parts = [
        doc.image(f"{slug}-image", x, y, width, image_h, slot="product_image"),
        doc.text(
            f"{slug}-code",
            x,
            y + image_h + 1.0,
            width,
            4.0,
            "Product code",
            size=code_size,
            font=DISPLAY_FONT,
            weight=700,
            slot="code",
        ),
        doc.text(
            f"{slug}-name",
            x,
            y + image_h + 5.2,
            width,
            4.0,
            "Product name",
            size=spec_size + 0.6,
            color=MUTED,
            slot="name",
        ),
        doc.text(
            f"{slug}-specs",
            x,
            y + image_h + 9.4,
            width,
            8.0,
            "Specification lines",
            size=spec_size,
            color=MUTED,
            line_height=1.35,
            slot="spec_lines",
        ),
        doc.price_badge(
            f"{slug}-price", x, y + image_h + 18.0, width - 2, 8.5, variant="promo"
        ),
    ]
    return doc.group(slug, parts)


def _connector(doc: _Doc, slug: str, label: str, x: float, y: float) -> None:
    """An ``OR`` / ``+`` connector: a shape and a text, as D28 specifies.

    Two layers rather than one, so a designer can restyle the pill without
    retyping the word, and delete the word without losing the pill.
    """
    doc.rect(f"{slug}-pill", x, y, 5.0, 5.0, WHITE, shape="ellipse", stroke=GREEN, stroke_width=0.4)
    doc.text(
        f"{slug}-label",
        x,
        y + 1.0,
        5.0,
        3.4,
        label,
        size=5.5,
        font=DISPLAY_FONT,
        weight=700,
        color=GREEN,
        align="center",
    )


def _kitchen_badge_row(doc: _Doc, asset: AssetLookup, *, y: float, size: tuple[float, float]) -> None:
    """The four kitchen badges, at the pitch page 1 and page 2 both use."""
    width, height = size
    for index, name in enumerate(
        (BADGE_SUS304, BADGE_ULTRASONIC, BADGE_25YR, BADGE_ANTI_BACTERIA)
    ):
        doc.badge(f"badge-{index}", 6.4 + index * 15.0, y, width, height, asset(name))


def _list_price_text(doc: _Doc, x: float, y: float, width: float, *, size: float) -> str:
    """The flyer's ``LP: RM 1,550`` line, as a label plus a bound figure.

    Two layers rather than one, because a slot resolves to the WHOLE of a text
    layer: a single layer reading "LP: RM 0,000" would either keep saying that
    (an invented price on a real tag) or resolve to a bare "RM 1,550" with the
    "LP:" gone. Splitting them lets the label stay a label and the figure come
    from the pricing engine. Returns the FIGURE's id, which is the layer the
    product block owns.
    """
    # Wide enough for "LP:" set in the condensed display face at this size.
    # 0.28 clipped it to "L" on the first pass, which read as a stray letter.
    label_width = size * 0.62
    doc.text(
        "list-price-label",
        x,
        y,
        label_width,
        size * 0.55,
        "LP:",
        size=size,
        font=DISPLAY_FONT,
        weight=700,
    )
    return doc.text(
        "list-price",
        x + label_width + 0.4,
        y,
        max(width - label_width - 0.4, 8.0),
        size * 0.55,
        "RM 0,000",
        size=size,
        font=DISPLAY_FONT,
        weight=700,
        slot="list_price",
    )


# --------------------------------------------------------------------------- #
# 1. Sink combo - page 1, 125.9 x 88.6 mm
# --------------------------------------------------------------------------- #


def build_sink_combo(asset: AssetLookup) -> dict:
    doc = _Doc("sink-combo", 125.9, 88.6)

    _brand_band(doc, height=19.2, wordmark_x=84.0, wordmark_w=36.0)
    _kitchen_badge_row(doc, asset, y=5.7, size=(15.6, 14.4))

    # -- the sink itself, left column -------------------------------------
    main = [
        doc.image("hero", 1.0, 22.2, 46.9, 31.1, slot="product_image"),
        # The round cut-out the flyer drops over the bottom-left of the photo,
        # captioned in place. Circle-masked, so it reads as a callout rather
        # than a second product.
        doc.image("callout", 2.4, 37.0, 15.0, 15.0, mask="circle", fit="cover"),
        doc.text(
            "callout-caption",
            5.4,
            43.8,
            9.0,
            4.4,
            "NANO\nGRAIN",
            size=4.9,
            font=DISPLAY_FONT,
            weight=700,
            align="center",
            line_height=1.15,
        ),
    ]
    doc.text(
        "code",
        4.5,
        50.7,
        44.0,
        6.0,
        "Product code",
        size=11.2,
        font=DISPLAY_FONT,
        weight=700,
        slot="code",
    )
    doc.text(
        "dimensions",
        4.5,
        55.6,
        44.0,
        4.4,
        "L000xW000xH000mm",
        size=8.8,
        color=MUTED,
        slot="dimensions",
    )
    doc.text(
        "spec-lines",
        4.5,
        59.2,
        44.0,
        7.6,
        "Specification lines",
        size=8.8,
        color=MUTED,
        line_height=1.3,
        slot="spec_lines",
    )
    _list_price_text(doc, 4.5, 67.7, 44.0, size=7.7)
    # The tag's own promotional price, bottom right. Added before the group so
    # it re-binds with the rest of the block rather than keeping the previous
    # product's figures.
    price = doc.price_badge("price", 90.5, 74.0, 32.9, 11.6, variant="promo")
    doc.group(
        "product",
        main
        + _slots_of(doc, ("code", "dimensions", "spec-lines", "list-price"))
        + [price],
    )

    # -- accessories strip, bottom left ------------------------------------
    strip = [
        doc.text(
            "accessories-title",
            4.8,
            71.9,
            42.0,
            4.2,
            "Accessories Included",
            size=4.2,
            weight=600,
            slot="included_accessories",
        )
    ]
    for index, caption in enumerate(("Drainer", "Chopping\nBoard", "Knife\nRack", "Soap\nDispenser")):
        x = 4.8 + index * 9.0
        strip.append(doc.image(f"accessory-{index}", x, 74.7, 8.4, 8.4))
        strip.append(
            doc.text(
                f"accessory-caption-{index}",
                x - 0.4,
                83.1,
                9.2,
                4.6,
                caption,
                size=3.8,
                align="center",
                line_height=1.2,
            )
        )
    doc.group("accessories", strip, bound=False)

    # -- alternatives row, right column ------------------------------------
    # Page 1 prints six taps in two rows of three, all six of them the same
    # thing: which tap comes with this sink. The seed lays ONE row of three with
    # the connectors the flyer uses (a leading `+`, `OR` between), because a row
    # is what a designer duplicates and D28 leaves every piece an ordinary layer
    # after the drop.
    _connector(doc, "plus", "+", 45.5, 34.0)
    _empty_product_block(doc, "alternative-a", 51.5, 21.0, width=20.0)
    _connector(doc, "or-1", "OR", 72.5, 34.0)
    _empty_product_block(doc, "alternative-b", 78.5, 21.0, width=20.0)
    _connector(doc, "or-2", "OR", 99.5, 34.0)
    _empty_product_block(doc, "alternative-c", 105.5, 21.0, width=20.0)

    return doc.build()


# --------------------------------------------------------------------------- #
# 2. Sink ala carte - page 2, 125.9 x 88.6 mm
# --------------------------------------------------------------------------- #


def build_sink_ala_carte(asset: AssetLookup) -> dict:
    doc = _Doc("sink-ala-carte", 125.9, 88.6)

    _brand_band(doc, height=19.1, wordmark_x=84.0, wordmark_w=36.0)
    _kitchen_badge_row(doc, asset, y=5.7, size=(15.5, 14.3))

    hero = doc.image("hero", 5.3, 21.0, 69.5, 63.0, slot="product_image")
    doc.text(
        "code", 78.5, 34.4, 43.0, 7.6, "Product code",
        size=13.9, font=DISPLAY_FONT, weight=700, slot="code",
    )
    doc.text(
        "dimensions", 78.5, 42.4, 43.0, 5.2, "L000xW000xH000mm",
        size=10.4, color=MUTED, slot="dimensions",
    )
    doc.text(
        "spec-lines", 78.5, 47.4, 43.0, 8.0, "Specification lines",
        size=8.8, color=MUTED, line_height=1.3, slot="spec_lines",
    )
    price_line = _list_price_text(doc, 78.5, 55.6, 43.0, size=7.6)
    badge = doc.price_badge("price", 79.5, 62.0, 32.6, 11.5, variant="promo")

    doc.group(
        "product",
        [hero, *_slots_of(doc, ("code", "dimensions", "spec-lines")), price_line, badge],
    )
    return doc.build()


# --------------------------------------------------------------------------- #
# 3. Art basin - page 3, 124.6 x 87.6 mm
# --------------------------------------------------------------------------- #


def build_art_basin(asset: AssetLookup) -> dict:
    """Image left, code and dimensions right, one badge. No warranty row.

    ``asset`` is unused here and that is the point: the basin tag carries no
    badges at all, and giving it some to look consistent would be inventing
    marketing claims for a product nobody made them about.
    """
    doc = _Doc("art-basin", 124.6, 87.6)

    _brand_band(doc, height=19.0, wordmark_x=83.0, wordmark_w=36.0)

    hero = doc.image("hero", 11.8, 28.4, 63.7, 50.1, slot="product_image")
    doc.text(
        "code", 84.4, 41.4, 38.0, 6.2, "Product code",
        size=11.3, font=DISPLAY_FONT, weight=700, slot="code",
    )
    doc.text(
        "dimensions", 84.4, 47.0, 38.0, 4.4, "L000xW000xH000mm",
        size=8.9, color=MUTED, slot="dimensions",
    )
    doc.text(
        "spec-lines", 84.4, 51.0, 38.0, 5.4, "Specification lines",
        size=8.9, color=MUTED, line_height=1.25, slot="spec_lines",
    )
    badge = doc.price_badge("price", 81.1, 57.2, 32.5, 11.5, variant="list_only")

    doc.group(
        "product",
        [hero, *_slots_of(doc, ("code", "dimensions", "spec-lines")), badge],
    )
    return doc.build()


# --------------------------------------------------------------------------- #
# 4. Mirror cabinet - page 4, 147.7 x 103.9 mm
# --------------------------------------------------------------------------- #


def build_mirror_cabinet(asset: AssetLookup) -> dict:
    doc = _Doc("mirror-cabinet", 147.7, 103.9)

    _brand_band(doc, height=22.5, wordmark_x=100.0, wordmark_w=42.0)

    hero = doc.image("hero", 9.6, 24.0, 57.3, 57.3, slot="product_image")

    # The second photo the flyer shows with the doors open, and its label. A
    # plain image layer, not a slot: which of the product's photos is the inside
    # view is a choice a designer makes per product.
    inside = doc.image("inside-view", 59.8, 46.4, 31.1, 31.1)
    doc.text(
        "inside-view-label",
        59.8,
        42.4,
        31.1,
        4.2,
        "INSIDE VIEW",
        size=8.3,
        weight=700,
        color="#030505",
    )
    doc.text(
        "dim-light-label",
        59.8,
        37.8,
        31.1,
        3.6,
        "DIM LIGHT",
        size=6.9,
        weight=700,
        color="#030505",
    )

    # The two light colours, shown as a pair of swatch photos with captions.
    lights = [
        doc.text(
            "light-title", 25.5, 75.4, 45.0, 4.4, "TWO LIGHT COLOR :", size=8.7, weight=600
        ),
        doc.image("light-white", 37.6, 80.0, 7.0, 7.0, mask="circle", fit="cover"),
        doc.image("light-yellow", 48.9, 80.0, 7.0, 7.0, mask="circle", fit="cover"),
        doc.text("light-white-label", 34.6, 88.0, 13.0, 4.4, "WHITE", size=8.7, align="center"),
        doc.text("light-yellow-label", 45.9, 88.0, 13.0, 4.4, "YELLOW", size=8.7, align="center"),
    ]
    doc.group("light-colours", lights, bound=False)

    doc.text(
        "code",
        96.9,
        36.3,
        48.0,
        7.0,
        "Product code",
        size=13.4,
        font=DISPLAY_FONT,
        weight=700,
        slot="code",
    )
    doc.text(
        "name", 96.9, 42.2, 48.0, 5.2, "Product name", size=10.5, color=MUTED, slot="name"
    )
    doc.text(
        "spec-body-material",
        96.9,
        46.9,
        48.0,
        5.2,
        "Body Material :",
        size=10.5,
        color=MUTED,
    )
    doc.text(
        "dimensions",
        96.9,
        51.6,
        48.0,
        5.2,
        "L000xW000xH000mm",
        size=10.5,
        color=MUTED,
        slot="dimensions",
    )
    doc.text(
        "spec-lines",
        96.9,
        56.4,
        48.0,
        5.2,
        "Feature:",
        size=10.5,
        color=MUTED,
        slot="spec_lines",
    )
    price_line = _list_price_text(doc, 97.2, 60.0, 48.0, size=12.8)
    badge = doc.price_badge("price", 96.2, 72.0, 38.6, 13.6, variant="promo")

    doc.group(
        "product",
        [
            hero,
            inside,
            *_slots_of(doc, ("code", "name", "dimensions", "spec-lines")),
            price_line,
            badge,
        ],
    )
    return doc.build()


# --------------------------------------------------------------------------- #
# 5. Shower set - page 7, 131.5 x 92.0 mm
# --------------------------------------------------------------------------- #


def build_shower_set(asset: AssetLookup) -> dict:
    doc = _Doc("shower-set", 131.5, 92.0)

    _brand_band(doc, height=19.9, wordmark_x=88.0, wordmark_w=40.0)

    hero = doc.image("hero", 14.9, 26.0, 19.0, 51.0, slot="product_image")

    doc.text(
        "code",
        35.6,
        27.6,
        55.0,
        6.2,
        "Product code",
        size=12.0,
        font=DISPLAY_FONT,
        weight=700,
        slot="code",
    )
    doc.text(
        "name", 35.6, 34.6, 55.0, 4.6, "Product name", size=8.6, weight=600, color=MUTED, slot="name"
    )
    doc.text(
        "spec-lines",
        35.6,
        38.4,
        55.0,
        25.0,
        "- Specification line\n- Specification line\n- Specification line",
        size=8.6,
        color=MUTED,
        line_height=1.42,
        slot="spec_lines",
    )
    price_line = _list_price_text(doc, 35.6, 64.3, 40.0, size=8.0)
    badge = doc.price_badge("price", 39.2, 71.4, 34.2, 12.1, variant="promo")

    # The plumbing diagram sits in its own grey panel on the right, with the two
    # labels the flyer prints under it.
    doc.rect("diagram-panel", 94.5, 23.5, 27.0, 62.0, GREY_PANEL)
    doc.text(
        "diagram-title",
        94.5,
        33.5,
        27.0,
        9.0,
        "WATER\nCOME FROM\nANGLE VALVE",
        size=7.1,
        weight=700,
        align="center",
        line_height=1.2,
    )
    doc.badge("diagram", 93.7, 43.8, 27.9, 28.6, asset(DIAGRAM_WATER))
    doc.text("diagram-inlet", 95.5, 81.8, 12.0, 2.6, "WATER INLET", size=3.7, weight=700)
    doc.text("diagram-outlet", 108.0, 81.8, 13.0, 2.6, "WATER OUTLET", size=3.7, weight=700)

    # The shower body's material claim, which page 6 carries as a badge.
    doc.badge("badge-stainless", 8.0, 23.0, 14.0, 13.0, asset(BADGE_STAINLESS_BODY))

    doc.group(
        "product",
        [hero, *_slots_of(doc, ("code", "name", "spec-lines")), price_line, badge],
    )
    return doc.build()


# --------------------------------------------------------------------------- #
# 6. WC - page 8, 131.6 x 92.1 mm
# --------------------------------------------------------------------------- #


def build_wc(asset: AssetLookup) -> dict:
    doc = _Doc("wc", 131.6, 92.1)

    _brand_band(doc, height=20.0, wordmark_x=90.0, wordmark_w=40.0)
    for index, name in enumerate(
        (BADGE_LIFETIME_CERAMIC, BADGE_5YR_FLUSH, BADGE_2YR_SEAT)
    ):
        doc.badge(f"badge-{index}", 12.9 + index * 14.4, 4.0, 15.0, 13.9, asset(name))

    # The photo, and the flush-brand logo beside it, as page 8 lays them out:
    # picture on the left half, everything the customer reads on the right.
    hero = doc.image("hero", 4.0, 23.0, 52.0, 46.0, slot="product_image")
    doc.badge("twister-logo", 26.0, 21.0, 27.9, 8.3, asset(LOGO_TWISTER))

    # The trap options, as the row of small badges the flyer prints above the
    # code. Two rows of two plus the seat-cover badge, clear of the text block.
    traps = []
    for index, name in enumerate(
        (BADGE_TRAP_6IN, BADGE_TRAP_8IN, BADGE_TRAP_10IN, BADGE_TRAP_P)
    ):
        traps.append(
            doc.badge(
                f"trap-{index}",
                59.0 + (index % 2) * 10.5,
                23.0 + (index // 2) * 8.4,
                9.6,
                7.6,
                asset(name),
            )
        )
    traps.append(doc.badge("trap-uf", 80.5, 23.0, 8.0, 8.6, asset(BADGE_UF_SEAT)))
    doc.group("traps", traps, bound=False)

    doc.text(
        "code",
        59.0,
        40.0,
        70.0,
        6.4,
        "Product code",
        size=12.2,
        font=DISPLAY_FONT,
        weight=700,
        slot="code",
    )
    doc.text(
        "name", 59.0, 46.4, 70.0, 4.2, "Product name", size=7.9, color="#221f20", slot="name"
    )
    doc.text(
        "flushing-technology",
        59.0,
        50.0,
        70.0,
        4.2,
        "Flushing Technology",
        size=7.9,
        color="#221f20",
    )
    doc.text(
        "dimensions",
        59.0,
        53.6,
        70.0,
        4.2,
        "D: L000xW000xH000mm",
        size=7.9,
        color="#221f20",
        slot="dimensions",
    )
    doc.text(
        "spec-lines",
        59.0,
        57.2,
        70.0,
        11.0,
        "S-Trap: Bottom Outlet\nP-Trap: Horizontal Outlet",
        size=7.9,
        color="#221f20",
        line_height=1.25,
        slot="spec_lines",
    )

    # The smart WC's feature row: six icons with captions under them, along the
    # bottom of the tag where page 8's second tag prints them.
    smart = []
    for index, (icon_name, caption) in enumerate(SMART_FEATURES):
        x = 4.0 + index * 9.0
        smart.append(doc.badge(f"smart-icon-{index}", x + 1.0, 71.0, 6.6, 6.6, asset(icon_name)))
        smart.append(
            doc.text(
                f"smart-caption-{index}",
                x,
                78.2,
                8.6,
                12.0,
                caption,
                size=4.6,
                align="center",
                line_height=1.15,
            )
        )
    doc.group("smart-features", smart, bound=False)

    # The remote, and the label naming it, on the smart variant of this tag.
    doc.badge("remote-diagram", 58.0, 70.0, 11.0, 15.0, asset(DIAGRAM_REMOTE))
    doc.text(
        "remote-label", 55.0, 85.6, 18.0, 3.4, "REMOTE CONTROL", size=5.4, weight=700,
        align="center",
    )

    badge = doc.price_badge("price", 87.1, 76.5, 28.7, 9.7, variant="list_only")

    doc.group(
        "product",
        [hero, *_slots_of(doc, ("code", "name", "dimensions", "spec-lines")), badge],
    )
    return doc.build()


# --------------------------------------------------------------------------- #
# 7. Urinal - page 8 (bottom tag), 131.6 x 92.1 mm
# --------------------------------------------------------------------------- #


def build_wc_urinal(asset: AssetLookup) -> dict:
    doc = _Doc("wc-urinal", 131.6, 92.1)

    _brand_band(doc, height=20.0, wordmark_x=90.0, wordmark_w=40.0)
    doc.badge("badge-ceramic", 36.5, 4.0, 15.0, 13.9, asset(BADGE_LIFETIME_CERAMIC))

    hero = doc.image("hero", 24.3, 21.8, 36.6, 66.4, slot="product_image")

    doc.text(
        "code",
        75.1,
        43.0,
        50.0,
        6.0,
        "Product code",
        size=11.3,
        font=DISPLAY_FONT,
        weight=700,
        slot="code",
    )
    doc.text(
        "name", 75.2, 48.3, 50.0, 4.2, "Product name", size=8.1, color="#030404", slot="name"
    )
    doc.text(
        "dimensions",
        75.2,
        51.7,
        50.0,
        4.2,
        "Dimension : L000xW000xH000mm",
        size=8.1,
        color="#030404",
        slot="dimensions",
    )
    doc.text(
        "spec-lines",
        75.2,
        55.1,
        50.0,
        8.4,
        "Top Inlet",
        size=8.1,
        color="#030404",
        line_height=1.3,
        slot="spec_lines",
    )
    badge = doc.price_badge("price", 86.1, 75.6, 28.4, 9.6, variant="list_only")

    doc.group(
        "product",
        [hero, *_slots_of(doc, ("code", "name", "dimensions", "spec-lines")), badge],
    )
    return doc.build()


# --------------------------------------------------------------------------- #
# 8. Bathroom furniture set - page 11, 94.0 x 134.2 mm portrait
# --------------------------------------------------------------------------- #


def build_furniture_set(asset: AssetLookup) -> dict:
    """The only portrait tag: a green surround with a white card inside it.

    The green is the tag itself rather than a header band, so the wordmark sits
    ABOVE the card and the price badge below it, both on the green.
    """
    doc = _Doc("furniture-set", 94.0, 134.2)

    doc.rect("surround", 0, 0, 94.0, 134.2, GREEN)
    doc.text(
        "wordmark",
        50.0,
        9.0,
        38.0,
        9.0,
        "Sorento",
        size=20,
        weight=600,
        color=WHITE,
        align="right",
        letter_spacing=0.4,
    )
    doc.rect("card", 4.2, 23.0, 85.9, 107.0, WHITE)

    hero = doc.image("hero", 8.0, 30.0, 42.0, 45.0, slot="product_image")

    # The pull-out drawer shot, with the label the flyer prints beside it.
    doc.image("pull-out", 10.6, 73.5, 9.9, 14.9)
    doc.badge("pull-out-label", 24.0, 74.5, 14.0, 5.2, asset(LABEL_PULL_OUT))

    # The honeycomb close-up, cut to a circle, with its caption set around the
    # top of the disc.
    doc.image("honeycomb", 8.0, 90.0, 22.0, 22.0, mask="circle", fit="cover")
    doc.text(
        "honeycomb-caption",
        8.0,
        86.0,
        22.0,
        4.0,
        "HONEYCOMB",
        size=5.4,
        font=DISPLAY_FONT,
        weight=700,
        color=MUTED,
        align="center",
        rotation=-8,
    )

    code = doc.text(
        "code",
        52.9,
        28.4,
        34.0,
        10.0,
        "Set code",
        size=11.0,
        font=DISPLAY_FONT,
        weight=700,
        line_height=1.15,
        slot="code",
    )
    doc.text(
        "set-heading",
        52.4,
        38.3,
        37.0,
        4.2,
        "N IN 1 BATHROOM FURNITURE",
        size=6.4,
        weight=700,
        color="#030404",
    )
    members = doc.text(
        "set-members",
        52.4,
        42.2,
        36.0,
        32.0,
        "- CODE (NAME) L000xW000xH000mm",
        size=6.8,
        color=INK,
        line_height=1.42,
        slot="set_members",
    )
    price_line = _list_price_text(doc, 54.2, 75.8, 34.0, size=8.8)
    badge = doc.price_badge("price", 53.1, 108.1, 34.8, 12.3, variant="promo")

    doc.group("product", [hero, code, members, price_line, badge])
    return doc.build()


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


def _slots_of(doc: _Doc, slugs: Iterable[str]) -> list[str]:
    """Ids of the layers added under these slugs, in document order.

    A lookup rather than passing ids around, because the stack helpers above add
    four or five layers each and threading their ids back through every caller
    is how a group ends up naming a layer that is not there.
    """
    wanted = set(slugs)
    return [
        layer["id"]
        for layer in doc.layers
        if _slug_of(layer["id"], doc.family) in wanted
    ]


def _slug_of(layer_id: str, family: str) -> str:
    """``sink-ala-carte-spec-lines-7`` -> ``spec-lines``."""
    trimmed = layer_id[len(family) + 1 :] if layer_id.startswith(family + "-") else layer_id
    return trimmed.rsplit("-", 1)[0]


#: family key -> (display name, builder). The key is what
#: ``tag_templates.family`` stores and what the tag sheet designer matches a
#: request line against.
SEED_TEMPLATES: list[tuple[str, str, Callable[[AssetLookup], dict]]] = [
    ("sink_combo", "Kitchen Sink - Combo", build_sink_combo),
    ("ala_carte", "Kitchen Sink - Ala Carte", build_sink_ala_carte),
    ("art_basin", "Art Basin", build_art_basin),
    ("mirror_cabinet", "Mirror Cabinet", build_mirror_cabinet),
    ("shower", "Exposed Shower Set", build_shower_set),
    ("wc", "Water Closet", build_wc),
    ("urinal", "Urinal", build_wc_urinal),
    ("furniture_set", "Bathroom Furniture Set", build_furniture_set),
]


def print_size_of(doc: dict) -> dict:
    """``print_size`` always agrees with the document it describes."""
    return {"width_mm": doc["width_mm"], "height_mm": doc["height_mm"]}


__all__ = [
    "SEED_TEMPLATES",
    "AssetLookup",
    "build_art_basin",
    "build_furniture_set",
    "build_mirror_cabinet",
    "build_shower_set",
    "build_sink_ala_carte",
    "build_sink_combo",
    "build_wc",
    "build_wc_urinal",
    "print_size_of",
]
