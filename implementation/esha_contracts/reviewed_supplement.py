from __future__ import annotations

from .contract_base import ContractFn, ContractSpec, ProductFacts, MatchDecision, match_spec

# Categories that commonly carry supplement products.
SUPPLEMENT_CATEGORIES = (
    "vitamin",
    "supplement",
    "children nutritional",
    "meal replacement",
    "specialty formula",
    "digestive",
    "fiber",
    "energy",
    "protein",
    "muscle",
    "recovery",
    "green supplement",
    "herbal supplement",
    "health care",
    "powdered drink",
    "gelatin",
    "sugar",
    "sport drink",
    "other drink",
    "baking additive",
    "cookie",
    "biscuit",
)


def make_supplement_contract(
    esha_code: str,
    esha_description: str,
    required_terms: tuple[str, ...],
    exclude_terms: tuple[str, ...] = (),
    allowed_categories: tuple[str, ...] = SUPPLEMENT_CATEGORIES,
) -> ContractFn:
    def contract(product: ProductFacts) -> MatchDecision:
        spec = ContractSpec(
            esha_code=esha_code,
            esha_description=esha_description,
            allowed_categories=allowed_categories,
            search_terms=required_terms,
            required_terms=required_terms,
            exclude_terms=exclude_terms,
        )
        return match_spec(product, spec)
    return contract


# ───────────────────────────────────────────────────────────────
# 1. Multi Vitamin & Mineral  (19 codes)
# ───────────────────────────────────────────────────────────────

def make_multivitamin_contract(
    esha_code: str,
    esha_description: str,
    extra_required: tuple[str, ...] = (),
    extra_exclude: tuple[str, ...] = (),
) -> ContractFn:
    required = ("vitamin",) + extra_required
    exclude = (
        "protein",
        "fiber",
        "amino",
        "spirulina",
        "algae",
        "green",
        "cleansing",
        "energy",
        "anti",
        "stress",
        "antioxidant",
        "immune",
        "saccharin",
        "sweetener",
        "thickener",
        "gelatine",
        "glucosamine",
        "diabetic",
        "infant",
        "dha",
        "expecta",
    ) + extra_exclude
    return make_supplement_contract(esha_code, esha_description, required, exclude)


MULTIVITAMIN_CONTRACTS = {
    "1915": ("Multi Vitamin & Mineral, Opti-Vit 75, with iron, tablet", ("opti", "vit")),
    "1916": ("Multi Vitamin & Mineral, Opti-Women, capsule", ("opti", "women")),
    "1917": ("Multi Vitamin & Mineral, Nutri-Vites, with iron, capsule", ("nutri", "vites")),
    "8971": ("Multi Vitamin & Mineral, Opti-Vites, with iron, capsule", ("opti", "vites")),
    "8972": ("Multi Vitamin & Mineral, Opti-Men, tablet", ("opti", "men")),
    "8973": ("Multi Vitamin & Mineral, Daily One Complete, with iron, capsule", ("daily", "one")),
    "52183": ("Multi Vitamin & Mineral, Super Twin, tablet", ("super", "twin")),
    "52184": ("Multi Vitamin & Mineral, Pre-Natal, capsules", ("pre", "natal")),
    "52186": ("Multi Vitamin & Mineral, Mega 6 Caps, capsule", ("mega", "6")),
    "52187": ("Multi Vitamin & Mineral, Mega 3 Caps, capsule", ("mega", "3")),
    "52188": ("Multi Vitamin & Mineral, Dualtabs, tablets", ("dualtabs",)),
    "52189": ("Multi Vitamin & Mineral, daily, with o iron, capsule", ("daily",)),
    "52190": ("Multi Vitamin & Mineral, daily, with iron, capsule", ("daily", "iron")),
    "52195": ("Multi Vitamin, essential formula, tablet", ("essential",)),
    "52196": ("Multi Vitamin & Mineral, maximum formula, tablet", ("maximum",)),
    "52197": ("Multi Vitamin & Mineral, 50 plus formula, tablet", ("50",)),
    "52198": ("Multi Vitamin & Mineral, active formula, tablet", ("active",)),
    "52199": ("Multi Vitamin & Mineral, men's formula, tablet", ("men",)),
    "52200": ("Multi Vitamin & Mineral, One A Day, women's formula, tablet", ("one", "women")),
}


# ───────────────────────────────────────────────────────────────
# 2. Fiber supplement  (3 codes)
# ───────────────────────────────────────────────────────────────

def make_fiber_contract(
    esha_code: str,
    esha_description: str,
    required: tuple[str, ...],
) -> ContractFn:
    exclude = (
        "bar",
        "chip",
        "snack",
        "pizza",
        "chocolate",
        "cookie",
        "cracker",
    )
    return make_supplement_contract(esha_code, esha_description, required, exclude)


FIBER_CONTRACTS = {
    "1977": ("Fiber, supplement, Opti-Fiber, powder", ("opti", "fiber")),
    "39133": ("Fiber, supplement, psyllium", ("psyllium",)),
    "62776": ("Fiber, supplement, Benefiber, powder, SD", ("benefiber",)),
}


# ───────────────────────────────────────────────────────────────
# 3. Protein supplement  (2 codes)
# ───────────────────────────────────────────────────────────────

PROTEIN_CONTRACTS = {
    "4060": ("Protein, supplement, Beneprotein, instant, serving, SD", ("beneprotein",)),
    "63041": ("Supplement, Primo Max, high protein, all flavors, powder, scoop", ("primo", "max")),
}


# ───────────────────────────────────────────────────────────────
# 4. Sweetener tablets (saccharin)  (5 codes)
# ───────────────────────────────────────────────────────────────

SACCHARIN_CATEGORIES = (
    "sugar",
    "granulated",
    "brown",
    "powdered",
    "sweetener",
    "supplement",
    "vitamin",
    "health care",
)

SACCHARIN_CONTRACTS = {
    "63449": ("Sweetener, saccharin, NectaSweet, 1 grain, tablet", ("saccharin", "nectasweet")),
    "63450": ("Sweetener, saccharin, NectaSweet, 1/2 grain, tablet", ("saccharin", "nectasweet")),
    "63451": ("Sweetener, saccharin, NectaSweet, 1/4 grain, tablet", ("saccharin", "nectasweet")),
    "63452": ("Sweetener, saccharin, Flavour Creations, tablet", ("saccharin", "flavour")),
    "63453": ("Sweetener, saccharin, InstaSweet, tablet", ("saccharin", "instasweet")),
}


# ───────────────────────────────────────────────────────────────
# 5. Amino acid supplements  (4 codes)
# ───────────────────────────────────────────────────────────────

AMINO_ACID_CONTRACTS = {
    "63738": ("Supplement, amino acid, capsule, SD", ("amino",)),
    "63739": ("Supplement, amino acid, tablet, SD", ("amino",)),
    "63753": ("Supplement, essential amino acids, powder, SD", ("essential", "amino")),
    "63758": ("Supplement, complete amino acids, powder, SD", ("complete", "amino")),
}


# ───────────────────────────────────────────────────────────────
# 6. Spirulina / Algae  (2 codes)
# ───────────────────────────────────────────────────────────────

SPIRULINA_CONTRACTS = {
    "29568": ("Algae, Arthrospira platensis, Spirulina Natural, capsule", ("spirulina", "algae")),
    "29570": ("Supplement, Spirulina Gold Plus", ("spirulina",)),
}


# ───────────────────────────────────────────────────────────────
# 7. Green Blends / Cleansing  (2 codes)
# ───────────────────────────────────────────────────────────────

GREEN_BLEND_CONTRACTS = {
    "29572": ("Supplement, Green Blends Cleansing", ("green", "blend")),
    "29573": ("Supplement, Green Blends Cleansing, powder", ("green", "blend")),
}


# ───────────────────────────────────────────────────────────────
# 8. Thickener  (2 codes)
# ───────────────────────────────────────────────────────────────

THICKENER_CONTRACTS = {
    "30054": ("Thickener, supplement, Thick It 2, concentrate, instant", ("thick", "2")),
    "30055": ("Thickener, supplement, Thick It, regular, instant", ("thick",)),
}


# ───────────────────────────────────────────────────────────────
# 9. Singleton / small-group contracts
# ───────────────────────────────────────────────────────────────

SINGLETON_CONTRACTS: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    # (description, required_terms, exclude_terms)
    "1894": ("Yeast, brewer's, 10 grain tablet", ("brewer", "yeast"), ()),
    "2665": ("Rennin, tablet, unsweetened, 0.35oz package", ("rennin",), ()),
    "8970": ("Supplement, Complete Diet Boost, capsule", ("complete", "diet", "boost"), ()),
    "8974": ("Vitamin C, with citrus bioflavonoids & rose hips, capsule", ("vitamin", "c"), ()),
    "14754": ("Supplement, Microlipid, liquid, ready to use, SD", ("microlipid",), ()),
    "14755": (
        "Supplement, vitamin & mineral, chewable, tablet, SD",
        ("vitamin", "mineral", "chewable"),
        (),
    ),
    "14767": ("Supplement, weight gain, Benecalorie, ready to use, serving, SD", ("benecalorie",), ()),
    "14774": ("Supplement, Glutasolve, powder, packet, SD", ("glutasolve",), ()),
    "24706": ("Supplement, OS Living Balance, powder", ("living", "balance"), ()),
    "30462": ("Supplement, Back To The Garden, powder, packet, SD", ("back", "garden"), ()),
    "32099": (
        "Supplement, gelatine, with glucosamine chondroitin & MSM caplet",
        ("gelatine", "glucosamine"),
        (),
    ),
    "38828": ("Supplement, diabetic, liquid", ("diabetic",), ()),
    "39807": ("Supplement, DHA, Expecta LIPIL, soft gel", ("dha", "expecta"), ()),
    "49908": ("Supplement, energy, Nrgize", ("energy", "nrgize"), ()),
    "49909": ("Supplement, anti-stress, Nrgize", ("anti", "stress", "nrgize"), ()),
    "49910": ("Supplement, antioxidant/immune, Nrgize", ("antioxidant", "nrgize"), ()),
    "52181": ("Multi Mineral, Multi Mineral Caps, capsules", ("multi", "mineral"), ()),
    "62065": ("Infant Supplement, Enfalyte, liquid", ("infant", "enfalyte"), ()),
    "63037": ("Supplement, Max Complete, capsules", ("max", "complete"), ()),
    "63757": (
        "Supplement, vitamin & mineral, Phlexy-Vits, dry packet, SD",
        ("phlexy",),
        (),
    ),
}


# ───────────────────────────────────────────────────────────────
# Build CONTRACTS dict
# ───────────────────────────────────────────────────────────────

CONTRACTS: dict[str, ContractFn] = {}

for _code, (_desc, _extra) in MULTIVITAMIN_CONTRACTS.items():
    CONTRACTS[_code] = make_multivitamin_contract(_code, _desc, _extra)

for _code, (_desc, _req) in FIBER_CONTRACTS.items():
    CONTRACTS[_code] = make_fiber_contract(_code, _desc, _req)

for _code, (_desc, _req) in PROTEIN_CONTRACTS.items():
    CONTRACTS[_code] = make_supplement_contract(_code, _desc, _req)

for _code, (_desc, _req) in SACCHARIN_CONTRACTS.items():
    CONTRACTS[_code] = make_supplement_contract(
        _code, _desc, _req, allowed_categories=SACCHARIN_CATEGORIES
    )

for _code, (_desc, _req) in AMINO_ACID_CONTRACTS.items():
    CONTRACTS[_code] = make_supplement_contract(_code, _desc, _req)

for _code, (_desc, _req) in SPIRULINA_CONTRACTS.items():
    CONTRACTS[_code] = make_supplement_contract(_code, _desc, _req)

for _code, (_desc, _req) in GREEN_BLEND_CONTRACTS.items():
    CONTRACTS[_code] = make_supplement_contract(_code, _desc, _req)

for _code, (_desc, _req) in THICKENER_CONTRACTS.items():
    CONTRACTS[_code] = make_supplement_contract(_code, _desc, _req)

for _code, (_desc, _req, _exc) in SINGLETON_CONTRACTS.items():
    CONTRACTS[_code] = make_supplement_contract(_code, _desc, _req, _exc)
