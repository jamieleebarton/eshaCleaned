# Per-recipe Hestia vs Ours — REAL shopping cost (whole packages)


Sample 100 recipes; ours uses sum of cheapest whole package per unique SKU.


## Aggregate

| Metric | Hestia | Ours (line-attrib) | Ours (whole cart) |
|---|---:|---:|---:|
| avg cost ($) | 34.92 | 9.20 | **22.25** |
| Δ vs Hestia | — | -25.72 | **-12.67** |

## Top 15 cost divergences (whole-cart vs Hestia)

| rid | title | hestia $ | ours line $ | ours WHOLE $ | n_pkg | surplus g |
|---|---|---:|---:|---:|---:|---:|
| 189779 | Smoked Whole Brisket With Burnt Ends | 227.30 | 49.32 | **69.71** | 13 | 2621 |
| 168229 | Roast Sirloin of Beef with Au Jus | 155.20 | 69.73 | **88.81** | 11 | 4510 |
| 3344 | Penne Piperade | 94.19 | 6.94 | **28.62** | 11 | 3013 |
| 49508 | Snappy Turtles | 83.35 | 5.14 | **23.39** | 9 | 4764 |
| 394792 | Bourbon-Pecan Tart | 72.23 | 9.61 | **22.46** | 9 | 2604 |
| 213799 | Grilled Asian-Influenced Rib-Eye Steak | 85.66 | 20.53 | **39.36** | 15 | 1770 |
| 206246 | Ridiculously Healthy Banana Oatmeal Co | 62.75 | 3.51 | **16.65** | 6 | 1162 |
| 465055 | Stir-Fried Prawns in Chili Bean Sauce | 82.75 | 10.50 | **37.19** | 13 | 5566 |
| 295345 | Grilled Fruited Pork Chops | 52.33 | 4.25 | **16.70** | 6 | 1579 |
| 71970 | Candy Corn & Peanut-Topped Brownies | 56.15 | 8.98 | **20.64** | 12 | 3516 |
| 195954 | Caramel Pecan Brownies | 0.00 | 21.80 | **34.43** | 13 | 9655 |
| 466206 | Tomato Breakfast Sauté with Onions and | 37.17 | 2.05 | **3.13** | 3 | 527 |
| 260663 | Blueberry Cobbler | 75.82 | 17.16 | **42.37** | 15 | 7077 |
| 115930 | Garlic-Lemon Mushroom Chicken | 51.43 | 5.17 | **18.38** | 11 | 4699 |
| 193084 | Classic Turkey Gravy from Pan Juices | 48.96 | 3.05 | **16.07** | 8 | 4594 |

## Brisket walkthrough (rid 189779)

- Hestia cached: $227.30
- Ours line-attributable: $49.32
- Ours WHOLE CART: $69.71 (13 packages)

| picked | size | $ | n × pack | grams needed |
|---|---:|---:|---:|---:|
| McCormick Whole Coriander Seed, 1.25 oz | 35g | $5.49 | 1 | 6g |
| El Guapo Non-GMO Whole Black Pepper, 0.62 oz Bag | 18g | $1.48 | 1 | 8g |
| El Guapo No Artificial Flavors Whole Oregano Oregano Me | 14g | $1.52 | 1 | 2g |
| Great Value Garlic Powder, 3.4 oz | 96g | $1.00 | 1 | 3g |
| Kroger® Salt | 739g | $0.79 | 1 | 54g |
| Great Value Light Brown Sugar, 32 oz | 907g | $1.94 | 1 | 55g |
| El Guapo No Artificial Flavors Whole Cumin, 0.75 oz Bag | 21g | $1.54 | 1 | 9g |
| McCormick Paprika | 59g | $2.99 | 1 | 18g |
| Great Value Worcestershire Sauce, 10 fl oz | 296g | $1.00 | 1 | 45g |
| Private Selection® Natural Angus Beef Brisket with Salt | 1293g | $12.99 | 4 | 4536g |

## Snappy Turtles walkthrough (rid 49508)

- Hestia cached: $83.35
- Ours line-attributable: $5.14
- Ours WHOLE CART: $23.39 (9 packages)

| picked | size | $ | n × pack | grams needed |
|---|---:|---:|---:|---:|
| Land O Lakes Salted Butter in Half Sticks, 4 Half Stick | 227g | $2.68 | 1 | 113g |
| Great Value Light Brown Sugar, 32 oz | 907g | $1.94 | 1 | 100g |
| Kroger® Large White Eggs | 59g | $1.09 | 1 | 50g |
| Watkins Cherry Extract with Other Natural Flavors, 2 fl | 59g | $3.11 | 1 | 4g |
| Great Value All-Purpose Unbleached Flour, 5 lb Bag | 2268g | $1.97 | 1 | 195g |
| Great Value Baking Soda, 1 lb | 454g | $0.92 | 1 | 1g |
| Kroger® Salt | 739g | $0.79 | 1 | 2g |
| Planters Lightly Salted Mixed Nuts with Peanuts, Almond | 292g | $7.12 | 1 | 75g |
| Great Value Semi-Sweet Chocolate Baking Chips, 12 oz Ba | 340g | $3.77 | 1 | 42g |