# Confidence Filtering in the Annotation Pipeline

This method report makes two different kinds of claim, and they are checked in
two different ways. Counts describe *this* release and are checked against the
release's own data. Guarantees describe the filter *itself* and are checked
against a machine-verified proof, because no amount of counting this release
establishes what the code does on the next one.

## What this release contains

<pre><code>
import csv

with open("data/curation_scores.csv", newline="") as handle:
    annotations = list(csv.DictReader(handle))

THRESHOLD = 70
kept = [row for row in annotations if int(row["confidence"]) >= THRESHOLD]
dropped = len(annotations) - len(kept)
</code></pre>

The release contains
<span class="result" data-code="len(annotations)">412<span class="method"></span></span>
candidate annotations. Filtering at a confidence threshold of
<span class="result" data-code="THRESHOLD">70<span class="method"></span></span>
retains
<span class="result" data-code="len(kept)">188<span class="method"></span></span>
and drops
<span class="result" data-code="dropped">224<span class="method"></span></span>.

The lowest confidence among retained annotations is
<span
  class="result"
  data-code="min(int(row['confidence']) for row in kept)"
>70<span class="method"></span></span>,
which is consistent with the threshold — but consistency on one release is not
the same as a guarantee.

## What the filter guarantees

Those counts are facts about 412 rows. The two claims below are facts about the
filter, for every possible input, and each is backed by a proof that Lean
checks and that `provedown verify` re-checks on every run.

<pre><code data-language="lean">
def keepAbove (t : Nat) : List Nat → List Nat
  | [] => []
  | x :: xs => if x >= t then x :: keepAbove t xs else keepAbove t xs

theorem keepAbove_never_invents (t : Nat) (xs : List Nat) :
    (keepAbove t xs).length ≤ xs.length := by
  induction xs with
  | nil => simp [keepAbove]
  | cons x xs ih =>
    simp only [keepAbove]
    split
    · simp; omega
    · simp; omega

theorem keepAbove_sound (t : Nat) (xs : List Nat) (y : Nat) :
    y ∈ keepAbove t xs → t ≤ y := by
  induction xs with
  | nil => simp [keepAbove]
  | cons x xs ih =>
    simp only [keepAbove]
    split
    next hx =>
      intro h
      rcases List.mem_cons.mp h with h1 | h2
      · omega
      · exact ih h2
    next hx => exact ih
</code></pre>

**The filter never fabricates an annotation.** Whatever the threshold and
whatever the input, the output is no longer than the input:

<span
  class="result"
  data-language="lean-proof"
  data-code="keepAbove_never_invents"
>∀ (t : Nat) (xs : List Nat), (keepAbove t xs).length ≤ xs.length<span
class="method"></span></span>

**The filter never retains a below-threshold annotation.** Every surviving
record genuinely meets the cutoff — not merely in this release, but in all of
them:

<span
  class="result"
  data-language="lean-proof"
  data-code="keepAbove_sound"
>∀ (t : Nat) (xs : List Nat) (y : Nat), y ∈ keepAbove t xs → t ≤ y<span
class="method"></span></span>

Each proof claim is checked three ways: the named theorem must exist, its
statement must match the one printed above, and it must depend on no axiom
beyond Lean's standard three. A `sorry` anywhere in its dependencies — even in
a lemma proved in another file — shows up as `sorryAx` and fails the report.
