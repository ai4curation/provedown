# Verifiable Diagrams: draw.io And SVG

**Status:** exploration. The prototype is
`scripts/diagram_to_provedown.py`, with examples in `examples/diagrams/`.

Numbers in diagrams go stale and get fabricated just like numbers in prose: a
box that says "4 paid orders", an arrow labeled "n = 1,203", a funnel with
stage counts. This note looks at how Provedown claims could be embedded in
draw.io models and SVG files and checked by the existing verifier.

## What Happens Today

The parser is a permissive `HTMLParser` scan, so it accepts any text file. It
doesn't check file types. Results on hand-written diagrams:

| Input | Result |
| --- | --- |
| SVG with `<tspan class="result">` | **0 claims found; reported `ok`.** Only `span` is recognized. |
| SVG with `<span class="result">` (invalid SVG) | Claims found and checked. |
| SVG `<code>` whose body is `<![CDATA[...]]>` | **Code silently becomes empty.** `HTMLParser` routes CDATA to `unknown_decl`, which drops it. Every claim then errors with `NameError`. |
| SVG `<code>` with `&lt;`-escaped body | Works. |
| `.drawio` file | **0 events; reported `ok`.** Labels live in escaped `value`/`label` attributes, which the parser never looks inside. |

The first and last rows are the most important finding. A diagram with claims
passes vacuously, which is the worst outcome for a verifier. Whatever else we
do, `verify` should reject or warn on a file with no claims, or refuse file
types it can't handle.

## draw.io

### Constraint: draw.io strips `data-*` from HTML labels

The obvious approach puts the existing HTML contract in an HTML label:

```html
Paid orders: <span class="result" data-code="len(paid)">4</span>
```

This fails in practice. draw.io sanitizes labels with DOMPurify using
`ALLOW_DATA_ATTR: false` (`window.DOM_PURIFY_CONFIG` in
`js/grapheditor/Init.js`), and `data-code` isn't on its `ADD_ATTR` allowlist.
When a person edits such a label in the editor, or exports to SVG, the
`data-code` attribute is removed. `class="result"` is kept, so the result is a
claim that has lost its evidence.

Agents that write `.drawio` XML directly can still use HTML labels, and the
prototype accepts them. The shape style must include `html=1`, and line breaks
in an evidence label (stored by draw.io as `<br>`) are turned back into
newlines. Such labels won't survive a round trip through a human editor.

### Recommended: Shape Properties

draw.io has a native key/value store per shape. It is "Edit Data" (Ctrl+M /
Cmd+M) in the editor, and it is stored as attributes on an `<object>` wrapper
around the `mxCell`. Properties are never sanitized, and "placeholders" can
render a property into the label with `%name%`. The prototype uses the same
attribute names as the HTML contract:

```xml
<object id="paid-orders" label="Paid&lt;br&gt;&lt;b&gt;%provedown-result%&lt;/b&gt;"
        placeholders="1" provedown-result="4" data-code="len(paid)">
  <mxCell style="rounded=1;html=1;" vertex="1" parent="1">...</mxCell>
</object>
```

- **Claim**: any shape with a `data-code` property. `data-compare`, `tol`,
  `seed`, and `data-language` work as they do on `span.result`.
- **Authored value**: the `provedown-result` property if present and
  non-empty, otherwise the label's whole visible text. The fallback only works
  when the label is exactly the value (`$461.00`, not `Revenue: $461.00`), so
  prefer the property. With `placeholders="1"` and `%provedown-result%` in the
  label, the number appears once, in the property, and the diagram renders it.
  Editing it in the Edit Data dialog updates the picture. The property is
  namespaced like `provedown-code` because a bare `result` is a common name in
  imported shape data.
- **Evidence**: a shape with a `provedown-code` property, a multi-line value
  that the Edit Data dialog edits as a textarea, plus an optional `name`. The
  shape itself can be a small "evidence" note, or it can sit on a hidden layer
  or a separate page. Long code belongs in an importable Python module next to
  the diagram, as it does for Markdown reports.

The placeholder regex (`%(date\{.*\}|[^%{}"'=;]+)%`) allows hyphens, which is
what makes `%provedown-result%` work.

### Execution Order

A diagram has no reading order, and draw.io's file order is z-order. The
prototype emits **all evidence cells first, then all claims**, with pages and
cells kept in file order within each group. Evidence that depends on other
evidence must still be in the right z-order. Named code with
`<code use>`-style references could remove that dependency later.

### File Variants

| Variant | Where the model lives | Prototype |
| --- | --- | --- |
| `.drawio` uncompressed | `<diagram><mxGraphModel>` | Supported |
| `.drawio` compressed (older default) | base64 → raw deflate → URI-encoded | Supported |
| `.drawio.svg` "editable SVG" | `content` attribute on `<svg>` | Supported. The embedded model is read; the rendered SVG is ignored. |
| `.drawio.png` | `mxfile` in a PNG `tEXt`/`zTXt` chunk | Not yet; same idea as `.drawio.svg` |

The `.drawio.svg` form is attractive. It renders directly on GitHub and in
MkDocs, and it stays editable in draw.io and the VS Code draw.io extension.
Verification reads the model, not the pixels. The rendered SVG could drift
from the model only if someone edits the SVG by hand.

## SVG

For SVG files written by hand or generated by an agent, keep the HTML contract
but use SVG elements:

```xml
<svg xmlns="http://www.w3.org/2000/svg" ...>
  <metadata>
    <code name="orders">
paid = [row for row in orders if row["status"] == "paid"]
    </code>
  </metadata>
  <text x="245" y="67"><tspan class="result" data-code="len(paid)">4</tspan></text>
</svg>
```

- **Claims**: `<tspan class="result">`, or `<text class="result">` for a
  whole text run. SVG 2 allows `data-*` attributes on all elements, and
  browsers expose them through `dataset`.
- **Evidence**: `<code>` inside `<metadata>`. Renderers ignore metadata, so
  the evidence doesn't draw, and `<metadata>` explicitly allows elements from
  foreign namespaces. For visible evidence, put `<pre><code>` in a
  `<foreignObject>` with an XHTML `div`.
- **Escaping**: the code has to be XML-safe. CDATA is the natural choice, and
  the parser should support it (see below).

The prototype rewrites result `tspan`/`text` elements to `span` and escapes
CDATA without adding or removing lines, so the parser's line numbers still
point at the original SVG. Columns can shift on lines where CDATA was
unwrapped or text was escaped. The HTML form `<span class="result">` also works
inside a `<foreignObject>`.

A `tspan` claim can sit in the middle of a sentence (`Revenue <tspan
class="result">$461.00</tspan>`), so SVG doesn't need the separate authored
value that `provedown-result` provides for draw.io labels. `examples/diagrams/orders.svg`
renders correctly in Chromium with the evidence hidden (checked by hand).

Namespace hygiene is still open. A bare `<code>` in the SVG namespace is
tolerated by browsers but is not valid SVG. A namespaced form such as
`<pd:code xmlns:pd="https://ai4curation.io/provedown">` would be cleaner.
Editors like Inkscape keep unknown metadata in "Inkscape SVG" saves. Whether it
survives "plain SVG" export is untested.

### Generated SVG

For charts produced by matplotlib, Graphviz, Mermaid, and similar tools, the
SVG is a build output. The claim belongs in the generator input, for example a
Provedown-verified value that feeds a chart title, or the Markdown that embeds
the figure. We probably should not recommend verifying generated SVG directly.

## Proposed Changes To Provedown

In rough priority order:

1. **Fail closed on empty documents.** `verify` should report an error, or at
   least a warning, for a file with zero result assertions. This matters for
   Markdown too.
2. **Recognize SVG result elements.** Accept `tspan` and `text` with
   `class="result"` alongside `span`. This is a small parser change.
3. **Keep CDATA.** Handle `<![CDATA[...]]>` inside `<code>` as literal code
   text in `unknown_decl`. At minimum, emit a diagnostic instead of dropping it
   silently.
4. **Add a draw.io source adapter.** Dispatch on `.drawio`, `.drawio.svg`, and
   `.drawio.png` in `parse_file`. Build the `Document` IR directly instead of
   going through generated HTML. `SourceLocation` would need an optional
   element id (the cell id and page name) because line numbers mean nothing
   for compressed pages.
   This also needs parser diagnostics to be structured records (message,
   `SourceLocation`, severity) rendered at report time. Today they are strings
   with the location already formatted in, so the prototype has to parse
   `<string>:LINE:COL` back out of each message to point it at a cell. Each
   record also needs a stable diagnostic code, so an adapter can tell a cause
   (an unclosed `<code>`) from its cascade without matching message text.
5. **Fix ignored-region tracking in the core parser.** `_ignore_depth` adds
   one for every start tag and subtracts one for every end tag, but a bare
   void element such as `<br>` has no end tag. One `<br>` inside a
   `provedown-ignore` region leaves the parser ignoring everything after the
   region, and a void element that itself carries the marker (such as
   `<br class="provedown-ignore">`) starts a region that never ends. Either
   way, later claims are silently skipped. Conversely, a stray `</br>` inside
   a region ends it early, so ignored claims get checked. This affects ordinary
   Markdown and HTML documents, not only diagrams. The fix is to skip
   `HTML_VOID_ELEMENTS` (start and end tags) when counting and treat a void
   element carrying the marker as ignoring only itself, as the prototype's
   `_IgnoredRegions` does, with tests in `tests/test_parser.py`.
6. **Add rendering later.** Evidence disclosure on a diagram could be a
   draw.io tooltip or link on claim shapes, which draw.io already supports
   through properties.

## Try The Prototype

```bash
python scripts/diagram_to_provedown.py examples/diagrams/orders.drawio
provedown verify examples/diagrams/orders.drawio.provedown.html

python scripts/diagram_to_provedown.py examples/diagrams/orders.svg
provedown verify examples/diagrams/orders.svg.provedown.html
```

Or run `just verify-diagram-examples`, which CI runs as part of
`just check-examples`. The generated HTML is written next to the input so
relative data paths such as `../data/orders.csv` still resolve.

The converter fails closed. If the input can't be read or decoded, it writes
nothing, removes any output left from an earlier run, and exits non-zero. If
the input converts but has no claims, or a cell looks like a mistake, it still
writes the HTML but exits non-zero:

- a `provedown-result` property with no `data-code`, which is a value with
  no evidence;
- a `data-code` shape that uses the earlier property name `result` instead of
  `provedown-result`;
- a shape that has `provedown-code` and also a claim (`data-code`,
  `provedown-result`, or a `class="result"` label) or a `<code>` label, or
  that has `data-code` and also Provedown markup in its label. Only the
  property would be used, so the rest (including any `assert` in a `<code>`
  label) would be dropped without running;
- an HTML label that mixes `<code>` and `class="result"`;
- a label with Provedown markup on a shape whose style lacks `html=1`, which
  draw.io would display as literal text;
- markup that `verify` would silently skip, in an HTML label or an SVG: an
  element with `data-code` but no `class="result"` (such as a misspelled
  `class="results"`), or `class="result"` on a tag `verify` doesn't check
  (anything but `<span>` in a label, or `<text>`, `<tspan>` and `<span>` in
  an SVG). A `<code>` carrying either is still evidence, which an SVG
  passes through for `verify` to run, so that is reported too. Ignored
  regions are skipped, as `verify` skips them. Labels are parsed as HTML,
  so every spelling `verify` accepts (such as unquoted `class=result`)
  works, and spellings it would ignore are reported;
- claims `verify` would check, or evidence it would run, that differ from
  the ones the converter found outside ignored regions, including no claims
  at all. Evidence counts as much as claims: a skipped `<code>` element
  takes its assertions with it, and one run from an ignored region
  executes code the author excluded. Elements are matched by the position
  of their start tag in the generated HTML, which is unique per element (a
  `data-code` is not: a legend often shows the same expression it
  illustrates), so one gained in one place cannot hide one lost in
  another. Today this catches
  the core parser bug in proposal 5 above: a `<br>` inside or carrying
  `provedown-ignore` makes `verify` skip later markup, and a stray `</br>`
  inside a region makes it read markup the author ignored. Skipped and
  wrongly read claims and evidence are each reported separately, naming
  the first such element by its source line and column in an SVG, or in
  draw.io by its page and cell, plus its position in the label as written
  when it is in a label, with a count of any more;
- a line of the output starting with ```` ``` ```` or `~~~` (from SVG
  text, a `provedown-code` value, or an evidence label once its `<br>`s
  become line breaks), which `verify` reads as a Markdown code fence,
  skipping every line up to the matching fence or the end. A fence wholly
  inside one ignored region, such as a legend showing a fenced example,
  hides only what `verify` skips anyway, so it is allowed. Markup before
  the first other fence is still compared;
- an SVG end tag that doesn't match its start tag, or has no start tag;
- anything the Provedown parser would reject in the generated HTML, since
  `verify` refuses to run such a document. A tag nested inside `<code>` is
  reported where it occurs. An unclosed `<code>` is reported in place of the
  later tags it swallows.

A misspelled property such as `datacode` can't be told apart from unrelated
shape data, so it's caught only when the whole diagram ends up with no claims.

## Trust Boundary

A diagram is now executable input. Lowering a `.drawio` or SVG file produces
Python or SQL that `verify` runs, so the posture for untrusted Markdown applies
unchanged: only verify diagrams you would be willing to run as code, or use the
uv sandbox. The prototype also decompresses and parses diagram XML with the
standard library, which is not hardened against decompression bombs or entity
expansion.
