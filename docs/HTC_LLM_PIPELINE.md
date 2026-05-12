# HTC LLM Pipeline — Complete Writeup

**Goal:** Use a cheap LLM API (DeepSeek) to classify ~75k recipe ingredients and ~9k retail canonical paths into 8-character Hestia Taxonomy Codes, then marry those codes to nutrition database keys.

**Total estimated cost:** ~$5 USD for the entire corpus.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Files in This Pipeline](#files-in-this-pipeline)
3. [The Condensed Dictionary](#the-condensed-dictionary)
4. [Step 1: Batch Encoding via LLM](#step-1-batch-encoding-via-llm)
5. [Step 2: Align to Nutrition Database](#step-2-align-to-nutrition-database)
6. [Cost Breakdown](#cost-breakdown)
7. [Running the Full Pipeline](#running-the-full-pipeline)
8. [Output Schema](#output-schema)
9. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
┌─────────────────┐     ┌──────────────────────┐     ┌──────────────────┐
│  Raw Inputs     │     │  DeepSeek API        │     │  Nutrition DB    │
│  (CSV/JSONL)    │────▶│  (batched 50/prompt) │────▶│  (canonical_     │
│                 │     │                      │     │   items.csv)     │
└─────────────────┘     └──────────────────────┘     └──────────────────┘
         │                       │                            │
         ▼                       ▼                            ▼
  recipe_ingredient_      llm_htc_output.jsonl          aligned_nutrition.csv
  items.csv               {item, htc_code, modifier,  {item, htc_code,
                          flavor, ...}                  ingredient_key,
                                                          nutrition...}
```

There are **three stages:**

1. **Prepare** — load the condensed dictionary + input items
2. **Encode** — send batches of 50 items to the LLM, get back structured JSON
3. **Align** — fuzzy-match LLM output to `canonical_items.csv` to resolve nutrition keys

---

## Files in This Pipeline

| File | Purpose | Status |
|------|---------|--------|
| `docs/HTC_CONDENSED_DICTIONARY.md` | Complete codebook + prompt template for the LLM | ✅ Written |
| `implementation/batch_encode_htc.py` | API client that batches 50 items/prompt, handles retries, parses JSON | ✅ Written |
| `implementation/align_llm_htc_to_nutrition.py` | Marries LLM output to `canonical_items.csv` using fuzzy matching | ✅ Written |
| `implementation/canonical_items.csv` | 9,614-row nutrition database lookup (canonical name → ESHA/SR28/FNDDS + macros) | Existing |

---

## The Condensed Dictionary

**Location:** `docs/HTC_CONDENSED_DICTIONARY.md`

**Size:** ~14 KB, ~4,000 tokens

**Contents:**
- 8-character code format (positions 1–8)
- Crockford base32 alphabet + mod-37 check algorithm
- All 21 Group codes with typical keywords
- Family tables for every group (Dairy, Red Meat, Poultry, Vegetables, Fruits, Grains, Spices, Condiments)
- Form codes (fresh, frozen, canned, dried, powder, liquid, smoked, pickled)
- Processing codes (raw, cooked, cured, fermented, ready-to-eat, seasoned, breaded, fortified)
- Product Type / Cut codes (whole, sliced, ground, steak, shredded, cubed, patty, strip)
- 6 worked examples with full reasoning chains
- A ready-to-paste API prompt template

**How it works:** Instead of giving the LLM regexes, we give it semantic tables. The LLM uses its own understanding of words like "cheese", "sliced", "frozen" to pick the right codes. The dictionary only needs to teach it the *arbitrary character mappings* (e.g., Dairy = `1`, Cheese family = `1`, Sliced = `1`).

---

## Step 1: Batch Encoding via LLM

**Script:** `implementation/batch_encode_htc.py`

### What it does
1. Loads `docs/HTC_CONDENSED_DICTIONARY.md` as the system prompt
2. Reads your input CSV (expects an `item` column)
3. Batches items into groups of 50
4. Sends each batch to the DeepSeek API with `temperature=0.0`
5. Requests a strict JSON array response
6. Parses, validates, and writes results incrementally to JSONL
7. Supports `--resume` to pick up where it left off

### Input format
CSV with at minimum an `item` column:
```csv
item
"1/4 cup milk"
"WHITE AMERICAN CHEESE SLICES"
"chipotle mayonnaise"
"ground beef"
```

Or a plain text file with one item per line.

### Output format
JSONL where each line is:
```json
{"item": "ground beef", "htc_code": "2000002X", "htc_group": "2", "htc_family": "0", "modifier": "", "flavor": ""}
```

### Prompt design
Each batch gets a user message like:

```
Encode the following items into HTC codes.

Return ONLY a valid JSON array. Each element must be an object with these exact keys:
  "item"       — the original item string (exactly as given)
  "htc_code"   — the full 8-character HTC code (7 chars + check digit)
  "htc_group"  — the 1-character group code
  "htc_family" — the 1-character family code
  "modifier"   — discovered modifier, or "" if none
  "flavor"     — discovered flavor, or "" if none

Items:
1. "1/4 cup milk"
2. "WHITE AMERICAN CHEESE SLICES"
...
50. "chipotle mayonnaise"

JSON array:
```

The model returns:
```json
[
  {"item": "1/4 cup milk", "htc_code": "1006000?", "htc_group": "1", "htc_family": "0", "modifier": "whole", "flavor": ""},
  ...
]
```

### Why batching 50 works
- The system prompt (~4,000 tokens) is amortized over 50 items
- Total input per call: ~5,500 tokens
- Total output per call: ~1,500 tokens
- For 75,000 items: only ~1,500 API calls
- DeepSeek handles 5,500-token prompts easily

---

## Step 2: Align to Nutrition Database

**Script:** `implementation/align_llm_htc_to_nutrition.py`

### What it does
1. Loads `implementation/canonical_items.csv` into memory
2. Reads the JSONL from Step 1
3. For each item:
   - Strips quantity/unit (e.g., `"1/4 cup milk"` → `"milk"`)
   - Normalizes text (lowercase, strip weak tokens)
   - Searches for exact match → substring match → token overlap → fuzzy match
   - Picks best candidate from canonical_items.csv
   - Returns nutrition key (`ESHA:xxx`, `SR28:xxx`, or `FNDDS:xxx`)
   - Preserves LLM-discovered modifier and flavor as separate columns
4. Writes a CSV with everything you need for recipe costing

### Matching logic
| Method | Confidence | Example |
|--------|-----------|---------|
| Exact | 1.00 | `"milk"` → `milk` |
| Substring | 0.70–0.95 | `"WHITE AMERICAN CHEESE SLICES"` → `american cheese` |
| Token overlap | 0.50–0.70 | `"ground cumin shaker"` → `cumin` |
| Fuzzy fallback | 0.60–0.85 | rapidfuzz/difflib on remaining candidates |

### Nutrition key priority
1. **ESHA** (highest fidelity, recipe-matched)
2. **SR28** (USDA reference, fallback)
3. **FNDDS** (FNDDS survey, fallback)

---

## Cost Breakdown

### Scale
| Dataset | Unique Items | Batches (size 50) |
|---------|-------------|-------------------|
| Recipe ingredients | ~74,000 | ~1,480 |
| Retail canonical paths | ~9,200 | ~184 |
| **Total** | **~83,000** | **~1,665** |

### Token math per batch
| Component | Tokens |
|-----------|--------|
| System prompt (dictionary) | ~4,000 |
| 50 item strings | ~1,500 |
| **Input per batch** | **~5,500** |
| JSON output (50 objects) | ~1,500 |
| **Output per batch** | **~1,500** |

### Total tokens
| Direction | Calculation | Total |
|-----------|-------------|-------|
| Input | 1,665 batches × 5,500 | **~9.2M tokens** |
| Output | 1,665 batches × 1,500 | **~2.5M tokens** |

### Pricing (DeepSeek V3 — check current rates at https://api.deepseek.com/quick_start/pricing/)

| Pricing tier | Rate (typical) | Cost |
|-------------|----------------|------|
| Input (cache miss) | ~$0.27 / 1M tokens | ~$2.50 |
| Input (cache hit)* | ~$0.07 / 1M tokens | ~$0.65 |
| Output | ~$1.10 / 1M tokens | ~$2.75 |
| **Total (worst case)** | | **~$5.25** |
| **Total (with caching)** | | **~$3.40** |

\* *After the first call, DeepSeek caches the system prompt. Subsequent calls pay the cheaper cache-hit rate for those 4,000 tokens.*

### Comparison
| Approach | Cost |
|----------|------|
| **Smart batching (this pipeline)** | **~$3–5** |
| Dumb (1 item per call, no caching) | ~$80+ |
| OpenAI GPT-4o equivalent | ~$150–300 |
| Manual human labeling | ~$2,000–5,000 |

---

## Running the Full Pipeline

### Prerequisites
```bash
pip install openai
# Optional but recommended for faster fuzzy matching:
pip install rapidfuzz

export DEEPSEEK_API_KEY="sk-..."
```

### Stage 1: Encode recipe ingredients
```bash
python3 implementation/batch_encode_htc.py \
    --input recipe_mapper/v1/output/recipe_ingredient_items.csv \
    --output /tmp/recipe_htc.jsonl \
    --batch-size 50 \
    --model deepseek-chat \
    --resume
```

### Stage 2: Encode retail canonical paths
```bash
# First extract unique canonical paths from the audit file
awk -F',' 'NR>1 {print $11}' retail_mapper/v2/consensus_full_corpus_audit.v2.csv | sort -u > /tmp/unique_canonical_paths.txt

python3 implementation/batch_encode_htc.py \
    --input /tmp/unique_canonical_paths.txt \
    --output /tmp/retail_htc.jsonl \
    --batch-size 50 \
    --model deepseek-chat \
    --resume
```

### Stage 3: Align both to nutrition DB
```bash
# Recipe side
python3 implementation/align_llm_htc_to_nutrition.py \
    --input /tmp/recipe_htc.jsonl \
    --output implementation/output/recipe_htc_aligned.csv

# Retail side
python3 implementation/align_llm_htc_to_nutrition.py \
    --input /tmp/retail_htc.jsonl \
    --output implementation/output/retail_htc_aligned.csv
```

### Combine (optional)
```bash
cat implementation/output/recipe_htc_aligned.csv > implementation/output/all_htc_aligned.csv
tail -n +2 implementation/output/retail_htc_aligned.csv >> implementation/output/all_htc_aligned.csv
```

---

## Output Schema

### `batch_encode_htc.py` output (JSONL)
```json
{
  "item": "Lay's BBQ Potato Chips",
  "htc_code": "J000000X",
  "htc_group": "J",
  "htc_family": "0",
  "modifier": "",
  "flavor": "BBQ"
}
```

### `align_llm_htc_to_nutrition.py` output (CSV)
| Column | Description |
|--------|-------------|
| `item` | Original input string |
| `htc_code` | 8-char HTC code from LLM |
| `matched_canonical` | Best-match canonical name from DB |
| `ingredient_key` | `ESHA:xxx`, `SR28:xxx`, or `FNDDS:xxx` |
| `key_type` | Which database won |
| `confidence` | Match confidence (0.0–1.0) |
| `modifier` | LLM-discovered modifier |
| `flavor` | LLM-discovered flavor |
| `per_100g_kcal` | Calories per 100g |
| `per_100g_protein_g` | Protein per 100g |
| `per_100g_fat_g` | Fat per 100g |
| `per_100g_carbs_g` | Carbs per 100g |
| `match_method` | exact / substring / token_overlap / fuzzy |

---

## Troubleshooting

### "API call failed after all retries"
- Check your `DEEPSEEK_API_KEY`
- Verify `--base-url` is correct (default: `https://api.deepseek.com`)
- Check your account balance at DeepSeek

### "Parse failed on batch X"
- The model occasionally returns markdown-wrapped JSON or adds commentary.
- The script tries to extract the JSON array automatically.
- If it still fails, the batch is flagged with `_parse_failed=true` and you can inspect `_raw_preview`.

### Missing check digits
- The LLM sometimes returns 7-char codes instead of 8.
- You can re-run just those rows, or compute check digits post-hoc using `recipe_mapper/v1/htc/encoder.py`.

### Low confidence matches
- If `confidence < 0.7`, the fuzzy matcher is guessing.
- Review those rows manually or add more canonical entries to `canonical_items.csv`.

### Resume after interruption
- Both scripts support `--resume`.
- `batch_encode_htc.py` skips items already in the output JSONL.
- `align_llm_htc_to_nutrition.py` does not need resume — it just re-processes.

---

## Summary

- **System prompt:** `docs/HTC_CONDENSED_DICTIONARY.md` (~4,000 tokens)
- **API client:** `implementation/batch_encode_htc.py` (50 items/prompt, ~$3–5 total)
- **Aligner:** `implementation/align_llm_htc_to_nutrition.py` (fuzzy match to nutrition DB)
- **Total unique items:** ~83,000
- **Total API calls:** ~1,665
- **Total cost:** Less than a burrito

Ready to run it?
