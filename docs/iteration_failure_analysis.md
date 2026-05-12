# Product-to-ESHA Iteration Failure Analysis

Date: 2026-04-29

## Bottom Line

The failed iterations are symptoms of one architectural mistake: the pipeline repeatedly optimized assignment coverage before proving product identity, form, and category compatibility. The system could often find *a plausible nutrition code*, but not necessarily the correct retail-product concept. When a safe match did not exist, several passes still chose a near miss instead of emitting a missing-leaf or review state.

## Evidence Summary

| Area | Evidence | What It Shows |
| --- | --- | --- |
| Current whole-map status | `implementation/CURRENT_STATUS.md` reports 50,561 unassigned rows after stricter gating | Safer matching lowers coverage because previous coverage included false positives |
| Category-first route | `implementation/SPOTCHECK.md` reports 106,205 rows needing reroute, 18,823 rerouted, and only 50% strict precision on sampled reroutes | Category gates help, but ESHA lacks many needed leaves, so near misses remain unsafe |
| Fixy overlay | `implementation/FIXY_DONE_CLEANUP.md` shows blanking maps reduce coverage while flagged maps preserve it | Fixy is strong evidence, not a complete ESHA replacement layer |
| Retail mapper quality | `retail_mapper/v2/_quality_report.txt` shows 64.0% findability, 84.3% specificity loss, 73.2% ingredient coherence | The retail taxonomy remains too lossy for production truth |
| Taxonomy rebuild | `docs/taxonomy_rebuild.md` documents clustering failures and the move to a head dictionary | Bottom-up clustering created invalid paths and cross-root contamination |
| Alignment design | `docs/specs/2026-04-27-product-to-esha-alignment-system.md` states embeddings must only generate candidates | Embeddings and cluster centroids collapse similar categories without preserving identity |

## Failure Classes

### 1. Coverage Was Treated As Correctness

High coverage variants looked better numerically but reintroduced wrong assignments. Example pattern:

- `vM3`: lower coverage, but quarantined uncertain rows.
- `vSelf`: raised coverage by assigning many rows through compatible-looking heads.
- `vCluster`: projected cluster decisions, sometimes preserving cluster-level mistakes.

Observed examples from archived maps include Apple Jacks assigned to a generic cereal, almond juice assigned to unrelated juice/drink leaves, hummus-with-flatbread assigned to crackers, and apple noodle kugel assigned to cooked cinnamon apple.

### 2. ESHA Leaves Were Used As Retail Taxonomy

ESHA descriptions are nutrition reference labels, not a complete retail product taxonomy. They often lack specific leaves for kits, combo packs, specialty snacks, regional foods, flavored beverages, plant-based variants, and prepared meals. When those leaves are missing, scoring picks the nearest ESHA row instead of representing the real product.

This causes errors like:

- cereal bars routed to dry cereal leaves
- taco shell kits routed to taco recipe leaves
- grape juice routed to cranberry juice drink leaves
- pepper jelly routed to apple/mint jelly leaves
- composite dishes routed to a single ingredient

### 3. Hot-Leaf Magnets And Generic Tokens

Generic or overloaded tokens repeatedly attracted unrelated products:

- `apple`, `almond`, `milk`, `juice`, `cream`, `sandwich`, `snack`, `sauce`
- modifiers such as `original`, `natural`, `fresh`, `whole`, `pieces`, `baby`

The current matcher now strips many weak tokens and requires identity overlap, but older maps and cluster projections still contain contamination from these magnets.

### 4. Clustering Was Used Too Early

Clusters are useful for audit and consistency checks, but not as the primary decision unit. Ingredient clusters and title clusters can group products that share ingredients, category context, or brand vocabulary while requiring different ESHA codes. Centroid or dominant-code projection loses minority identity.

Safe rule: assign per product first, then use clusters to find disagreement.

### 5. Embeddings Were Used For Precision

Embedding similarity retrieves semantically adjacent candidates, but it does not prove substitutability. It collapses:

- chicken salad toward other salad/sandwich concepts
- Apple Jacks toward cereal neighbors
- almond juice toward almond milk or juice/drink neighbors
- protein/fiber almond milk toward shakes or flavored plant milk

Embedding output should be candidate recall only. Hard gates must decide.

### 6. Fixy Solved A Different Layer

Fixy ground truth is highly valuable for FNDDS alignment. `retail_mapper/fixy_v6_summary.txt` shows 456,613 rows with FNDDS assigned, but that does not automatically repair ESHA. Fixy rows also have scope gaps: many Fixy-reviewed `fdc_id`s are outside the current whole-corpus map, and description-bridge matches are useful but riskier than direct FDC overlap.

### 7. Parser And Taxonomy Debt Leaked Downstream

The taxonomy rebuild notes show why the previous taxonomy was not findable:

- form words became path nodes
- tokens crossed roots
- the same product family scattered across unrelated roots

Later dictionary work improved this, but remaining unclassified and generic heads mean downstream matching still receives incomplete product facts.

### 8. Observability Is Not Trustworthy Enough

Several audit artifacts disagree or are stale. `implementation/output/comprehensive_fix_plan.md` notes invalid queues, missing upstreams, and whole-map count mismatches. This makes it possible for a pass to appear successful because the measurement layer failed silently.

## What Not To Repeat

- Do not promote a map because coverage increased.
- Do not use ESHA/FNDDS/SR28 as the retail taxonomy spine.
- Do not use embeddings, cluster centroids, or dominant cluster codes as final truth.
- Do not trust legacy assignments without revalidation.
- Do not treat ingredient overlap as product identity.
- Do not force rows with missing ESHA leaves into nearby codes.
- Do not use broad terms or modifiers as assignment anchors.

## Corrective Direction

The next durable architecture should follow the existing alignment design:

1. Extract product facts per row: identity terms, form, role, category lane, brand, and target heads.
2. Build reference facts for ESHA, FNDDS, and SR28 using the same extraction path.
3. Use embeddings only to retrieve top-K candidates.
4. Apply hard gates before scoring: identity noun, form family, category lane, and brand/group homogeneity where relevant.
5. Reconcile ESHA/FNDDS/SR28 as separate candidate sources instead of forcing ESHA priority.
6. Emit `NEEDS_NEW_CONCEPT`, `IDENTITY_GATE_FAILED`, or `LOW_CONFIDENCE` when no safe match exists.
7. Use clusters only after assignment to detect disagreements and missing leaves.
8. Fix observability first so false accepts, missing contracts, unassigned rows, and coverage changes are measured consistently.

## Priority Issue Queue

1. Repair observability and stale/missing artifact references.
2. Preserve strict whole-map gates and stop forced coverage rebuilds.
3. Build or validate product/reference fact catalogs.
4. Convert known hot-leaf failures into hard negative tests.
5. Drive missing-leaf queues by family: milk subtypes, plant milk/creamer/shake, produce specificity, jelly/preserve/spread, snacks/bars, kits, and composite dishes.
6. Treat Fixy as evidence for FNDDS and review, not automatic ESHA truth.
7. Keep retail taxonomy work separate from nutrition-code assignment, then connect them through explicit gates.
