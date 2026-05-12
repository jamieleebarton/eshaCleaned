"""Layered-trust resolver. Surface-first, existing registries as fallback.

Resolution order (every layer preserved — nothing is deleted from the repo):

  L0_surface  canonical_surface_normalized.csv (nutrition/shopping split)  canonical_surface_hit
  L0a         supplemental_concepts_seed.csv                               reviewed_proxy
  L0b         approved_normalization_rules.csv → concept cascade           concept_alias
  L1          canonical_items.csv via normalizer on raw `item`             canonical_hit
  L2          canonical_items.csv via normalizer on `display`              canonical_display_hit
  L3          canonical_items.csv via normalizer on `normalized_line`      canonical_line_hit
  L4          reviewed_nutrition_anchors.csv on computed concept_key       reviewed_proxy
  L5          reviewed_sr28_nutrition_fallbacks.csv                        sr28_fallback
  L6          reviewed_external_catalog_items.csv                          external_catalog
  L8          nutrition_unknown (honest terminal)                          nutrition_unknown

L0_surface is the primary. Every row carries both a nutrition canonical
(`canonical_normalized`) and a shopping canonical (`canonical_shopping_item`)
so the plural/singular drift between L0's concept_key bases and the
canonical_items/term_cpg maps is solved by design, not patched.

A load-time blocklist rejects rows that would regress the Tier-0 normalizer
regression pack (butter peas→butter, coffee beans→bean, milk chocolate→
chocolate milk). Extend RECIPE_REGRESSION_BLOCKLIST when a new compositional
bug is pinned in test_normalizer.py.

SR28 is the primary anchor per user rule; FNDDS is secondary. For each
resolved canonical, both codes are returned; callers choose SR28 first.
"""
from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from normalizer import Normalizer, NormalizerResult

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
CANONICAL_ITEMS = ROOT / 'canonical_items.csv'
CANONICAL_TO_ESHA = ROOT / 'canonical_to_esha.csv'
REVIEWED_ANCHORS = ROOT / 'reviewed_nutrition_anchors.csv'
SR28_FALLBACKS = ROOT / 'reviewed_sr28_nutrition_fallbacks.csv'
EXTERNAL_CATALOG = ROOT / 'reviewed_external_catalog_items.csv'
APPROVED_NORM_RULES = ROOT / 'approved_normalization_rules.csv'
SUPPLEMENTAL_CONCEPTS = ROOT / 'supplemental_concepts_seed.csv'
CANONICAL_SURFACE = REPO_ROOT / 'canonical_surface_normalized_with_product_proxies.csv'
CANONICAL_SURFACE_FALLBACK = REPO_ROOT / 'canonical_surface_normalized.csv'
AUDIT_DB = ROOT / 'output' / 'recipe_qa_nutrition_calculation_audit.db'
HESTIA_LOOKUP = Path('/Users/jamiebarton/Desktop/Hestia/api/data/ingredient_lookup.json')

# Compositional errors pinned in test_normalizer.py. Rows in
# canonical_surface_normalized.csv matching (surface, nutrition_canonical) here
# are rejected at load time so L0_surface cannot regress the Tier-0 pack.
RECIPE_REGRESSION_BLOCKLIST: set[tuple[str, str]] = {
    # Originally pinned via test_normalizer.py
    ('butter peas', 'butter'),
    ('butter peas', 'pea'),
    ('coffee beans', 'bean'),
    ('coffee beans', 'kidney bean'),
    ('milk chocolate', 'chocolate milk'),
    ('milk chocolate', 'milk'),
    ('bagel chips', 'bagel'),
    ('caesar salad dressing', 'salad'),
    ('sardines in olive oil', 'olive oil'),
    ('artichoke hearts in oil', 'oil'),
    ('canned light tuna in water', 'water'),
    ('oil, to brush the bread', 'bread'),
    ('instant coffee, original roast', 'beef pot roast'),
    # Discovered in 2026-04-19 audit — plant milks collapsing to nuts/flesh
    ('almond milk', 'almond'),
    ('unsweetened almond milk', 'almond'),
    ('unsweetened vanilla almond milk', 'almond'),
    ('vanilla almond milk', 'almond'),
    ('coconut milk', 'coconut'),
    ('light coconut milk', 'coconut'),
    ('unsweetened coconut milk', 'coconut'),
    ('cream of coconut', 'coconut'),
    ('oat milk', 'oat'),
    ('soy milk', 'soy'),
    ('rice milk', 'rice'),
    ('cashew milk', 'cashew'),
    # Extracts / flavorings — "extract" is not an SR28 anchor
    ('vanilla extract', 'extract'),
    ('almond extract', 'extract'),
    ('lemon extract', 'extract'),
    ('peppermint extract', 'extract'),
    # Baking leaveners — "soda" would route to soft drinks
    ('baking soda', 'soda'),
    # Zest / rind — tiny mass, not flesh
    ('lemon rind', 'rinds'),
    ('lemon rind', 'pork rind'),
    ('orange rind', 'rinds'),
    ('lime rind', 'rinds'),
}
APPROVED_RULE_SURFACE_BLOCKLIST = {
    'green bean casserole, leftover',
}


@dataclass
class Resolution:
    """One ingredient line's resolved identity.

    trust_state is one of:
      canonical_surface_hit, canonical_hit, canonical_display_hit,
      canonical_line_hit, reviewed_proxy, sr28_fallback, external_catalog,
      concept_alias, non_food, nutrition_unknown

    shopping_canonical is the distinct shopping-side canonical when the
    resolver hits L0_surface; it separates "1% milk" (shopping) from
    "low-fat milk" (nutrition). Empty string otherwise — callers fall
    back to canonical_name.
    """
    canonical_name: str | None
    sr28_fdc_id: str
    fndds_code: str
    description: str
    trust_state: str
    layer: str
    matched_candidate: str
    path: list[str] = field(default_factory=list)
    shopping_canonical: str = ''
    # True when the canonical_items row used for this resolution has
    # review_status=proxy_auto_batched — i.e. the SR28 code is a proxy that
    # no human has approved. Nutrition can use it (honestly labeled REVIEWED_
    # PROXY) but shopping MUST NOT — the proxy's SR28 code points at an
    # unrelated food that no cook would buy for this recipe line.
    proxy_unreviewed: bool = False
    # Esha code — granular food ID from esha_cleaned.csv. Calculator prefers
    # Esha Tier-A label medians over SR28 direct when set.
    esha_code: str = ''


def _load_canonical_lookup(path: Path) -> dict[str, dict]:
    """canonical_name -> row (sr28_fdc_id, fndds_code, description, etc.)."""
    out: dict[str, dict] = {}
    if not path.exists(): return out
    with path.open(newline='') as f:
        for row in csv.DictReader(f):
            cn = row['canonical_name'].strip().lower()
            if cn:
                out[cn] = row
    return out


def _load_reviewed_anchors(path: Path) -> dict[str, dict]:
    """concept_key -> anchor row. concept_key uses the 'base|variant|form|state' format."""
    out: dict[str, dict] = {}
    if not path.exists(): return out
    with path.open(newline='') as f:
        for row in csv.DictReader(f):
            if row.get('review_status', '').strip() not in ('approved', 'approved_proxy'):
                continue
            ck = row.get('concept_key', '').strip()
            if ck:
                out[ck] = row
    return out


def _load_sr28_fallbacks(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not path.exists(): return out
    with path.open(newline='') as f:
        for row in csv.DictReader(f):
            k = (row.get('concept_key') or row.get('shopping_label') or '').strip()
            if k:
                out[k] = row
    return out


def _load_external_catalog(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not path.exists(): return out
    with path.open(newline='') as f:
        for row in csv.DictReader(f):
            k = (row.get('concept_key') or row.get('shopping_label') or '').strip()
            if k:
                out[k] = row
    return out


def _load_supplemental_concepts(path: Path) -> dict[str, dict]:
    """43K hand-curated recipe-surface -> canonical + SR28/FNDDS anchor.
    Returns: alias_lower -> {canonical, anchor_system, anchor_code, anchor_description}.
    Only rows with review_status='approved'.
    """
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    with path.open(newline='') as f:
        for r in csv.DictReader(f):
            if (r.get('review_status') or '').strip() != 'approved':
                continue
            alias = (r.get('alias') or '').strip().lower()
            canonical = (r.get('canonical_concept') or '').strip().lower()
            code = (r.get('anchor_code') or '').strip()
            system = (r.get('anchor_system') or '').strip().upper()
            desc = (r.get('anchor_description') or '').strip()
            if alias and canonical and code and alias not in out:
                out[alias] = {
                    'canonical': canonical,
                    'anchor_system': system,
                    'anchor_code': code,
                    'description': desc,
                }
    return out


def _load_approved_normalization_rules(path: Path) -> dict[str, str]:
    """745K hand-curated rules mapping recipe surface -> concept_key.
    input_surface (lowercased) -> canonical_concept_key (e.g. 'orange juice|||fresh').
    Only rows with status='approved' and rule_type='alias'/'split'/'alternative'.
    """
    out: dict[str, str] = {}
    if not path.exists():
        return out
    with path.open(newline='') as f:
        for r in csv.DictReader(f):
            if (r.get('status') or '').strip() != 'approved':
                continue
            surface = (r.get('input_surface') or '').strip().lower()
            ck = (r.get('canonical_concept_key') or '').strip()
            if surface in APPROVED_RULE_SURFACE_BLOCKLIST:
                continue
            if surface and ck and surface not in out:
                out[surface] = ck
    return out


def _load_canonical_to_esha(path: Path) -> dict[str, str]:
    """canonical_name (lowercase) -> EshaCode. Built by build_canonical_to_esha.py."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    with path.open(newline='') as f:
        for r in csv.DictReader(f):
            cn = (r.get('canonical_name') or '').strip().lower()
            code = (r.get('esha_code') or '').strip()
            if cn and code:
                out[cn] = code
    return out


def _load_canonical_surface(path: Path) -> dict[str, dict]:
    """canonical_surface_normalized.csv — 18K surface -> (nutrition, shopping, type).

    Schema: canonical_surface, canonical_normalized, canonical_shopping_item,
    record_type, product_query, prep_attributes, form_attributes,
    state_attributes, size_attributes, style_attributes, packaging_attributes,
    quantity_context, brand_candidate, review_flags, decision_reason, notes.

    Returns: surface_lower -> {
      'nutrition':  canonical_normalized (lowercase),
      'shopping':   canonical_shopping_item,
      'record_type': 'ingredient' | 'non_ingredient' | 'component_split',
    }

    Rows in RECIPE_REGRESSION_BLOCKLIST are dropped. component_split rows are
    also dropped — they require splitter logic we don't yet run here; the
    resolver falls through to the normalizer when we skip them.
    """
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    with path.open(newline='') as f:
        for r in csv.DictReader(f):
            surface = (r.get('canonical_surface') or '').strip().lower()
            nutrition = (r.get('canonical_normalized') or '').strip().lower()
            shopping = (r.get('canonical_shopping_item') or '').strip().lower()
            rtype = (r.get('record_type') or '').strip().lower()
            if not surface or not nutrition:
                continue
            if rtype == 'component_split':
                continue
            if (surface, nutrition) in RECIPE_REGRESSION_BLOCKLIST:
                continue
            if surface in out:
                continue
            out[surface] = {
                'nutrition': nutrition,
                'shopping': shopping,
                'record_type': rtype or 'ingredient',
                'family_base': (r.get('family_base') or '').strip().lower(),
                # Row-level anchors — fallback when canonical_items lookup
                # on `nutrition` (and `family_base`) both miss. Source order
                # matches the file: sr28 > fndds > esha > product_proxy_sr28.
                'row_sr28': (r.get('sr28_code') or '').strip(),
                'row_fndds': (r.get('fndds_code') or '').strip(),
                'row_esha': (r.get('esha_code') or '').strip(),
                'row_prod_proxy_sr28': (r.get('product_proxy_sr28_anchor_code') or '').strip(),
                # Median nutrition derived from tagged retail products. When
                # set, these are label-median per-100g values — REVIEWED_LOCAL
                # _LABEL_ANCHOR trust level.
                'prod_proxy_kcal': (r.get('product_proxy_median_calories') or '').strip(),
                'prod_proxy_protein': (r.get('product_proxy_median_protein_g') or '').strip(),
                'prod_proxy_fat': (r.get('product_proxy_median_fat_g') or '').strip(),
                'prod_proxy_carbs': (r.get('product_proxy_median_carbs_g') or '').strip(),
            }
    return out


def _load_hestia_exact_lookup(path: Path) -> dict[str, str]:
    """Hestia ingredient_lookup.json is the hand-curated head set (~2.5k entries).
    It has no `method` field — all entries are treated as method=exact.
    The method=substring aliases live in ingredient_lookup_expanded.json and
    are deliberately excluded per the cross-verify guardrail.
    Returns: surface_lower -> canonical ingredient name.
    """
    out: dict[str, str] = {}
    if not path.exists():
        return out
    try:
        with path.open() as f:
            data = json.load(f)
    except Exception:
        return out
    if not isinstance(data, dict):
        return out
    for surface, entry in data.items():
        if not isinstance(entry, dict):
            continue
        # Honor a `method` field if present; otherwise treat as exact.
        method = entry.get('method', 'exact')
        if method != 'exact':
            continue
        ing = entry.get('ingredient') or surface
        out[surface.strip().lower()] = str(ing).strip().lower()
    return out


class LayeredResolver:
    """Resolves ingredient lines through the L1–L8 cascade."""

    def __init__(self) -> None:
        self.normalizer = Normalizer()
        self._canonical = _load_canonical_lookup(CANONICAL_ITEMS)
        self._canonical_to_esha = _load_canonical_to_esha(CANONICAL_TO_ESHA)
        self._anchors = _load_reviewed_anchors(REVIEWED_ANCHORS)
        self._sr28_fb = _load_sr28_fallbacks(SR28_FALLBACKS)
        self._ext_cat = _load_external_catalog(EXTERNAL_CATALOG)
        self._supplemental = _load_supplemental_concepts(SUPPLEMENTAL_CONCEPTS)
        self._approved_rules = _load_approved_normalization_rules(APPROVED_NORM_RULES)
        self._canonical_surface = _load_canonical_surface(CANONICAL_SURFACE)
        self._hestia_exact_lookup = _load_hestia_exact_lookup(HESTIA_LOOKUP)

    def _esha_for(self, canonical: str | None) -> str:
        if not canonical:
            return ''
        return self._canonical_to_esha.get(canonical.strip().lower(), '')

    # -- cross-verify signal helpers --------------------------------------

    def _cross_verify_signals(self, item: str) -> list[str]:
        """Log-only cross-verify against two independent opinions:
        (1) item_fallback_lookup from the prior calculator run, and
        (2) Hestia ingredient_lookup.json (method=exact only).
        Signals are appended to path; no branching on outcome in this pass.
        """
        out: list[str] = []
        surface = (item or '').strip().lower()
        if not surface:
            return out
        try:
            with sqlite3.connect(f"file:{AUDIT_DB}?mode=ro", uri=True) as c:
                row = c.execute(
                    "SELECT concept_key FROM item_fallback_lookup "
                    "WHERE cleaned_surface = ? LIMIT 1",
                    (surface,),
                ).fetchone()
                if row and row[0]:
                    out.append(f"cross_verify: item_fallback_lookup -> {row[0]!r}")
        except Exception:
            pass
        hestia_hit = self._hestia_exact_lookup.get(surface)
        if hestia_hit:
            out.append(f"cross_verify: hestia_method_exact -> {hestia_hit!r}")
        return out

    # -- canonical lookup helpers ------------------------------------------

    # Review statuses that mean the SR28/FNDDS code on this canonical_items row
    # is a proxy, not an exact match. Resolutions routed through these rows
    # MUST emit trust_state='reviewed_proxy' — CLAUDE.md rule 3 + trust-state
    # honesty (see memory: feedback_proxy_is_the_design).
    _PROXY_STATUSES: set[str] = {
        'proxy_auto_batched',
        'approved_proxy',
        'provisional_proxy',
        'provisional_proxy_from_parent',
        'provisional_desc_proxy',
    }

    def _state_from_row(self, row: dict, default: str) -> str:
        """Inspect review_status on a canonical_items row. Return the honest
        trust_state — default (canonical_hit or canonical_surface_hit) when the
        row's status indicates a reviewed exact match, or 'reviewed_proxy' when
        the row is a proxy (auto-batched or human-reviewed proxy alike)."""
        status = (row.get('review_status') or '').strip().lower()
        if status in self._PROXY_STATUSES:
            return 'reviewed_proxy'
        return default

    # Proxy statuses that indicate NO human has approved the proxy decision.
    # These may supply nutrition (honestly labeled REVIEWED_PROXY) but MUST
    # NOT drive shopping — the proxy's SR28 code is a best-guess and points
    # at an unrelated food. Contrast with 'approved_proxy' which is a
    # human-approved proxy and IS safe for shopping via its SR28.
    _AUTO_BATCHED_STATUSES: set[str] = {
        'proxy_auto_batched',
        'provisional_proxy',
        'provisional_proxy_from_parent',
        'provisional_desc_proxy',
        'provisional',
    }

    @classmethod
    def _is_auto_batched(cls, row: dict) -> bool:
        """True when the canonical_items row is a proxy that no human has
        approved — nutrition may use it but shopping MUST NOT."""
        return (row.get('review_status') or '').strip().lower() in cls._AUTO_BATCHED_STATUSES

    def _canonical_to_anchors(self, canonical: str, match_result: NormalizerResult,
                              layer: str) -> Resolution:
        row = self._canonical.get(canonical, {})
        sr28 = row.get('sr28_fdc_id', '').strip()
        fndds = row.get('fndds_code', '').strip()
        desc = row.get('sr28_description', '') or row.get('fndds_description', '')
        state = 'canonical_hit'
        # If the canonical row has neither SR28 nor FNDDS (tree-only seed), it's
        # still a canonical hit — just with no direct anchor. Callers fall through
        # to reviewed_nutrition_anchors via the concept_key route.
        if not sr28 and not fndds:
            state = 'canonical_name_only'
        else:
            state = self._state_from_row(row, state)
        return Resolution(canonical_name=canonical,
                          sr28_fdc_id=sr28, fndds_code=fndds, description=desc,
                          trust_state=state, layer=layer,
                          matched_candidate=match_result.matched_candidate,
                          path=list(match_result.path),
                          proxy_unreviewed=self._is_auto_batched(row),
                          esha_code=self._esha_for(canonical))

    # -- concept_key builder (legacy cascade compatibility) ----------------

    @staticmethod
    def _concept_key_from_canonical(canonical: str) -> str:
        """Map canonical name to the legacy base|variant|form|state concept_key.
        Default: all slots empty except base = canonical."""
        return f"{canonical}|||"

    # -- resolve ------------------------------------------------------------

    def resolve(self, item: str = '', display: str = '',
                normalized_line: str = '') -> Resolution:
        path: list[str] = []

        # Cross-verify signals (log-only — do not branch resolver flow).
        path.extend(self._cross_verify_signals(item))

        # L0_surface: canonical_surface_normalized.csv (18K surface -> nutrition + shopping).
        # Highest-trust primary. Splits nutrition canonical from shopping canonical so
        # "1% milk" shops as "1% milk" but gets nutrition from "low-fat milk". Bad
        # compositional pairs are blocklisted at load time, not patched here.
        for field_name, text in (('item', item), ('display', display),
                                  ('normalized_line', normalized_line)):
            if not text: continue
            hit = self._canonical_surface.get(text.strip().lower())
            if not hit: continue
            if hit['record_type'] == 'non_ingredient':
                return Resolution(
                    canonical_name='', sr28_fdc_id='', fndds_code='',
                    description='non_ingredient',
                    trust_state='non_food', layer=f'L0_surface/{field_name}',
                    matched_candidate=text,
                    path=path + [f"L0_surface: {text!r} -> non_ingredient"],
                    shopping_canonical='',
                )
            nutrition = hit['nutrition']
            shopping = hit['shopping']
            row = self._canonical.get(nutrition, {})
            sr28 = row.get('sr28_fdc_id', '').strip()
            fndds = row.get('fndds_code', '').strip()
            desc = row.get('sr28_description', '') or row.get('fndds_description', '') or nutrition
            # Singular fold: if plural nutrition key doesn't anchor but its
            # singular does, prefer the anchored singular (tortillas→tortilla,
            # eggs→egg). Only strips trailing s/es — no aggressive stemming.
            if not sr28 and not fndds and nutrition.endswith('s'):
                sing = nutrition[:-2] if nutrition.endswith('es') else nutrition[:-1]
                sing_row = self._canonical.get(sing, {})
                if sing_row.get('sr28_fdc_id', '').strip() or sing_row.get('fndds_code', '').strip():
                    nutrition = sing
                    row = sing_row
                    sr28 = row.get('sr28_fdc_id', '').strip()
                    fndds = row.get('fndds_code', '').strip()
                    desc = row.get('sr28_description', '') or row.get('fndds_description', '') or sing
            # family_base fallback: when the surface's `canonical_normalized` is
            # a specific form (e.g. "white baking chocolate") that has no row in
            # canonical_items, use the surface's `family_base` (e.g. "white
            # chocolate") if that IS anchored. Honest: carries
            # family_base canonical and its codes, not a made-up match.
            borrowed_from_family = False
            if not sr28 and not fndds:
                fb = hit.get('family_base') or ''
                fb_row = self._canonical.get(fb, {}) if fb else {}
                fb_sr28 = fb_row.get('sr28_fdc_id', '').strip()
                fb_fndds = fb_row.get('fndds_code', '').strip()
                if fb_sr28 or fb_fndds:
                    # Preserve surface's stated nutrition name (honors the
                    # reviewed canonical_normalized — e.g. surface row says
                    # tortilla, family_base says tortillas; we keep tortilla).
                    row = fb_row
                    sr28 = fb_sr28
                    fndds = fb_fndds
                    desc = fb_row.get('sr28_description', '') or fb_row.get('fndds_description', '') or nutrition
                    borrowed_from_family = fb != nutrition
            # Honesty gate: proxy_auto_batched rows emit reviewed_proxy here
            # too — the L0_surface hit might route nutrition to a polluted row.
            state = self._state_from_row(row, 'canonical_surface_hit')
            # Family-base borrow: if we used another canonical's codes, the
            # trust is reviewed_proxy (borrowed, not exact).
            if borrowed_from_family and state == 'canonical_surface_hit':
                state = 'reviewed_proxy'
            # Row-level anchor fallback: canonical_surface_normalized_with_
            # product_proxies.csv carries per-surface sr28/fndds/esha codes
            # in its own columns. When canonical_items can't anchor (neither
            # on canonical_normalized nor family_base), consult the surface
            # row directly. This is the "every surface resolves" path.
            row_level_used = False
            if not sr28 and not fndds:
                row_sr28 = hit.get('row_sr28') or ''
                row_fndds = hit.get('row_fndds') or ''
                row_prod_sr28 = hit.get('row_prod_proxy_sr28') or ''
                if row_sr28 or row_fndds:
                    sr28 = row_sr28
                    fndds = row_fndds
                    row_level_used = True
                    state = 'canonical_surface_hit' if row_sr28 else 'reviewed_proxy'
                elif row_prod_sr28:
                    sr28 = row_prod_sr28
                    row_level_used = True
                    state = 'reviewed_proxy'
            # If canonical_items has neither anchor, try reviewed_nutrition_anchors
            # on the canonical's concept_key before falling out.
            row_esha = hit.get('row_esha') or ''
            if not sr28 and not fndds:
                ck = f"{nutrition}|||"
                anchor = self._anchors.get(ck)
                if anchor:
                    src = (anchor.get('source_system') or '').upper()
                    return Resolution(
                        canonical_name=nutrition,
                        sr28_fdc_id=anchor.get('food_id','') if src == 'SR28' else '',
                        fndds_code=anchor.get('food_id','') if src in ('FNDDS','BRANDED_FDC') else '',
                        description=anchor.get('description','') or desc,
                        trust_state='reviewed_proxy',
                        layer=f'L0_surface+L4/{field_name}',
                        matched_candidate=text,
                        path=path + [f"L0_surface/canonical_surface_hit: {text!r} -> nut={nutrition!r} shop={shopping!r}; anchor {anchor.get('food_id')!r}"],
                        shopping_canonical=shopping,
                        esha_code=row_esha or self._esha_for(nutrition),
                    )
            return Resolution(
                canonical_name=nutrition,
                sr28_fdc_id=sr28, fndds_code=fndds, description=desc,
                trust_state=state, layer=f'L0_surface/{field_name}',
                matched_candidate=text,
                path=path + [f"L0_surface/canonical_surface_hit: {text!r} -> nut={nutrition!r} shop={shopping!r}"],
                shopping_canonical=shopping,
                proxy_unreviewed=self._is_auto_batched(row),
                esha_code=row_esha or self._esha_for(nutrition),
            )

        # L0a: supplemental_concepts_seed.csv (43K hand-curated surface -> canonical + anchor).
        # Richest layer: carries the SR28/FNDDS anchor inline. Highest trust.
        for field_name, text in (('item', item), ('display', display),
                                  ('normalized_line', normalized_line)):
            if not text: continue
            hit = self._supplemental.get(text.strip().lower())
            if not hit: continue
            code = hit['anchor_code']
            system = hit['anchor_system']
            return Resolution(
                canonical_name=hit['canonical'],
                sr28_fdc_id=code if system == 'SR28' else '',
                fndds_code=code if system in ('FNDDS', 'BRANDED_FDC') else '',
                description=hit['description'],
                trust_state='reviewed_proxy',
                layer=f'L0a/{field_name}',
                matched_candidate=text,
                path=path + [f"L0a: supplemental {text!r} -> {hit['canonical']!r} ({system} {code})"],
            )

        # L0: approved_normalization_rules.csv (745K hand-curated surface -> concept_key)
        # — the highest-trust layer. If a recipe surface exists in the reviewed rules,
        # map directly to its concept_key and look up the reviewed anchor.
        for field_name, text in (('item', item), ('display', display),
                                  ('normalized_line', normalized_line)):
            if not text: continue
            ck = self._approved_rules.get(text.strip().lower())
            if ck is None: continue
            anchor = self._anchors.get(ck)
            if anchor:
                src = anchor.get('source_system','').upper()
                return Resolution(
                    canonical_name=ck.split('|')[0],
                    sr28_fdc_id=anchor.get('food_id','') if src=='SR28' else '',
                    fndds_code=anchor.get('food_id','') if src in ('FNDDS','BRANDED_FDC') else '',
                    description=anchor.get('description',''),
                    trust_state='reviewed_proxy',
                    layer=f'L0/{field_name}',
                    matched_candidate=text,
                    path=path + [f"L0: approved_norm_rule {text!r} -> {ck!r} -> anchor {anchor.get('food_id')!r}"])
            # No anchor on concept_key — continue cascade but stash the ck
            # as a hint for downstream layers (the canonical_items.csv base
            # may still carry nutrition).
            path.append(f"L0: approved_norm_rule {text!r} -> {ck!r} (no anchor; falling through)")
            base = ck.split('|')[0].strip().lower()
            row = self._canonical.get(base)
            if row and (row.get('sr28_fdc_id','').strip() or row.get('per_100g_kcal','').strip()):
                return Resolution(
                    canonical_name=base,
                    sr28_fdc_id=row.get('sr28_fdc_id','').strip(),
                    fndds_code=row.get('fndds_code','').strip(),
                    description=row.get('sr28_description','') or row.get('fndds_description',''),
                    trust_state='canonical_hit',
                    layer=f'L0+L1_base/{field_name}',
                    matched_candidate=text,
                    path=path + [f"L0_base: concept_key base {base!r} -> canonical_items row"])

        # L1: normalizer on `item` (Expert 3's 62% fix)
        for field_name, text, layer in (('item', item, 'L1'),
                                         ('display', display, 'L2'),
                                         ('normalized_line', normalized_line, 'L3')):
            if not text: continue
            nr = self.normalizer.normalize(text)
            path.append(f"{layer}/{field_name}={text!r} -> {nr.canonical!r}")
            if nr.canonical is not None:
                res = self._canonical_to_anchors(nr.canonical, nr, layer)
                res.path = path + res.path
                # If canonical_name_only (no anchors), fall through to L4 to find
                # a reviewed anchor on the concept_key
                if res.trust_state == 'canonical_name_only':
                    ck = self._concept_key_from_canonical(nr.canonical)
                    anchor = self._anchors.get(ck)
                    if anchor:
                        return Resolution(
                            canonical_name=nr.canonical,
                            sr28_fdc_id=anchor.get('food_id','') if anchor.get('source_system','').upper()=='SR28' else '',
                            fndds_code=anchor.get('food_id','') if anchor.get('source_system','').upper()=='FNDDS' else '',
                            description=anchor.get('description',''),
                            trust_state='reviewed_proxy',
                            layer='L1+L4',
                            matched_candidate=nr.matched_candidate,
                            path=path + [f"L4: anchor_hit ck={ck!r} -> {anchor.get('food_id')!r}"])
                return res

        # L4: reviewed_nutrition_anchors on the item as-is (in case a concept_key
        # prebuilt outside the normalizer matches)
        for field_name, text in (('item', item), ('display', display),
                                  ('normalized_line', normalized_line)):
            if not text: continue
            ck_guess = f"{text.strip().lower()}|||"
            anchor = self._anchors.get(ck_guess)
            if anchor:
                src = anchor.get('source_system','').upper()
                return Resolution(
                    canonical_name=text.strip().lower(),
                    sr28_fdc_id=anchor.get('food_id','') if src=='SR28' else '',
                    fndds_code=anchor.get('food_id','') if src in ('FNDDS','BRANDED_FDC') else '',
                    description=anchor.get('description',''),
                    trust_state='reviewed_proxy',
                    layer='L4',
                    matched_candidate=ck_guess,
                    path=path + [f"L4: anchor_hit ck={ck_guess!r}"])

        # L5: SR28 fallbacks
        for text in (item, display, normalized_line):
            if not text: continue
            row = self._sr28_fb.get(text.strip().lower())
            if row:
                return Resolution(
                    canonical_name=text.strip().lower(),
                    sr28_fdc_id=row.get('sr28_fdc_id','') or row.get('food_id',''),
                    fndds_code='',
                    description=row.get('sr28_description','') or row.get('description',''),
                    trust_state='sr28_fallback',
                    layer='L5',
                    matched_candidate=text,
                    path=path + [f"L5: sr28_fallback_hit {text!r}"])

        # L6: external catalog
        for text in (item, display, normalized_line):
            if not text: continue
            row = self._ext_cat.get(text.strip().lower())
            if row:
                return Resolution(
                    canonical_name=text.strip().lower(),
                    sr28_fdc_id=row.get('sr28_fdc_id','') or row.get('food_id',''),
                    fndds_code=row.get('fndds_code',''),
                    description=row.get('description',''),
                    trust_state='external_catalog',
                    layer='L6',
                    matched_candidate=text,
                    path=path + [f"L6: external_catalog_hit {text!r}"])

        # L8: honest terminal
        return Resolution(
            canonical_name=None, sr28_fdc_id='', fndds_code='', description='',
            trust_state='nutrition_unknown', layer='L8', matched_candidate='',
            path=path + ['L8: nutrition_unknown'])


_DEFAULT: LayeredResolver | None = None

def get_resolver() -> LayeredResolver:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = LayeredResolver()
    return _DEFAULT
