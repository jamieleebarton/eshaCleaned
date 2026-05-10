#!/usr/bin/env python3
"""Move SKUs that are sitting at the wrong canonical_path to where they
actually belong. After moving, also remove them from excluded_upcs since
they no longer cause harm at their proper home.

This is the right shape of fix: products stay discoverable, just at the
correct leaf so they only get picked for recipes that actually want
that kind of product.
"""
from __future__ import annotations
import csv, shutil, sqlite3, sys
from pathlib import Path

ROOT = Path("/Users/jamiebarton/Desktop/esha_audit_bundle")
DB   = ROOT / "recipe_pricing" / "data" / "priced_products_v2.db"
BAK  = DB.with_name("priced_products_v2.before_identity_moves.db")
RUN_BAK = DB.with_name("priced_products_v2.before_form_facet_moves.db")
EXCLUDED = ROOT / "recipe_pricing" / "excluded_upcs.csv"

HAM_LUNCHMEAT_PATH = "Meal > Sandwiches > Lunch Meat"
HAM_LUNCHMEAT_HTC = "H0000013"

HAM_LUNCHMEAT_TERMS = (
    "lunch meat",
    "lunchmeat",
    "deli meat",
    "deli ham",
    "deli sliced",
    "deli style",
    "deli fresh",
    "thin sliced",
    "ultra thin",
    "sandwich meat",
    "sandwich sliced",
    "fresh sliced deli",
    "grab & go",
)

HAM_LUNCHMEAT_EXCLUDE_TERMS = (
    "ham steak",
    "ham shank",
    "shank portion",
    "ham hock",
    "spiral",
    "quarter ham",
    "dinner ham",
    "ham roast",
    "bone in",
    "bone-in",
    "diced ham",
    "canned ham",
)

# Move tuple shapes:
#   (upc, new_canonical_path, new_htc_form_code, why)
#   (upc, new_canonical_path, new_htc_code, new_htc_form_code, why)
# The 5-field shape keeps identity and form HTC distinct for fixes where the
# existing pool already shows the correct identity bucket.
MOVES = [
    ("638392102165", "Pantry > Spices & Seasonings > BBQ Rub", "",
     "Bearded Butchers Maple Bacon DIY Kit — bacon-curing kit, not cinnamon"),
    ("052100048857", "Pantry > Spices & Seasonings > Crushed Red Pepper", "",
     "McCormick Crushed Red Pepper with Oregano — primary id is crushed red pepper"),
    ("052100053073", "Pantry > Spices & Seasonings > Spice Blend", "",
     "McCormick Sesame and Ginger Crunch with Garlic — multi-ingredient blend"),
    ("052100055954", "Pantry > Spices & Seasonings > Seasoning", "",
     "Grill Mates Dill Pickle Seasoning — flavored seasoning blend, not pure dill"),
    ("520712128", "Pantry > Canned Vegetables > Tomatoes", "",
     "Great Value Italian-Style Diced Tomatoes — canned tomatoes, not oregano"),
    ("466942277649", "Pantry > Sweeteners > Corn Syrup", "C01D000M",
     "Karo corn syrup with vanilla extract belongs to corn syrup, not vanilla extract"),
    ("15239750016", "Pantry > Sweeteners > Corn Syrup", "C01D000M",
     "Karo corn syrup with vanilla extract belongs to corn syrup, not vanilla extract"),
    ("040811070502", "Pantry > Baking Extracts > Imitation Vanilla", "E500000*",
     "Molina vanilla blend is imitation/blend vanilla, not pure vanilla extract"),
    ("098100101215", "Beverage > Coffee > Espresso", "D30Q000X",
     "Starbucks caramel macchiato is a coffee drink, not caramel candy"),
    ("072554112058", "Frozen > Ice Cream", "1510600=",
     "Drumstick sundae cones are frozen ice cream, not caramel candy"),
    ("040000641674", "Snack > Chocolate Candy > Candy Bar", "J43J600G",
     "Snickers Xtreme is a chocolate candy bar, not bagged caramels"),
    ("810815022261", "Snack > Bars > Energy Bars", "J1HC000K",
     "Honey Stinger waffle is an energy snack bar/waffle, not caramel candy"),
    ("0001111074290", "Pantry > Sweeteners > Caramel Topping", "C01E0006",
     "Kroger caramel dessert topping is topping, not bagged caramel candy"),
    ("051500000212", "Pantry > Sweeteners > Caramel Topping", "C01E0006",
     "Smucker's caramel topping is topping, not bagged caramel candy"),
    ("072980002435", "Pantry > Sweeteners > Caramel Topping", "C01E0006",
     "Mrs. Richardson's caramel topping is topping, not bagged caramel candy"),
    ("028000518868", "Pantry > Sauces & Salsas > Caramel Sauce", "F62J600V",
     "Dulce de leche liquid caramel sauce belongs to caramel sauce"),
    ("0003120000231", "Snack > Dried Fruit > Dried Cranberries", "735A4003",
     "Ocean Spray Cherry Craisins are flavored dried cranberries, not plain dried cherries"),
    ("0007834278154", "Non-Food > Grilling > Smoking Wood", "N0000000",
     "Duraflame Western cooking chunks are smoking wood, not seasoning"),
    ("0007834278155", "Non-Food > Grilling > Smoking Wood", "N0000000",
     "Western Hickory BBQ Cooking Chunks are smoking wood, not barbecue sauce"),
    ("0007834228184", "Non-Food > Grilling > Smoking Wood", "N0000000",
     "Western Apple BBQ Cooking Chunks are smoking wood, not ham"),
    ("077400127439", "Meal > Sandwiches > Lunch Meat", "H0000002",
     "Carl Buddig corned beef lunchmeat is deli/lunch meat, not generic corned beef"),
    ("0007740012743", "Meal > Sandwiches > Lunch Meat", "H0000002",
     "Buddig Corned Beef Lunch Meat is deli/lunch meat, not generic corned beef"),
    ("0020572190000", "Meal > Sandwiches > Lunch Meat", "H0000002",
     "Private Selection deli corned beef sliced belongs to lunch meat"),
    ("0022572100000", "Meal > Sandwiches > Lunch Meat", "H0000002",
     "Private Selection uncured deli corned beef sliced belongs to lunch meat"),
    ("0001111062874", "Meal > Sandwiches > Lunch Meat", "H0000002",
     "Private Selection Angus deli corned beef sliced belongs to lunch meat"),
    ("0007740012123", "Meal > Sandwiches > Lunch Meat", "H0000013",
     "Buddig Black Forest Ham Lunch Meat is deli/lunch meat, not generic ham"),
    ("0007740012853", "Meal > Sandwiches > Lunch Meat", "H0000013",
     "Buddig Honey Ham Lunch Meat is deli/lunch meat, not generic ham"),
    ("0004660003427", "Meal > Lunch Kits", "H0000002",
     "Armour LunchMaker Ham Smalls is a lunch/snack kit item, not generic ham"),
    ("078742194233", "Meal > Sandwiches > Lunch Meat", "H0000013",
     "Great Value Black Forest Ham is in the retailer ham lunch meat shelf"),
    ("078742042190", "Meal > Sandwiches > Lunch Meat", "H0000013",
     "Great Value Honey Ham Lunchmeat is deli/lunch meat, not generic ham"),
    ("194346144129", "Meal > Sandwiches > Lunch Meat", "H0000013",
     "Great Value Black Forest Ham Lunchmeat is deli/lunch meat, not generic ham"),
    ("0005190001613", "Meal > Sandwiches > Lunch Meat", "H0000013",
     "Land O' Frost Black Forest Ham Lunch Meat is deli/lunch meat"),
    ("0007080023482", "Meal > Sandwiches > Lunch Meat", "H0000013",
     "Smithfield Black Forest Ham 16 oz is sliced packaged deli ham"),
    ("0007080023483", "Meal > Sandwiches > Lunch Meat", "H0000013",
     "Smithfield Honey Ham 16 oz is sliced packaged deli ham"),

    # Protein tier audit: move products into the food they actually are. These
    # are not quarantine cases; they were contaminating beef/pork concept pools.
    ("0002718256550", "Meat & Seafood > Ground Meat > Beef & Pork Blend",
     "2000000P", "2000002R",
     "Tyson Ground Beef & Pork is mixed ground meat, not plain ground beef"),
    ("076788300267", "Meat & Seafood > Sausage > Italian Sausage",
     "241M0003", "241M0025",
     "Falls Brand Mild Italian Sausage belongs to Italian sausage, not plain ground pork"),
    ("078742064826", "Meat & Seafood > Sausage > Italian Sausage",
     "241M0003", "241M0025",
     "Marketside Mild Ground Italian Sausage belongs to Italian sausage, not plain ground pork"),
    ("078742357584", "Meat & Seafood > Sausage > Italian Sausage",
     "241M0003", "241M0025",
     "Marketside Sweet Ground Italian Sausage belongs to Italian sausage, not plain ground pork"),
    ("078742357591", "Meat & Seafood > Sausage > Italian Sausage",
     "241M0003", "241M0025",
     "Marketside Hot Ground Italian Sausage belongs to Italian sausage, not plain ground pork"),
    ("0001111097274", "Meat & Seafood > Sausage > Pork Sausage",
     "2422000X", "2422000X",
     "Kroger Country Pork Ground Sausage is pork sausage, not plain ground pork"),
    ("194346096480", "Meal > Meal Starters > Stuffed Pork",
     "H0000002", "H0000002",
     "Marketside bacon-cheddar stuffed pork chops are prepared stuffed pork, not plain pork chops"),
    ("052100060347", "Pantry > Spices & Seasonings > Seasoning",
     "E602000R", "E602000R",
     "McCormick Pork Chops & Apples is a seasoning packet, not pork chops"),
    ("0025338300000", "Meat & Seafood > Pork > Pork Shoulder",
     "2106000*", "2106000*",
     "Kroger Bone-In Pork Shoulder Steaks belong to pork shoulder, not pork chops"),
    ("052100058566", "Pantry > Spices & Seasonings > Seasoning",
     "E602000R", "E602000R",
     "McCormick Brown Sugar Glazed Ham is a seasoning/glaze packet, not ham"),
    ("037600816205", "Pantry > Bacon Bits",
     "J0CP000V", "J0CP100F",
     "Hormel chopped bacon topping belongs to bacon bits, not raw bacon"),
    ("037600273299", "Pantry > Bacon Bits",
     "J0CP000V", "J0CP100F",
     "Hormel crumbled bacon topping belongs to bacon bits, not raw bacon"),
    ("052100058405", "Pantry > Sweeteners > Flavored Sugar",
     "C005000S", "C005080P",
     "McCormick Apple Cider Finishing Sugar is flavored sugar, not apple cider"),
    ("796853100249", "Pantry > Canned Meat > Canned Beef",
     "J000000D", "J000200T",
     "Keystone canned ground beef is shelf-stable canned beef, not raw ground beef"),
]


def _unpack_move(raw):
    if len(raw) == 4:
        upc, new_cp, new_htc_form, why = raw
        new_htc_code = new_htc_form
    elif len(raw) == 5:
        upc, new_cp, new_htc_code, new_htc_form, why = raw
    else:
        raise ValueError(f"bad move tuple length: {len(raw)}")
    return upc, new_cp, new_htc_code, new_htc_form, why


def _norm(text: str | None) -> str:
    return " ".join((text or "").lower().replace("&", " ").split())


def _is_ham_lunchmeat(row: sqlite3.Row) -> bool:
    text = _norm(" ".join([
        row["name"] or "",
        row["category_path"] or "",
        row["category_path_walmart"] or "",
        row["retail_leaf_path"] or "",
    ]))
    if any(term in text for term in HAM_LUNCHMEAT_EXCLUDE_TERMS):
        return False
    return any(term in text for term in HAM_LUNCHMEAT_TERMS)


def auto_ham_lunchmeat_moves(con: sqlite3.Connection) -> list[tuple[str, str, str, str]]:
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT upc, name, category_path, category_path_walmart, retail_leaf_path
        FROM priced_products
        WHERE available = 1
          AND consensus_canonical = 'Meat & Seafood > Ham'
          AND upc IS NOT NULL
        GROUP BY upc, name, category_path, category_path_walmart, retail_leaf_path
    """).fetchall()
    moves = []
    manual_upcs = {_unpack_move(raw)[0] for raw in MOVES}
    for row in rows:
        upc = row["upc"]
        if upc in manual_upcs:
            continue
        if _is_ham_lunchmeat(row):
            moves.append((
                upc,
                HAM_LUNCHMEAT_PATH,
                HAM_LUNCHMEAT_HTC,
                "auto: explicit deli/lunch/sandwich ham evidence, not generic ham",
            ))
    return moves


def main():
    if not BAK.exists():
        print(f"backing up DB → {BAK.name}", file=sys.stderr)
        shutil.copy(str(DB), str(BAK))
    if not RUN_BAK.exists():
        print(f"backing up current DB → {RUN_BAK.name}", file=sys.stderr)
        shutil.copy(str(DB), str(RUN_BAK))

    con = sqlite3.connect(str(DB))
    cur = con.cursor()

    moved_upcs = set()
    moves = MOVES + auto_ham_lunchmeat_moves(con)
    for raw in moves:
        upc, new_cp, new_htc_code, new_htc_form, why = _unpack_move(raw)
        non_food = 1 if new_cp.startswith("Non-Food") else 0
        cur.execute("""SELECT name, consensus_canonical, htc_form_code, COUNT(*)
            FROM priced_products WHERE upc = ? GROUP BY name, consensus_canonical, htc_form_code""",
            (upc,))
        before = cur.fetchall()
        if not before:
            print(f"  ⚠ upc={upc} not in DB", file=sys.stderr); continue
        for name, old_cp, old_htc, n in before:
            print(f"  upc={upc} ({n} rows) — was: {old_cp}", file=sys.stderr)
            print(f"                          → now: {new_cp}", file=sys.stderr)
            if new_htc_form:
                print(f"                          htc: {old_htc or '(blank)'} → {new_htc_form}", file=sys.stderr)
            print(f"      why: {why}", file=sys.stderr)
        # Re-enable AND move
        if new_htc_form:
            cur.execute("""UPDATE priced_products
                SET consensus_canonical = ?, htc_form_code = ?, htc_code = ?,
                    htc_group = ?, available = 1, non_food_path = ?
                WHERE upc = ?""", (
                    new_cp, new_htc_form, new_htc_code,
                    new_htc_code[:1], non_food, upc,
                ))
        else:
            cur.execute("""UPDATE priced_products
                SET consensus_canonical = ?, available = 1, non_food_path = ?
                WHERE upc = ?""", (new_cp, non_food, upc))
        moved_upcs.add(upc)
    con.commit()
    con.close()

    # Remove these UPCs from excluded_upcs.csv (they're not bad anymore)
    if EXCLUDED.exists():
        existing = list(csv.DictReader(EXCLUDED.open()))
        kept = [r for r in existing if r.get("upc") not in moved_upcs]
        if len(kept) < len(existing):
            with EXCLUDED.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=existing[0].keys())
                w.writeheader()
                for row in kept: w.writerow(row)
            print(f"\nremoved {len(existing) - len(kept)} entries from excluded_upcs.csv",
                  file=sys.stderr)

    print(f"\n✓ moved {len(moved_upcs)} SKUs to correct paths and re-enabled them",
          file=sys.stderr)
    print(f"rollback via: cp {RUN_BAK} {DB}", file=sys.stderr)


if __name__ == "__main__":
    main()
