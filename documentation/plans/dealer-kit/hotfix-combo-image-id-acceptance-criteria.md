# UAC: HOTFIX-COMBO-IMAGE-ID

1. A combo whose free items include a catalogue product that has a photo: the host product's Combos
   card loads (`GET /products/{id}/combos` 200), and the combo's accessories list loads
   (`GET /product-combos/{combo_id}/accessories` 200).
2. The same holds for a product's own accessories list (`GET /products/{id}/accessories` 200) and for
   saving either list (PUT 200).
3. The product entry still shows its photo: `image.attachment_id` and `images[0].attachment_id` are the
   product's photo; `images[0].id` is null (it is not an accessory picture).
4. Library accessory entries are unchanged: their pictures keep their ids, so the picture choice works.
