# Funnel audit — what to look at

Generated 2026-04-28 20:41:18

## Top-line numbers

- Total products: 462,646
- Products with sub_leaf == 'other': 166,069 (35.9%)
- Total L1 clusters: 3,000
- Clusters with >50% 'other': 728

## Cluster-by-cluster audit files

Open each in a spreadsheet. Sort by `sub_leaf_label`; the `other` rows are listed first.
Compare `product_description` + `ingredients_top5` against `sub_leaf_label`. The `what_should_it_be` column is my heuristic guess for the right leaf.

- **`audit/cluster_1463_almond_milk.csv`** — 384 products, 240 (62%) in 'other'
- **`audit/cluster_662_almond_milk_alt.csv`** — 115 products, 93 (81%) in 'other'
- **`audit/cluster_799_egg_nog.csv`** — 111 products, 6 (5%) in 'other'
- **`audit/cluster_1917_salsa_swallowed_hummus.csv`** — 213 products, 14 (7%) in 'other'
- **`audit/cluster_2320_mayo_lime.csv`** — 110 products, 14 (13%) in 'other'
- **`audit/cluster_1590_corn_dog.csv`** — 171 products, 25 (15%) in 'other'
- **`audit/cluster_1912_chicken_nuggets.csv`** — 159 products, 16 (10%) in 'other'
- **`audit/cluster_20_ice_cream_sandwich.csv`** — 252 products, 26 (10%) in 'other'
- **`audit/cluster_2586_milk_chocolate.csv`** — 693 products, 86 (12%) in 'other'
- **`audit/cluster_1947_chocolate_milk.csv`** — 212 products, 130 (61%) in 'other'
- **`audit/cluster_1344_chunky_monkey.csv`** — 282 products, 48 (17%) in 'other'

## Worst dumps

`audit/other_dump_top20.csv` — for the 20 clusters with the most `other` products, 10 sample 'other' members per cluster, with what they should have been.

## Top 20 worst clusters by 'other' count

| cluster_id | tree_label | modal_bfc | n_total | n_other | pct |
|---|---|---|---|---|---|
| 672 | Sauce, cilantro & lime, Mexican Creations, cooking | Oriental, Mexican & Ethnic Sau | 941 | 888 | 94% |
| 1638 | Popcorn, caramel corn, with peanuts | Popcorn, Peanuts, Seeds & Rela | 826 | 806 | 98% |
| 237 | Juice Drink, mango nectar, canned | Fruit & Vegetable Juice, Necta | 897 | 795 | 89% |
| 690 | Seasoning, fajita, marinade, dry mix | Seasoning Mixes, Salts, Marina | 808 | 731 | 90% |
| 1934 | Spice, coriander, seeds | Herbs & Spices | 741 | 714 | 96% |
| 2296 | Cookie, biscuit, Nice, serving | Cookies & Biscuits | 786 | 698 | 89% |
| 1691 | Seasoning, garlic salt, California blend | Seasoning Mixes, Salts, Marina | 875 | 685 | 78% |
| 735 | Pastry, Mini Crisps, cinnamon brown sugar | Croissants, Sweet Rolls, Muffi | 700 | 678 | 97% |
| 89 | Cracker, biscuits for cheese, assorted | Crackers & Biscotti | 686 | 572 | 83% |
| 573 | Salsa, restaurant style | Dips & Salsa | 809 | 544 | 67% |
| 341 | Cookie, biscuit, Nice, serving | Cookies & Biscuits | 578 | 540 | 93% |
| 1789 | Soda, lemon lime twist | Soda | 707 | 524 | 74% |
| 2080 | Potstickers, vegetable, with o sauce, frozen | Frozen Appetizers & Hors D'oeu | 562 | 518 | 92% |
| 991 | Syrup, sweetner, sugar free | Syrups & Molasses | 682 | 511 | 75% |
| 643 | Cookie, chocolate mint cake, SnackWell's | Cakes, Cupcakes, Snack Cakes | 589 | 507 | 86% |
| 225 | Snack, bagel, chips | Chips, Pretzels & Snacks | 732 | 505 | 69% |
| 986 | Pasta Dish, SpaghettiOs, original, easy open | Pasta by Shape & Type | 537 | 504 | 94% |
| 390 | Fruit, mixed, tropical, canned | Pre-Packaged Fruit & Vegetable | 511 | 501 | 98% |
| 1807 | Soup, chicken vegetable, hearty, dry mix | Other Soups | 642 | 476 | 74% |
| 508 | Dip, salsa, grande | Dips & Salsa | 547 | 462 | 84% |
