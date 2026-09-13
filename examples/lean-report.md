# Lean Cohort Summary

This report states its numbers in prose and attaches Lean 4 definitions as
evidence. Running `provedown verify examples/lean-report.md` re-elaborates the
Lean and checks every authored value.

<pre><code data-language="lean">
def cohortSizes : List Nat := [128, 96, 188]

def total (xs : List Nat) : Nat := xs.foldl (· + ·) 0

def largest (xs : List Nat) : Nat := xs.foldl max 0
</code></pre>

The study pooled
<span class="result" data-language="lean" data-code="cohortSizes.length">3<span class="method"></span></span>
cohorts totalling
<span class="result" data-language="lean" data-code="total cohortSizes">412<span class="method"></span></span>
samples. The largest single cohort contributed
<span class="result" data-language="lean" data-code="largest cohortSizes">188<span class="method"></span></span>
samples.

Because Lean computes on exact `Nat` values, the share held by the largest
cohort is stated in basis points rather than as a float:

<span
  class="result"
  data-language="lean"
  data-code="#largest-share-bp"
>4563<span class="method"></span></span>
basis points.

<pre><code name="largest-share-bp" data-language="lean">
largest cohortSizes * 10000 / total cohortSizes
</code></pre>
