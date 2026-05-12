"""Final safety filter with all agent-learned rules."""
import csv, sys
from pathlib import Path

REJECT_PATTERNS = [
    # Soda leaks
    ('product_description', 'root beer', 'proposed_esha_desc', 'beer', 'reject_rootbeer_to_beer'),
    ('product_description', 'ginger beer', 'proposed_esha_desc', 'beer', 'reject_gingerbeer_to_beer'),
    ('proposed_esha_desc', 'water, tap', None, None, 'reject_tap_water'),
    ('proposed_esha_desc', 'tangerines, fresh', None, None, 'reject_produce_leak'),
    ('proposed_esha_desc', 'carbohydrate gel', None, None, 'reject_gel_leak'),
    # Frozen veg
    ('branded_food_category', 'frozen vegetables', 'proposed_esha_desc', 'canned', 'reject_frozen_to_canned'),
    ('branded_food_category', 'frozen vegetables', 'proposed_esha_desc', 'sprouts', 'reject_frozen_to_sprouts'),
    ('branded_food_category', 'frozen vegetables', 'proposed_esha_desc', 'fresh', 'reject_frozen_to_fresh'),
    # Dressing
    ('product_description', 'vinaigrette', 'proposed_esha_desc', 'balsamic', 'reject_vinaigrette_flatten'),
    ('product_description', 'light mayonnaise', 'proposed_esha_desc', 'mayonnaise', 'reject_mayo_flatten'),
    ('product_description', 'fat free mayonnaise', 'proposed_esha_desc', 'mayonnaise', 'reject_mayo_flatten'),
    ('product_description', 'real mayonnaise', 'proposed_esha_desc', 'mayonnaise', 'reject_mayo_flatten'),
    ('product_description', 'honey mustard mayonnaise', 'proposed_esha_desc', 'mayonnaise', 'reject_mayo_flatten'),
    ('product_description', 'chipotle mayonnaise', 'proposed_esha_desc', 'mayonnaise', 'reject_mayo_flatten'),
    # Nut/seed -> veg
    ('product_description', 'peanut', 'proposed_esha_desc', 'squash', 'reject_nut_to_veg'),
    ('product_description', 'almond', 'proposed_esha_desc', 'squash', 'reject_nut_to_veg'),
    ('product_description', 'cashew', 'proposed_esha_desc', 'squash', 'reject_nut_to_veg'),
    ('product_description', 'walnut', 'proposed_esha_desc', 'squash', 'reject_nut_to_veg'),
    ('product_description', 'pecan', 'proposed_esha_desc', 'squash', 'reject_nut_to_veg'),
    ('product_description', 'pistachio', 'proposed_esha_desc', 'squash', 'reject_nut_to_veg'),
    ('product_description', 'seed', 'proposed_esha_desc', 'squash', 'reject_seed_to_veg'),
    # Dressing outliers
    ('product_description', 'balsamic glaze', 'proposed_esha_desc', 'barbecue', 'reject_glaze_misroute'),
    ('product_description', 'poppyseed', 'proposed_esha_desc', 'oil', 'reject_poppy_to_oil'),
    # Cheese curls sink (critical)
    ('proposed_esha_code', '1280', None, None, 'reject_cheese_curls'),
    # Yogurt -> milk
    ('product_description', 'yogurt', 'proposed_esha_desc', 'milk, whole', 'reject_yogurt_to_milk'),
    ('product_description', 'yogurt', 'proposed_esha_desc', 'milk, skim', 'reject_yogurt_to_milk'),
    ('product_description', 'yogurt', 'proposed_esha_desc', 'milk, low fat', 'reject_yogurt_to_milk'),
    ('product_description', 'yogurt', 'proposed_esha_desc', 'milk, nonfat', 'reject_yogurt_to_milk'),
    # Yogurt plain -> flavored
    ('product_description', 'plain', 'proposed_esha_desc', 'honey', 'reject_plain_to_flavored'),
    ('product_description', 'plain', 'proposed_esha_desc', 'raspberry', 'reject_plain_to_flavored'),
    ('product_description', 'plain', 'proposed_esha_desc', 'peach', 'reject_plain_to_flavored'),
    ('product_description', 'plain', 'proposed_esha_desc', 'strawberry', 'reject_plain_to_flavored'),
    ('product_description', 'plain', 'proposed_esha_desc', 'blueberry', 'reject_plain_to_flavored'),
    # Candy -> raw meat / raw nuts / bread / juice
    ('branded_food_category', 'candy', 'proposed_esha_desc', 'bear, raw', 'reject_candy_to_raw_meat'),
    ('branded_food_category', 'candy', 'proposed_esha_desc', 'heart, raw', 'reject_candy_to_raw_meat'),
    ('branded_food_category', 'candy', 'proposed_esha_desc', 'beef', 'reject_candy_to_raw_meat'),
    ('branded_food_category', 'candy', 'proposed_esha_desc', 'peanuts, raw', 'reject_candy_to_raw_nuts'),
    ('branded_food_category', 'candy', 'proposed_esha_desc', 'cashews, raw', 'reject_candy_to_raw_nuts'),
    ('branded_food_category', 'candy', 'proposed_esha_desc', 'bread', 'reject_candy_to_bread'),
    ('branded_food_category', 'candy', 'proposed_esha_desc', 'juice', 'reject_candy_to_juice'),
    # Milk -> plant milk
    ('product_description', 'milk', 'proposed_esha_desc', 'soy milk', 'reject_dairy_to_soy'),
    ('product_description', 'milk', 'proposed_esha_desc', 'oat milk', 'reject_dairy_to_oat'),
    ('product_description', 'milk', 'proposed_esha_desc', 'almond milk', 'reject_dairy_to_almond'),
    # Ice cream -> branded
    ('product_description', 'ice cream', 'proposed_esha_desc', 'snickers', 'reject_icecream_to_branded'),
    ('product_description', 'ice cream', 'proposed_esha_desc', 'reeses', 'reject_icecream_to_branded'),
    ('product_description', 'sherbet', 'proposed_esha_desc', 'orange', 'reject_sherbet_flatten'),
    # Oatmeal -> snack bar
    ('product_description', 'oatmeal', 'proposed_esha_desc', 'bar, snack', 'reject_oatmeal_to_bar'),
    # Sherbet/sorbet -> frozen produce
    ('product_description', 'sherbet', 'proposed_esha_desc', 'raspberries, frozen', 'reject_sherbet_to_produce'),
    ('product_description', 'sorbet', 'proposed_esha_desc', 'raspberries, frozen', 'reject_sorbet_to_produce'),
]

def is_noop(row):
    return row.get('current_esha_code','').strip() == row.get('proposed_esha_code','').strip()

def is_rejected(row):
    if is_noop(row):
        return 'reject_noop'
    pd = (row.get('product_description') or '').lower()
    cat = (row.get('branded_food_category') or '').lower()
    for f1, p1, f2, p2, reason in REJECT_PATTERNS:
        v1 = (row.get(f1) or '').lower()
        if p1 and p1 not in v1:
            continue
        if f2:
            v2 = (row.get(f2) or '').lower()
            if p2 and p2 not in v2:
                continue
        if reason == 'reject_rootbeer_to_beer' and 'root beer' in v1:
            return reason
        if reason == 'reject_gingerbeer_to_beer' and 'ginger beer' in v1:
            return reason
        if reason in ('reject_rootbeer_to_beer', 'reject_gingerbeer_to_beer'):
            continue
        if reason == 'reject_cheese_curls' and 'cheese' in pd:
            return reason
        if reason == 'reject_cheese_curls':
            continue
        if reason == 'reject_yogurt_to_milk' and 'yogurt' in pd:
            return reason
        if reason == 'reject_yogurt_to_milk':
            continue
        if reason.startswith('reject_plain_to_flavored') and 'plain' in pd and not any(f in pd for f in ['honey','raspberry','peach','strawberry','blueberry']):
            return reason
        if reason.startswith('reject_plain_to_flavored'):
            continue
        if reason.startswith('reject_candy_') and 'candy' in cat:
            return reason
        if reason.startswith('reject_candy_'):
            continue
        if reason.startswith('reject_dairy_to_') and 'milk' in pd and not any(p in pd for p in ['soy','oat','almond','coconut']):
            return reason
        if reason.startswith('reject_dairy_to_'):
            continue
        if reason.startswith('reject_icecream_to_branded') and 'ice cream' in pd:
            return reason
        if reason.startswith('reject_icecream_to_branded'):
            continue
        if reason == 'reject_sherbet_flatten' and 'sherbet' in pd and 'orange' not in pd:
            return reason
        if reason == 'reject_sherbet_flatten':
            continue
        if reason == 'reject_oatmeal_to_bar' and 'oatmeal' in pd:
            return reason
        if reason == 'reject_oatmeal_to_bar':
            continue
        if reason.startswith('reject_sherbet_to_produce') and 'sherbet' in pd:
            return reason
        if reason.startswith('reject_sherbet_to_produce'):
            continue
        if reason.startswith('reject_sorbet_to_produce') and 'sorbet' in pd:
            return reason
        if reason.startswith('reject_sorbet_to_produce'):
            continue
        return reason
    return None

def filter_file(path):
    safe = []
    rejected = []
    with path.open(encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            rej = is_rejected(row)
            if rej:
                row['reject_reason'] = rej
                rejected.append(row)
            else:
                safe.append(row)
    base = path.stem.replace('_safe','').replace('_rejected','')
    orig = path.with_name(f'{base}.csv')
    safe_path = orig.with_name(f'{base}_safe.csv')
    rej_path = orig.with_name(f'{base}_rejected.csv')
    if safe:
        with safe_path.open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(safe[0].keys()))
            w.writeheader(); w.writerows(safe)
    if rejected:
        with rej_path.open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rejected[0].keys()))
            w.writeheader(); w.writerows(rejected)
    print(f'{orig.name}: {len(safe)} safe, {len(rejected)} rejected')
    return safe, rejected

if __name__ == '__main__':
    for p in sys.argv[1:]:
        filter_file(Path(p))
