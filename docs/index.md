# Provedown

<div class="pd-hero" markdown>

Markdown-native verifiable literate documents. Write reports for people, attach
small executable evidence to the claims that matter, and let a non-LLM verifier
check the numbers.

[Start the tutorial](tutorials/first-verified-report.md){ .md-button .md-button--primary }
[Read the markup contract](reference/markup.md){ .md-button }

</div>

## What It Does

Provedown keeps the human-readable document as the source of truth. Values in
prose are authored claims, not generated render output, and verifier plugins can
recompute those claims from embedded evidence.

```html
<code>
x = 410 + 2
</code>

The cohort has <span class="result" data-code="x">412<span class="method"></span></span> samples.
```

## Find Your Path

<div class="grid cards" markdown>

- **Learn the loop**

    Create a first report, run the verifier, and see how mismatches are
    reported.

    [First verified report](tutorials/first-verified-report.md)

- **Use real inputs**

    Import standard-library modules, read local CSV files, and verify prose
    claims against computed summaries.

    [Python modules and data files](how-to-guides/use-python-modules-and-data-files.md)

- **Inspect and lint**

    Understand which code supports which claims, then catch fragile document
    structure before verification.

    [Inspect dependencies](how-to-guides/inspect-claim-dependencies.md)

- **Check the contract**

    Review the recognized HTML elements, attributes, comparison policies, and
    CLI behavior.

    [Markup contract](reference/markup.md)

- **Understand hallucination checks**

    See how Provedown turns important prose claims into values that deterministic
    tools can challenge.

    [Hallucination detection](explanations/hallucination-detection.md)

</div>

## Documentation Map

This documentation follows the Diataxis structure:

- **Tutorials** teach new workflows step by step.
- **How-to guides** solve focused operational tasks.
- **Reference** describes stable APIs, commands, and file formats.
- **Explanations** discuss design choices and tradeoffs.

The project is still early, so examples and reference pages describe what exists
today while design notes track where the format is heading.
