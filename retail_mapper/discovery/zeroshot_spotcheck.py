#!/usr/bin/env python3
"""Fast spot-check: 50 hand-picked products through zero-shot classifier.
Streams results to stdout so we can watch in real time."""
from __future__ import annotations
import sys, sqlite3, time, warnings
warnings.filterwarnings('ignore')

DB = '/Users/jamiebarton/Desktop/esha_audit_bundle/data/master_products.db'

# 50 products that hit user's pain points + variety
TEST_TITLES = [
    # almond milk variants
    'UNSWEETENED CHOCOLATE ORGANIC ALMONDMILK',
    'ORIGINAL ALMOND BEVERAGE',
    'PUMPKIN SPICE FLAVORED ALMONDMILK',
    'VANILLA ALMONDMILK',
    'CHOCOLATE ALMONDMILK SWEETENED',
    'ALMOND NOG, HOLIDAY',
    # eggnog
    'EGG NOG',
    'HOLIDAY EGG NOG',
    'LIGHT EGG NOG',
    # corn dog vs hot dog
    'CORN DOG',
    'MINI CORN DOGS, BEEF',
    'CLASSIC CORN DOGS',
    'UNCURED BEEF HOT DOG',
    'TURKEY HOT DOG',
    # chicken nugget
    'CHICKEN NUGGETS',
    'BREADED CHICKEN NUGGETS',
    'PLANT BASED CHICKEN NUGGETS',
    # ice cream
    'ICE CREAM SANDWICH, VANILLA',
    'CHUNKY MONKEY BANANA ICE CREAM',
    'CHERRY GARCIA ICE CREAM',
    'VANILLA ICE CREAM',
    # chocolate / chocolate milk
    'CHOCOLATE MILK',
    'TRUMOO LOWFAT CHOCOLATE MILK',
    'MILK CHOCOLATE BAR',
    'DARK CHOCOLATE BAR',
    'WHITE CHOCOLATE CHIPS',
    # mayo
    'CHIPOTLE MAYO',
    'AVOCADO OIL WITH A HINT OF LIME MAYONNAISE DRESSING',
    'OLIVE OIL MAYONNAISE',
    'REGULAR MAYONNAISE',
    # cheese
    'SHARP CHEDDAR CHEESE',
    'EXTRA SHARP CHEDDAR',
    'MOZZARELLA CHEESE',
    # yogurt
    'VANILLA GREEK NONFAT YOGURT WITH STRAWBERRIES',
    'PLAIN GREEK YOGURT',
    'DRINKABLE STRAWBERRY YOGURT',
    # snacks / combos
    'ROASTED RED PEPPER HUMMUS WITH FLATBREAD',
    'HUMMUS WITH PITA CHIPS',
    'APPLE SLICES WITH PEANUT BUTTER',
    # other pain
    'APPLE NOODLE KUGEL',
    'FRIED APPLES',
    'CINNAMON APPLE PIE FILLING',
    # variety
    'PEANUT BUTTER, CREAMY',
    'EXTRA VIRGIN OLIVE OIL',
    'SPARKLING WATER LIME',
    'FRENCH BREAD PIZZA, CHEESE',
    'BACON, FULLY COOKED',
    'BABY CARROTS',
    'COCONUT OIL VIRGIN',
    'BEYOND BURGER PLANT BASED PATTY',
]

LABELS = [
    'plant-based milk', 'dairy milk', 'eggnog', 'fruit juice', 'smoothie', 'soda',
    'cheese', 'yogurt', 'butter', 'sour cream', 'cream',
    'ice cream', 'ice cream sandwich', 'frozen yogurt',
    'chocolate candy', 'gummy candy', 'mints',
    'potato chip', 'tortilla chip', 'popcorn', 'pretzel', 'cracker',
    'cookie', 'cake', 'pie', 'muffin', 'donut',
    'bread', 'tortilla', 'bagel',
    'pasta', 'rice', 'cereal', 'oatmeal', 'flour',
    'mayonnaise', 'ketchup', 'mustard', 'salad dressing', 'salsa', 'hummus',
    'pasta sauce', 'cooking sauce', 'hot sauce', 'bbq sauce',
    'cooking oil', 'olive oil', 'coconut oil',
    'sugar', 'honey', 'maple syrup', 'jam jelly',
    'corn dog', 'hot dog', 'chicken nugget', 'fish stick',
    'pizza', 'frozen meal', 'frozen burger', 'meatball', 'sausage', 'bacon',
    'fresh fruit', 'fresh vegetable', 'canned fruit', 'canned vegetable',
    'frozen fruit', 'frozen vegetable', 'baby carrots',
    'mixed nuts', 'peanut butter', 'nut butter',
    'protein powder', 'protein shake',
    'water', 'sparkling water', 'tea', 'coffee',
    'hummus with crackers or chips combo',
    'apple slices with peanut butter combo',
    'casserole or baked dish',
    'fried fruit',
    'dessert filling',
]

print("Loading model (DeBERTa-v3-base-mnli) on MPS...", flush=True)
from transformers import pipeline
clf = pipeline('zero-shot-classification',
               model='MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli', device='mps')
print("Ready. Classifying 50 products...\n", flush=True)

t0 = time.time()
for i, title in enumerate(TEST_TITLES, 1):
    text = title.lower()
    res = clf(text, LABELS, multi_label=False)
    top3 = list(zip(res['labels'][:3], res['scores'][:3]))
    elapsed = time.time() - t0
    rate = i / elapsed
    print(f"[{i:>2}/50  {elapsed:5.1f}s  {rate:.1f}/s]  {title[:50]}", flush=True)
    for lbl, sc in top3:
        marker = '★' if sc == top3[0][1] else ' '
        print(f"      {marker} {sc:.3f}  {lbl}", flush=True)
    print('', flush=True)

print(f"\nTotal: {time.time()-t0:.1f}s for 50 products = {50/(time.time()-t0):.1f}/sec")
print(f"Projected for 462,646 products: {462646/(50/(time.time()-t0))/60:.0f} minutes")
