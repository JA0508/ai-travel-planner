# Style Attribution QA Sample Conventions

This directory keeps the internal parser-QA sample layers for style attribution.

## Layers

### `strict`
File: [style_attribution_samples.jsonl](style_attribution_samples.jsonl)

Use `strict` for small boundary-case samples with stable expected provenance.

Add a sample here only when:
- it covers a clean attribution boundary such as `request_wording`, `parser_explicit`, `parser_inferred`, or `poi_mix`
- we want hard regression assertions on its exact output
- the wording is intentionally compact and low-ambiguity

Good `strict` samples:
- explicit museum wording without museum-heavy POIs
- museum-heavy POI mix without explicit wording
- parser-inferred vs poi-mix inferred distinction
- explicit-over-inferred dominance

### `realistic`
File: [style_attribution_realistic_corpus.jsonl](style_attribution_realistic_corpus.jsonl)

Use `realistic` for natural-sounding request wording that still represents clear style intent.

Add a sample here when:
- the request sounds like a real user message
- we want drift-oriented observability, not brittle exact assertions
- the wording is more natural than the `strict` boundary cases

This layer should prefer softer checks such as:
- corpus remains inspectable
- useful provenance categories still appear
- explicit / inferred distributions do not collapse unexpectedly

### `internal`
File: [style_attribution_internal_corpus.jsonl](style_attribution_internal_corpus.jsonl)

Use `internal` for longer-lived, product-like internal requests that help us watch attribution behavior over time.

Add a sample here when:
- it looks like a plausible planning request we may see in the product
- it adds coverage breadth more than a precise boundary assertion
- we want long-term observational QA instead of exact provenance locking

This layer is the right place for:
- mixed-intent requests
- product-like multi-line requests
- cases that feel valuable to keep watching but are too natural/noisy for `strict`

## Promotion rule

Promote a case from `realistic` or `internal` into `strict` only when all of these are true:
- the same attribution drift or boundary confusion keeps recurring
- the desired attribution behavior is now clear and stable
- the wording can be rewritten into a compact, low-ambiguity boundary sample
- exact provenance assertions will improve confidence more than they increase brittleness

If a case is still valuable mainly for observation, keep it in `realistic` or `internal`.

## Internal-sample hygiene

For `internal` samples:
- keep wording realistic but anonymized
- do not include personal names, booking numbers, phone numbers, or addresses
- avoid directly copying raw user messages; lightly rewrite them into representative product-like requests
- prefer generic, durable labels in `snake_case`

## Sample authoring conventions

All sample files are JSONL with one object per line.

Required fields:
- `label`
- `text`

Optional fields:
- `parser_mode`
- `style_preferences`
- `style_preference_sources`

Use override fields only when the sample is intentionally testing parser-source provenance such as:
- `parser_explicit`
- `parser_inferred`
- explicit-over-inferred reconciliation

## Workflow

Run the inspector on a named layer:

```bash
PYTHONPATH=backend python backend/tools/inspect_parsed_style_attribution.py --sample-set strict
PYTHONPATH=backend python backend/tools/inspect_parsed_style_attribution.py --sample-set realistic
PYTHONPATH=backend python backend/tools/inspect_parsed_style_attribution.py --sample-set internal
```

Use `strict` for exact regression checks.
Use `realistic` for lighter drift inspection.
Use `internal` for longer-lived observational QA.

## Lightweight review cadence

Keep this review loop small and practical:

### When to review
- after parser / intent-extraction changes that touch style attribution
- when a recurring attribution drift shows up in QA or manual inspection
- when the realistic or internal corpora start to feel skewed toward one style bucket

### Quick review checklist
- run `strict` and confirm exact boundary assertions still pass
- run `realistic` and check whether aggregate provenance still looks healthy
- run `internal` and scan for recurring drift patterns or newly unstable request shapes
- note whether any internal/realistic case now looks stable and important enough for `strict`
- note whether any corpus has become too repetitive and needs rebalancing

### Promotion guidance

Promote a case into `strict` when:
- the same drift pattern has appeared more than once
- the desired attribution outcome is no longer controversial
- the case can be rewritten into a short, low-ambiguity boundary sample
- locking exact provenance will prevent future confusion

Keep a case in `realistic` or `internal` when:
- it is still mainly useful for observation
- the wording is naturally messy or product-like
- the value comes from coverage breadth rather than exact boundary enforcement

### Refresh guidance

Refresh `realistic` or `internal` when:
- one style category is overrepresented
- multiple samples are saying nearly the same thing
- product request patterns have shifted and a common request shape is missing

Prefer replacing stale near-duplicates over simply growing the corpus indefinitely.
