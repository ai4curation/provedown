# Hallucination Detection

Provedown is designed around a narrow but useful question:

> Does this readable document contain claims that a deterministic checker can
> falsify?

That is different from asking whether an AI system is generally truthful. A
verifier cannot prove that a report is complete, well interpreted, or
scientifically sound. It can do something more mechanical: recompute or re-fetch
specific claims and report when the document disagrees with the evidence.

## The Pattern

The core pattern is:

1. Write the claim in the document.
2. Attach the evidence needed to check it.
3. Choose a deterministic comparison policy.
4. Run a non-LLM verifier.

For computed values, the evidence is code:

```html
<code>
rows = load_rows("data/orders.csv")
paid_rows = [row for row in rows if row["status"] == "paid"]
</code>

The report includes <span class="result" data-code="len(paid_rows)">4<span class="method"></span></span> paid orders.
```

The authored value `4` is the claim. The code is evidence. The verifier executes
the code and compares the recomputed value with the authored text.

The same pattern applies beyond numbers. For identifiers, the evidence may be an
authoritative ontology or registry. For citations, the evidence may be a
publication database. For quoted support, the evidence may be the source text
itself.

## Relation To Identifier Validation

The AI4Curators guide on
[making identifiers hallucination-resistant](https://ai4curation.io/aidocs/how-tos/make-ids-hallucination-resistant/)
describes a practical rule for AI-assisted curation: require more than a
plausible-looking identifier. Require the identifier and a second piece of
information that must agree with an authoritative source, such as the canonical
label.

That is the same design pressure Provedown applies to prose claims. A claim
should not stand alone when it can be paired with checkable evidence.

Examples:

| Claim type | Authored claim | Evidence | Check |
| --- | --- | --- | --- |
| Count | `412 samples` | Python over a data file | Recompute count |
| Ontology term | `GO:0005515 protein binding` | Ontology lookup | ID exists and label matches |
| Publication | `PMID:10802651 Gene Ontology...` | PubMed metadata | PMID exists and title matches |
| Quote | Supporting text plus citation | Publication text | Excerpt appears in source |

The common idea is consistency checking. A model may produce something that
looks valid. It is harder for it to produce multiple independently checked
pieces that all agree with the relevant authority.

## Detection, Not Generation

Provedown deliberately treats the document value as authored source, not as
rendered output.

That distinction matters. If a report always renders a value fresh from code,
then there is no separate claim for a verifier to disagree with. The rendered
number simply becomes whatever the current code produces.

Provedown keeps the human-readable value in the document:

```html
The cohort has <span class="result" data-code="len(cohort)">412</span> samples.
```

If `len(cohort)` later evaluates to `410`, the verifier can say the document is
false or stale. That mismatch is the hallucination signal.

## What Provedown Can Catch

The built-in Python verifier can catch:

- fabricated or miscopied scalar values;
- stale prose after data or code changes;
- result expressions that raise errors;
- wrong comparison policies;
- broken named-code references.

The inspection and linting commands add static checks before execution:

- `provedown inspect` shows which code supports which claims;
- `provedown lint` flags unresolved references, unused named code, unjustified
  unverified claims, fragile Python patterns such as randomness or wall-clock
  time, and distant mutation of shared global state.

Future verifier plugins can extend the same model to other hallucination-prone
claims:

- ontology IDs and labels;
- gene, protein, chemical, and disease identifiers;
- publication IDs and titles;
- quoted text and cited sources;
- schema-backed references in structured data.

## What It Cannot Catch

Verification is not a substitute for review.

Provedown cannot catch a bad claim if the attached code faithfully computes the
same bad claim. It cannot know that the wrong dataset was loaded, that a
statistical method was inappropriate, or that an important caveat was omitted.

A verifier also depends on the quality of its authority:

- Computed claims depend on the code, data, and environment.
- Identifier claims depend on the registry or ontology source.
- Citation claims depend on the publication metadata source.
- Quote claims depend on access to the relevant source text.

When those inputs are wrong or incomplete, deterministic validation can still
pass the wrong thing.

## Why Deterministic Checks Matter

Hallucination detection should not rely on another language model deciding
whether the first language model sounded right.

The strongest checks are boring:

- exact equality for stable scalar values;
- numeric tolerance only when declared;
- ID existence checks against authoritative APIs;
- canonical label matching;
- deterministic substring checks for quoted support;
- explicit skips for values that are intentionally out of scope.

This is why Provedown treats `data-compare="none"` as visible metadata rather
than silently accepting unverified text. An unverified claim may be legitimate,
but it should be countable and reviewable.

## Design Consequence

Provedown's job is not to make AI write better prose. Its job is to make the
prose expose enough structure that ordinary tools can challenge it.

That leads to a simple design rule:

> Every important claim should either be verifiable, explicitly unverified, or
> obviously outside the scope of mechanical checking.

The current implementation starts with Python-backed scalar claims because they
are common and easy to check. The broader architecture is verifier-neutral so
identifier, citation, and reference validators can use the same document model.

## Sources

- [Make identifiers hallucination-resistant](https://ai4curation.io/aidocs/how-tos/make-ids-hallucination-resistant/)
- [Verifiable Literate Weave design spec](../ideas/verifiable-weave-spec.md)
