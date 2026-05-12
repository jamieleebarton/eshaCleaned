# Per-recipe calc A/B — Hestia (recipes2.csv FNDDS) vs Ours (SKU-priced)

Sample: 100 recipes; sorted by abs(cost diff) descending.

## Aggregate stats

| Metric | Hestia avg | Ours avg | Δ |
|---|---:|---:|---:|
| total cost ($) | 34.92 | 9.10 | -25.82 |
| kcal/recipe | 3361 | 2697 | -663 |
| mass/recipe (g) | 1549 | 1397 | -153 |

## Top 10 cost divergences

| rid | title | hestia $ | ours $ | Δ$ | hestia kcal | ours kcal | mass diff |
|---|---|---:|---:|---:|---:|---:|---:|
| 189779 | Smoked Whole Brisket With Burnt Ends | 227.30 | 48.33 | -178.97 | 10917 | 10803 | +632g |
| 3344 | Penne Piperade | 94.19 | 6.82 | -87.37 | 1221 | 764 | -186g |
| 49508 | Snappy Turtles | 83.35 | 3.67 | -79.68 | 15338 | 2089 | -1454g |
| 213799 | Grilled Asian-Influenced Rib-Eye Steak | 85.66 | 9.68 | -75.98 | 3068 | 2763 | +59g |
| 465055 | Stir-Fried Prawns in Chili Bean Sauce | 82.75 | 8.62 | -74.13 | 1091 | 664 | -131g |
| 168229 | Roast Sirloin of Beef with Au Jus | 155.20 | 85.47 | -69.73 | 22769 | 23795 | +335g |
| 394792 | Bourbon-Pecan Tart | 72.23 | 8.63 | -63.60 | 6710 | 3594 | -482g |
| 206246 | Ridiculously Healthy Banana Oatmeal Co | 62.75 | 2.17 | -60.58 | 1794 | 1317 | -62g |
| 509854 | Creamy Shrimp Dijon with Cognac | 65.95 | 5.61 | -60.34 | 1432 | 1252 | -14g |
| 260663 | Blueberry Cobbler | 75.82 | 15.63 | -60.19 | 2133 | 675 | -9g |

## Top 5 — full ingredient-by-ingredient comparison


### 189779 — Smoked Whole Brisket With Burnt Ends
- Hestia: $227.30  /  10917 kcal  /  1343g prot  /  4114g mass
- Ours:   $48.33  /  10803 kcal  /  1334g prot  /  4746g mass

| line | grams | SKU | $line | kcal |
|---|---:|---|---:|---:|
| 1⁄2 tablespoon coriander seed | 6.0 | McCormick Whole Coriander Seed, 1.25 oz | 0.93 | 0.0 |
| 1 tablespoon fresh ground pepper | 8.0 | McCormick Pepper Black Whole, 7.0 oz Bottle | 0.29 | 16.0 |
| 1 teaspoon oregano (Mexican if available) | 2.0 | McCormick Crushed Red Pepper with Oregano and Garlic Al | 0.09 | 0.0 |
| 1 teaspoon garlic powder | 3.0 | Great Value Garlic Powder, 3.4 oz | 0.03 | 5.0 |
| 1 tablespoon celery salt | 10.0 |  | 0.00 | 0.0 |
| 3 tablespoons kosher salt | 54.0 | Kroger® Salt | 0.06 | 0.0 |
| 1⁄4 cup brown sugar | 55.0 | Great Value Light Brown Sugar, 32 oz | 0.12 | 209.0 |
| 1 tablespoon ground cumin | 9.0 | Best Press Toddler Food Texture and Advanced Ingredient | 0.18 | 0.0 |
| 2 tablespoons paprika | 18.0 | McCormick Paprika | 0.91 | 60.0 |
| 3 tablespoons Worcestershire sauce | 45.0 | Kroger® Worcestershire Sauce | 0.15 | 35.0 |
| 10 lbs beef brisket, whole | 4536.0 | Private Selection® Natural Angus Beef Brisket with Salt | 45.58 | 10478.0 |

### 3344 — Penne Piperade
- Hestia: $94.19  /  1221 kcal  /  47g prot  /  1532g mass
- Ours:   $6.82  /  764 kcal  /  19g prot  /  1346g mass

| line | grams | SKU | $line | kcal |
|---|---:|---|---:|---:|
| 4 cups penne | 400.0 | Kroger® 100% Whole Grain Penne Rigate Pasta | 0.78 | 428.0 |
| 1 tablespoon extra virgin olive oil | 14.0 | Pompeian Smooth Extra Virgin Olive Oil - 32 fl oz | 0.19 | 126.0 |
| 1 green bell pepper, cored, seeded, and cut into p | 150.0 | Fresh Large Green Bell Pepper | 0.29 | 0.0 |
| 1 red bell pepper, cored, seeded, and cut into pen | 150.0 | Mezzetta™ Mild Roasted Red Bell Peppers | 1.55 | 0.0 |
| 1 yellow bell pepper, cored, seeded, and cut into  | 150.0 | Fresh Yellow Bell Pepper | 0.56 | 0.0 |
| 1 medium onion, thinly sliced | 110.0 | Jumbo Yellow Onions | 0.22 | 0.0 |
| 3 cloves garlic, thinly sliced | 9.0 | Garlic | 0.02 | 26.0 |
| 3 thin slices prosciutto, cut into bite-size piece | 30.0 | Del Duca, Dry Cured Prosciutto, Sliced Pork Deli Charcu | 1.40 | 58.0 |
| 1 ounce bacon, chopped (optional) | 28.0 | Smithfield® Hometown Original Bacon | 0.00 | 0.0 |
| 2 large tomatoes, finely chopped, with juices | 300.0 | Kroger® Vine Ripe Tomatoes | 1.58 | 105.0 |
| 1 teaspoon hot paprika | 3.0 | McCormick Paprika | 0.15 | 10.0 |
| Salt, to taste | 2.0 | Kroger® Salt | 0.00 | 0.0 |
| Black pepper, to taste | 0.5 | McCormick Pepper Black Whole, 7.0 oz Bottle | 0.00 | 0.0 |
| 1/2 cup flat leaf parsley, chopped | 30.0 | Parsley | 0.08 | 11.0 |
| 1 ounce feta cheese, crumbled (optional) | 28.0 | Athenos Crumbled Traditional Feta Cheese 12 oz, Refrige | 0.00 | 0.0 |

### 49508 — Snappy Turtles
- Hestia: $83.35  /  15338 kcal  /  38g prot  /  2036g mass
- Ours:   $3.67  /  2089 kcal  /  52g prot  /  582g mass

| line | grams | SKU | $line | kcal |
|---|---:|---|---:|---:|
| 1/2 cup butter, softened | 113.0 | Land O Lakes Salted Butter Half Sticks | 0.87 | 432.0 |
| 1/2 cup brown sugar | 100.0 | Great Value Light Brown Sugar, 32 oz | 0.21 | 380.0 |
| 1 egg | 50.0 | Kroger® Extra Large White Eggs | 0.11 | 92.0 |
| 3/4 teaspoon vanilla extract | 3.8 | Watkins Pure Lemon Extract, 32 fl oz (Liquids, plastic  | 0.09 | 4.0 |
| 1 1/2 cups all-purpose flour | 195.0 | Great Value All-Purpose Unbleached Flour, 5 lb Bag | 0.17 | 521.0 |
| 1/4 teaspoon baking soda | 1.2 | Great Value Baking Soda, 4 lb | 0.00 | 0.0 |
| 1/4 teaspoon salt | 1.5 | Kroger® Salt | 0.00 | 0.0 |
| 15 pecan halves | 75.0 | Planters Lightly Salted Mixed Nuts with Peanuts, Almond | 1.83 | 459.0 |
| 3 semi-sweet chocolate baking squares, melted | 42.0 | Great Value Semi Sweet Chocolate Chips, 36 oz Bag | 0.38 | 202.0 |

### 213799 — Grilled Asian-Influenced Rib-Eye Steaks
- Hestia: $85.66  /  3068 kcal  /  185g prot  /  1134g mass
- Ours:   $9.68  /  2763 kcal  /  198g prot  /  1193g mass

| line | grams | SKU | $line | kcal |
|---|---:|---|---:|---:|
| 4 rib eye steaks (about 1 inch thick) | 680.0 | Ribeye Extra Thin Beef Steak Strips, Choice Angus Beef, | 4.40 | 1625.0 |
| 1/2 cup soy sauce | 120.0 | Great Value Less Sodium Soy Sauce, 15 fl oz | 0.43 | 64.0 |
| 3 tablespoons oyster sauce | 45.0 | Heinz Golden Mark Oyster Sauce 9.2oz | 0.37 | 23.0 |
| 2 tablespoons lime juice | 30.0 | Rose's Sweetened Lime Juice | 0.03 | 3.0 |
| 4 tablespoons sesame oil | 56.0 | Imperial Dragon 100% Pure Sesame Seed Oil, 5 fl oz | 1.22 | 495.0 |
| 3 tablespoons crushed red pepper flakes | 18.0 | Great Value Crushed Red Pepper, 12 oz | 0.38 | 12.0 |
| 5 garlic cloves, minced | 15.0 | Garlic | 0.03 | 43.0 |
| 1/2 bunch fresh cilantro, chopped | 15.0 | Fresh Produce, Whole Green Cilantro, 1 Bunch | 0.18 | 3.0 |
| 4 tablespoons honey | 84.0 | Great Value Honey, 12 oz Plastic Bear | 0.97 | 255.0 |
| 2 tablespoons Dijon mustard | 28.0 | Grey Poupon Dijon Mustard, 10 oz Bottle | 0.46 | 77.0 |
| 2 tablespoons prepared horseradish | 30.0 | Meyer's Ground Horseradish | 0.26 | 151.0 |
| 1/4 cup bourbon | 60.0 | Evan Williams Black Label Straight Bourbon, 1.75 L Bott | 0.65 | 0.0 |
| 1 tablespoon ground cumin | 6.0 | Best Press Toddler Food Texture and Advanced Ingredient | 0.12 | 0.0 |
| 1 tablespoon ground black pepper | 6.0 | Kroger® Pure Ground Black Pepper Shaker | 0.19 | 12.0 |
| Extra fresh cilantro, chopped, for topping | 10.0 | Fresh Produce, Whole Green Cilantro, 1 Bunch | 0.00 | 0.0 |
| Extra black pepper, for topping | 0.5 | Kroger® Pure Ground Black Pepper Shaker | 0.00 | 0.0 |

### 465055 — Stir-Fried Prawns in Chili Bean Sauce
- Hestia: $82.75  /  1091 kcal  /  65g prot  /  1111g mass
- Ours:   $8.62  /  664 kcal  /  67g prot  /  980g mass

| line | grams | SKU | $line | kcal |
|---|---:|---|---:|---:|
| 1 tablespoon vegetable oil | 14.0 | Great Value Vegetable Oil, Heart Healthy and Versatile, | 0.03 | 126.0 |
| 12 large raw prawns, shelled, deveined, and halved | 300.0 | Great Value Frozen Cooked Peeled, Tail-off Salad Shrimp | 4.52 | 270.0 |
| 1 teaspoon garlic, crushed | 5.0 | Garlic | 0.01 | 14.0 |
| 1 teaspoon ginger, grated | 5.0 | Gourmet Garden Ginger Stir-In Paste | 0.21 | 15.0 |
| 1 cup bean sprouts | 100.0 | Polar, Bean Sprouts, 14.4 oz. | 0.46 | 30.0 |
| 6 spring onions, sliced diagonally | 90.0 | Green Onions | 0.20 | 29.0 |
| 150 g asparagus, cut into 2-inch lengths, blanched | 150.0 | Green Asparagus | 0.99 | 28.0 |
| 1 red capsicum, thinly sliced | 150.0 | Mezzetta™ Mild Roasted Red Bell Peppers | 1.55 | 0.0 |
| 1⁄2 cup chicken stock | 120.0 | Swanson Chicken Stock, 48 oz Carton | 0.36 | 79.0 |
| 1 1⁄2 tablespoons light soy sauce | 22.0 | Great Value Less Sodium Soy Sauce, 15 fl oz | 0.08 | 12.0 |
| 1⁄2 tablespoon dark soy sauce | 7.0 | Great Value Less Sodium Soy Sauce, 15 fl oz | 0.02 | 4.0 |
| 1 1⁄2 teaspoons oyster sauce | 9.0 | Heinz Golden Mark Oyster Sauce 9.2oz | 0.07 | 5.0 |
| 1 1⁄2 teaspoons chili bean sauce (Yeo's), to taste | 9.0 | Kroger® Mixed Chili Beans in Mild Sauce | 0.00 | 0.0 |
| 1 teaspoon sesame oil | 5.0 | Imperial Dragon 100% Pure Sesame Seed Oil, 5 fl oz | 0.11 | 44.0 |
| 1 teaspoon cornflour, mixed with 1 tablespoon wate | 3.0 | Great Value Corn Flour, 4.0 lb | 0.00 | 8.0 |

## Top 10 mass-divergence (recipes where total_mass disagrees most)

| rid | title | hestia mass | ours mass | Δ |
|---|---|---:|---:|---:|
| 179556 | Homemade Spaghetti Sauce (with Meat Option | 4584 | 2847 | -1737g |
| 185131 | Naudine's Potato and Spinach Bake | 3341 | 1784 | -1557g |
| 49508 | Snappy Turtles | 2036 | 582 | -1454g |
| 348947 | The Best Homemade Chicken Noodle Soup | 8003 | 6750 | -1252g |
| 319320 | Braised Lamb Breast with Root Vegetables | 844 | 2034 | +1190g |
| 311938 | Low Carb Fried Chicken | 729 | 1837 | +1108g |
| 470893 | Thai Vegetable and Shrimp Noodle Soup | 2884 | 1779 | -1105g |
| 71970 | Candy Corn & Peanut-Topped Brownies | 2840 | 1832 | -1008g |
| 426476 | Gatorade-Limoncello Margarita | 2327 | 1360 | -967g |
| 370714 | Tacos Árabes (Arabian Tacos) | 2058 | 1120 | -938g |