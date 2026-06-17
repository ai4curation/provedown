# Write Result Assertions

A result assertion is the smallest Provedown contract: an authored value in prose
and the code that should reproduce it.

## Inline Expressions

Use `data-code` for short Python expressions:

````markdown
<code>
samples = ["alpha", "beta", "gamma"]
</code>

The cohort has <span class="result" data-code="len(samples)">3<span class="method"></span></span> samples.
````

The authored value is the text inside the result span: `3`.

The expression is `len(samples)`.

The optional `<span class="method"></span>` slot is ignored by the verifier. It
is reserved for renderers that may later inject method markers or disclosure UI.

## Exact Comparison

Exact comparison is the default:

````markdown
The answer is <span class="result" data-code="answer">42<span class="method"></span></span>.
````

The computed value is converted to text with `str()`, then compared with the
authored text.

## Numeric Comparison

Use `data-compare="numeric"` when textual representations may differ but numeric
values should match:

````markdown
The total is <span class="result" data-code="total" data-compare="numeric">42<span class="method"></span></span>.
````

This treats `42` and `42.0` as equal.

## Tolerance Comparison

Use `tol` or `data-tol` for floating-point values:

````markdown
The rate is <span class="result" data-code="rate" tol="1e-6">0.333333<span class="method"></span></span>.
````

The parser assigns the `tol` comparison policy automatically when a tolerance
attribute is present and `data-compare` is not set.

## Set Comparison

Use `data-compare="set"` for unordered collections:

````markdown
The observed labels are <span class="result" data-code="labels" data-compare="set">alpha,beta,gamma<span class="method"></span></span>.
````

The Python verifier can compare authored comma-separated text, Python literal
collections, and computed sets, lists, tuples, or dict keys.

## Seeded Comparison

Use `seed` or `data-seed` when an assertion depends on Python randomness:

````markdown
<code>
import random
</code>

The draw is <span class="result" data-code="random.randint(1, 10)" seed="7">6<span class="method"></span></span>.
````

The Python verifier seeds Python's `random` module. If `np` is present in the
execution namespace and has `np.random`, it seeds NumPy's random generator too.

## Explicitly Unverified Claims

Use `data-compare="none"` only when a value is intentionally outside the current
verification contract:

````markdown
The external service status is <span class="result" data-code="status()" data-compare="none">available<span class="method"></span></span>.
````

The Python verifier does not evaluate the expression. It emits a `skip` finding.

## Other Languages

The markup is language-neutral. Add `data-language`, `language`, or `lang` to
mark a result for another verifier:

````markdown
The answer is <span class="result" data-code="select 40 + 2" data-language="sql">42<span class="method"></span></span>.
````

Built-in language names:

`python`, `py`
: Handled by `python-results`.

`sql`, `duckdb`, `duckdb-sql`
: Handled by `sql-results`.

Verifiers ignore result spans for other languages. Use `data-compare="none"`
when a claim is intentionally unverified and should produce an explicit `skip`.
