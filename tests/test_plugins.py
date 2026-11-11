import importlib
import json
import sys
from pathlib import Path

import pytest
from pytest import CaptureFixture, MonkeyPatch

from provedown import (
    VERIFIER_ENTRY_POINT_GROUP,
    PluginLoadError,
    Status,
    UnknownVerifierError,
    default_registry,
    load_plugin_verifiers,
    parse_document,
    verify_document,
)
from provedown.cli import main

PLUGIN_MODULE = """
from provedown import Finding, SourceLocation, Status


class EventCountVerifier:
    verifier_id = "event-count"

    def verify(self, document, context):
        del context
        yield Finding(
            verifier_id=self.verifier_id,
            status=Status.PASS,
            location=SourceLocation(path=document.path, line=1, column=1),
            message=f"{len(document.events)} events",
        )


def make_verifier():
    return EventCountVerifier()


class ClashingVerifier(EventCountVerifier):
    verifier_id = "python-results"


def broken():
    raise RuntimeError("no source cache configured")


class _UnstringableLoadError(Exception):
    def __str__(self):
        raise RuntimeError("str exploded")


def unstringable_broken():
    raise _UnstringableLoadError()


def huge_broken():
    raise ValueError("schema " * 20000)


class RaisingIdVerifier:
    @property
    def verifier_id(self):
        raise RuntimeError("lazy import failed")

    def verify(self, document, context):
        return []


class AttributeErrorIdVerifier:
    @property
    def verifier_id(self):
        return self._missing_module.Thing

    def verify(self, document, context):
        return []


class UnsetSlotVerifier:
    __slots__ = ("verifier_id",)

    def verify(self, document, context):
        return []


class RaisingVerifyVerifier:
    verifier_id = "raising-verify"

    @property
    def verify(self):
        raise RuntimeError("lazy import failed")


class ShiftingIdVerifier:
    # Returns a fresh id on the first read and a taken one afterwards.

    def __init__(self):
        self._reads = 0

    @property
    def verifier_id(self):
        self._reads += 1
        return "fresh-id" if self._reads == 1 else "python-results"

    def verify(self, document, context):
        return []


def not_a_verifier():
    return {"verifier_id": "dict"}


class SecondEventCountVerifier(EventCountVerifier):
    pass


LOADED = []


class FirstByName(EventCountVerifier):
    verifier_id = "first"

    def __init__(self):
        LOADED.append("aaa")


class SecondByName(EventCountVerifier):
    verifier_id = "second"

    def __init__(self):
        LOADED.append("zzz")


class CrashingVerifier:
    verifier_id = "crashing"

    def verify(self, document, context):
        raise RuntimeError("source cache is corrupt")


class _UnstringableError(Exception):
    def __str__(self):
        raise RuntimeError("str exploded")


class UnstringableRaiseVerifier:
    verifier_id = "unstringable"

    def verify(self, document, context):
        yield Finding(
            verifier_id=self.verifier_id,
            status="pass",
            location=SourceLocation(path=document.path, line=1, column=1),
            message="before the raise",
        )
        raise _UnstringableError()


class SourceFetchError(Exception):
    pass


class ChainedErrorVerifier:
    verifier_id = "chained"

    def verify(self, document, context):
        try:
            raise ConnectionError("dns lookup failed for example.org")
        except ConnectionError as exc:
            raise SourceFetchError("could not fetch source") from exc


class HugeErrorVerifier:
    verifier_id = "huge-error"

    def verify(self, document, context):
        raise RuntimeError("x" * 100000)


class StringStatusVerifier:
    verifier_id = "strings"

    def verify(self, document, context):
        yield Finding(
            verifier_id=self.verifier_id,
            status="pass",
            location=SourceLocation(path=document.path, line=1, column=1),
            message="plain string status",
        )


class BadStatusVerifier:
    verifier_id = "bad-status"

    def verify(self, document, context):
        yield Finding(
            verifier_id=self.verifier_id,
            status="passed",
            location=SourceLocation(path=document.path, line=1, column=1),
            message="unknown status",
        )


class StringLocationVerifier:
    verifier_id = "bad-location"

    def verify(self, document, context):
        yield Finding(
            verifier_id=self.verifier_id,
            status="pass",
            location="report.md:1:1",
            message="location is a string",
        )


class HugeYieldVerifier:
    verifier_id = "huge"

    def verify(self, document, context):
        yield {"rows": list(range(10000))}


class PathEvidenceVerifier:
    verifier_id = "path-evidence"

    def verify(self, document, context):
        from pathlib import Path

        yield Finding(
            verifier_id=self.verifier_id,
            status="pass",
            location=SourceLocation(path=document.path, line=1, column=1),
            message="evidence holds a Path",
            evidence={"source": Path("refs/paper.md")},
        )


class ListEvidenceVerifier:
    verifier_id = "list-evidence"

    def verify(self, document, context):
        yield Finding(
            verifier_id=self.verifier_id,
            status="pass",
            location=SourceLocation(path=document.path, line=1, column=1),
            message="evidence is a list",
            evidence=[1, 2],
        )


CLOSED = []


class CleanupVerifier:
    verifier_id = "cleanup"

    def verify(self, document, context):
        try:
            yield "not a finding"
            yield "never reached"
        finally:
            CLOSED.append(True)


class _Unprintable:
    def __repr__(self):
        raise RuntimeError("repr exploded")


def unprintable_factory():
    return _Unprintable()


class BadReprVerifier:
    verifier_id = "bad-repr"

    def verify(self, document, context):
        class Unprintable:
            def __repr__(self):
                raise RuntimeError("repr exploded")

        yield Unprintable()


class DictVerifier:
    verifier_id = "dicts"

    def verify(self, document, context):
        yield Finding(
            verifier_id=self.verifier_id,
            status=Status.PASS,
            location=SourceLocation(path=document.path, line=1, column=1),
            message="first is fine",
        )
        yield {"status": "pass"}
"""


def install_plugin(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    entry_points: dict[str, str],
    distribution: str = "countplugin",
) -> None:
    """Install a real distribution on ``sys.path`` that advertises verifiers."""

    (tmp_path / "countplugin.py").write_text(PLUGIN_MODULE, encoding="utf-8")
    dist_info = tmp_path / f"{distribution}-0.1.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {distribution}\nVersion: 0.1\n",
        encoding="utf-8",
    )
    lines = [f"[{VERIFIER_ENTRY_POINT_GROUP}]"]
    lines.extend(f"{name} = {target}" for name, target in entry_points.items())
    (dist_info / "entry_points.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    # Each test writes its own module; never reuse one an earlier test imported.
    # This clears a module left by an earlier test (delitem records nothing when
    # the key is absent), so every test that imports the plugin must call this.
    monkeypatch.delitem(sys.modules, "countplugin", raising=False)


def test_no_plugins_installed_leaves_the_builtin_verifiers() -> None:
    # Describes CI's environment: fails if a Provedown plugin is installed here.
    assert load_plugin_verifiers() == []
    assert default_registry().names() == ["python-results", "sql-results"]


def test_default_registry_loads_entry_point_verifiers(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    install_plugin(
        tmp_path, monkeypatch, {"event-count": "countplugin:EventCountVerifier"}
    )

    registry = default_registry()

    assert registry.names() == ["event-count", "python-results", "sql-results"]
    report = verify_document(
        parse_document("<code>x = 1</code>"),
        registry=registry,
        verifier_ids=["event-count"],
    )
    assert [finding.message for finding in report.findings] == ["1 events"]


def test_entry_point_may_name_a_factory_function(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    install_plugin(tmp_path, monkeypatch, {"event-count": "countplugin:make_verifier"})

    assert [verifier.verifier_id for verifier in load_plugin_verifiers()] == [
        "event-count"
    ]


def test_plugins_can_be_left_out(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    install_plugin(
        tmp_path, monkeypatch, {"event-count": "countplugin:EventCountVerifier"}
    )

    assert default_registry(plugins=False).names() == [
        "python-results",
        "sql-results",
    ]


def test_plugin_that_fails_to_load_names_its_entry_point(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    install_plugin(tmp_path, monkeypatch, {"broken": "countplugin:broken"})

    with pytest.raises(PluginLoadError, match="'broken' from countplugin") as info:
        default_registry()
    assert "no source cache configured" in str(info.value)


def test_plugin_cannot_replace_an_existing_verifier(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    install_plugin(tmp_path, monkeypatch, {"clash": "countplugin:ClashingVerifier"})

    with pytest.raises(
        PluginLoadError, match=r"'clash' from countplugin .*'python-results'"
    ):
        default_registry()


def test_cli_lists_and_runs_plugin_verifiers(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    install_plugin(
        tmp_path, monkeypatch, {"event-count": "countplugin:EventCountVerifier"}
    )
    report_path = tmp_path / "report.md"
    report_path.write_text("<code>x = 1</code>\n", encoding="utf-8")

    assert main(["list-verifiers"]) == 0
    assert "event-count" in capsys.readouterr().out.splitlines()

    assert main(["verify", str(report_path), "--verifier", "event-count"]) == 0
    assert "[pass] event-count" in capsys.readouterr().out


def test_cli_reports_a_broken_plugin_without_a_traceback(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    install_plugin(tmp_path, monkeypatch, {"broken": "countplugin:broken"})

    assert main(["list-verifiers"]) == 2
    captured = capsys.readouterr()
    assert captured.err.startswith("provedown: cannot load verifier plugin 'broken'")


def test_plugin_that_returns_a_non_verifier_names_its_entry_point(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    install_plugin(tmp_path, monkeypatch, {"dict": "countplugin:not_a_verifier"})

    with pytest.raises(PluginLoadError, match="'dict' from countplugin"):
        load_plugin_verifiers()
    assert main(["list-verifiers"]) == 2
    assert "has no verifier_id" in capsys.readouterr().err


def test_two_plugins_with_one_id_name_the_second_entry_point(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    install_plugin(
        tmp_path,
        monkeypatch,
        {
            "aaa": "countplugin:EventCountVerifier",
            "bbb": "countplugin:SecondEventCountVerifier",
        },
    )

    with pytest.raises(
        PluginLoadError, match=r"'bbb' from countplugin .*'event-count'"
    ):
        load_plugin_verifiers()


def test_entry_points_load_in_name_order(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    install_plugin(
        tmp_path,
        monkeypatch,
        {"zzz": "countplugin:SecondByName", "aaa": "countplugin:FirstByName"},
    )

    verifiers = load_plugin_verifiers()

    assert [verifier.verifier_id for verifier in verifiers] == ["first", "second"]
    assert sys.modules["countplugin"].LOADED == ["aaa", "zzz"]


def test_cli_no_plugins_skips_a_broken_plugin(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    install_plugin(tmp_path, monkeypatch, {"broken": "countplugin:broken"})
    report_path = tmp_path / "report.md"
    report_path.write_text(
        '<code>x = 1</code>\n<span class="result" data-code="x">1'
        '<span class="method"></span></span>\n',
        encoding="utf-8",
    )

    assert main(["verify", str(report_path)]) == 2
    assert "--no-plugins" in capsys.readouterr().err

    assert main(["verify", "--no-plugins", str(report_path)]) == 0
    capsys.readouterr()
    assert main(["list-verifiers", "--no-plugins"]) == 0
    assert capsys.readouterr().out.splitlines() == ["python-results", "sql-results"]


def test_cli_loads_plugins_once_for_many_files(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    install_plugin(tmp_path, monkeypatch, {"first": "countplugin:FirstByName"})
    paths = []
    for name in ("a.md", "b.md", "c.md"):
        path = tmp_path / name
        path.write_text("<code>x = 1</code>\n", encoding="utf-8")
        paths.append(str(path))

    assert main(["verify", *paths]) == 0
    assert sys.modules["countplugin"].LOADED == ["aaa"]


def test_clash_between_plugins_names_both_entry_points(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    install_plugin(
        tmp_path, monkeypatch, {"aaa": "countplugin:EventCountVerifier"}, "alpha"
    )
    install_plugin(
        tmp_path,
        monkeypatch,
        {"bbb": "countplugin:SecondEventCountVerifier"},
        "beta",
    )

    with pytest.raises(PluginLoadError) as info:
        load_plugin_verifiers()
    message = str(info.value)
    assert "'bbb' from beta" in message
    assert "already registered by 'aaa' from alpha" in message


def test_clash_with_a_builtin_says_so(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    install_plugin(tmp_path, monkeypatch, {"clash": "countplugin:ClashingVerifier"})

    with pytest.raises(PluginLoadError, match="already registered by a built-in"):
        default_registry()


def test_unknown_verifier_id_is_a_typed_error_for_library_callers() -> None:
    with pytest.raises(UnknownVerifierError, match=r"'nope'.*python-results"):
        verify_document(parse_document("<code>x = 1</code>"), verifier_ids=["nope"])


def test_cli_rejects_an_unknown_verifier_id(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    install_plugin(
        tmp_path, monkeypatch, {"event-count": "countplugin:EventCountVerifier"}
    )
    report_path = tmp_path / "report.md"
    report_path.write_text("<code>x = 1</code>\n", encoding="utf-8")

    code = main(
        ["verify", "--no-plugins", "--verifier", "event-count", str(report_path)]
    )

    assert code == 2
    err = capsys.readouterr().err
    assert "unknown verifier 'event-count'" in err
    assert "python-results, sql-results" in err


def test_verifier_that_raises_becomes_an_error_finding(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    install_plugin(tmp_path, monkeypatch, {"crashing": "countplugin:CrashingVerifier"})
    paths = []
    for name in ("a.md", "b.md"):
        path = tmp_path / name
        path.write_text(
            '<code>x = 1</code>\n<span class="result" data-code="x">1'
            '<span class="method"></span></span>\n',
            encoding="utf-8",
        )
        paths.append(str(path))

    report = verify_document(
        parse_document(Path(paths[0]).read_text(encoding="utf-8")),
        registry=default_registry(),
    )

    assert not report.ok
    assert report.count(Status.PASS) == 1
    [error] = [f for f in report.findings if f.status == Status.ERROR]
    assert error.verifier_id == "crashing"
    assert "source cache is corrupt" in error.message

    assert main(["verify", *paths]) == 1
    out = capsys.readouterr().out
    assert out.count("[pass] python-results") == 2
    assert out.count("[error] crashing") == 2


def test_verifier_that_yields_a_non_finding_keeps_earlier_findings(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    install_plugin(tmp_path, monkeypatch, {"dicts": "countplugin:DictVerifier"})
    report_path = tmp_path / "report.md"
    report_path.write_text("<code>x = 1</code>\n", encoding="utf-8")

    report = verify_document(
        parse_document("<code>x = 1</code>"),
        registry=default_registry(),
        verifier_ids=["dicts"],
    )

    first = report.findings[0]
    assert (first.status, first.message) == (Status.PASS, "first is fine")
    error = report.findings[1]
    assert error.status == Status.ERROR
    assert error.verifier_id == "dicts"
    assert error.message.startswith("verifier yielded {'status': 'pass'}")
    assert "which is not a Finding" in error.message
    assert error.evidence == {"yielded": "{'status': 'pass'}"}

    assert main(["verify", str(report_path), "--verifier", "dicts"]) == 1
    assert "[error] dicts" in capsys.readouterr().out


def test_unknown_verifier_id_raises_even_for_a_document_with_parser_errors() -> None:
    document = parse_document('<code use=""/>')
    assert document.diagnostics

    with pytest.raises(UnknownVerifierError):
        verify_document(document, verifier_ids=["nope"])


def test_broken_plugin_raises_whether_or_not_ids_are_given(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    install_plugin(tmp_path, monkeypatch, {"broken": "countplugin:broken"})
    document = parse_document('<code use=""/>')
    assert document.diagnostics

    with pytest.raises(PluginLoadError):
        verify_document(document)
    with pytest.raises(PluginLoadError):
        verify_document(document, verifier_ids=["python-results"])


def test_registry_get_raises_the_typed_error() -> None:
    with pytest.raises(UnknownVerifierError, match="available: python-results"):
        default_registry(plugins=False).get("nope")


def test_cli_reports_an_unknown_id_before_the_sandbox_guard(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    report_path = tmp_path / "report.md"
    report_path.write_text("<code>x = 1</code>\n", encoding="utf-8")

    code = main(
        [
            "verify",
            "--no-plugins",
            "--sandbox",
            "uv",
            "--verifier",
            "pyton-results",
            str(report_path),
        ]
    )

    assert code == 2
    assert "unknown verifier 'pyton-results'" in capsys.readouterr().err


def test_finding_status_may_be_the_plain_string_the_docs_describe() -> None:
    from provedown import Finding, SourceLocation

    finding = Finding(
        verifier_id="x",
        status="fail",  # type: ignore[arg-type]
        location=SourceLocation(path=None, line=1, column=1),
        message="m",
    )

    assert finding.status is Status.FAIL
    assert finding.to_dict()["status"] == "fail"


def test_findings_with_bad_fields_become_attributed_errors(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    install_plugin(
        tmp_path,
        monkeypatch,
        {
            "bad-location": "countplugin:StringLocationVerifier",
            "bad-status": "countplugin:BadStatusVerifier",
            "huge": "countplugin:HugeYieldVerifier",
            "strings": "countplugin:StringStatusVerifier",
        },
    )

    report = verify_document(parse_document("text"), registry=default_registry())
    by_id = {finding.verifier_id: finding for finding in report.findings}

    assert by_id["strings"].status is Status.PASS
    assert by_id["bad-status"].status is Status.ERROR
    assert "'passed' is not a valid Status" in by_id["bad-status"].message
    assert by_id["bad-location"].status is Status.ERROR
    assert "location" in by_id["bad-location"].message
    assert by_id["huge"].status is Status.ERROR
    assert len(by_id["huge"].message) < 300
    assert len(by_id["huge"].evidence["yielded"]) < 300

    report_path = tmp_path / "report.md"
    report_path.write_text("text\n", encoding="utf-8")
    assert main(["verify", str(report_path), "--format", "json"]) == 1
    assert '"verifier_id": "bad-status"' in capsys.readouterr().out


def test_evidence_must_be_a_json_serializable_mapping(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    install_plugin(
        tmp_path,
        monkeypatch,
        {
            "list-evidence": "countplugin:ListEvidenceVerifier",
            "path-evidence": "countplugin:PathEvidenceVerifier",
        },
    )

    report = verify_document(parse_document("text"), registry=default_registry())
    by_id = {finding.verifier_id: finding for finding in report.findings}

    for verifier_id in ("list-evidence", "path-evidence"):
        assert by_id[verifier_id].status is Status.ERROR
        assert "evidence must be" in by_id[verifier_id].message

    report_path = tmp_path / "report.md"
    report_path.write_text("text\n", encoding="utf-8")
    assert main(["verify", str(report_path), "--format", "json"]) == 1
    assert '"verifier_id": "path-evidence"' in capsys.readouterr().out


def test_wrong_type_yield_closes_the_verifier_generator(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    install_plugin(tmp_path, monkeypatch, {"cleanup": "countplugin:CleanupVerifier"})

    report = verify_document(parse_document("text"), registry=default_registry())

    assert [f.verifier_id for f in report.findings] == ["cleanup"]
    assert sys.modules["countplugin"].CLOSED == [True]


def test_wrong_type_yield_with_a_broken_repr_is_still_reported(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    install_plugin(tmp_path, monkeypatch, {"bad-repr": "countplugin:BadReprVerifier"})

    report = verify_document(parse_document("text"), registry=default_registry())

    [finding] = report.findings
    assert finding.status is Status.ERROR
    assert finding.message.startswith("verifier yielded <Unprintable")
    assert "repr exploded" not in finding.message


def test_finding_text_fields_must_be_strings() -> None:
    from datetime import datetime

    from provedown import Finding, SourceLocation

    location = SourceLocation(path=None, line=1, column=1)
    for field, value in (
        ("verifier_id", 1),
        ("message", Path("x")),
        ("expected", Path("refs/paper.md")),
        ("actual", datetime(2026, 1, 1)),
    ):
        kwargs = {"verifier_id": "x", "status": "pass", "location": location}
        kwargs["message"] = "m"
        kwargs[field] = value
        with pytest.raises(TypeError, match=f"Finding {field} must be a str"):
            Finding(**kwargs)  # type: ignore[arg-type]

    finding = Finding(
        verifier_id="x", status=Status.PASS, location=location, message="m", actual=None
    )
    assert finding.actual is None


def test_finding_evidence_must_be_a_mapping_and_nan_is_rejected() -> None:
    from provedown import Finding, SourceLocation

    location = SourceLocation(path=None, line=1, column=1)
    for evidence in (None, {"similarity": float("nan")}):
        with pytest.raises(TypeError, match="JSON-serializable mapping"):
            Finding(
                verifier_id="x",
                status=Status.PASS,
                location=location,
                message="m",
                evidence=evidence,  # type: ignore[arg-type]
            )


def test_load_error_for_a_non_verifier_with_a_broken_repr(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    install_plugin(tmp_path, monkeypatch, {"bad": "countplugin:unprintable_factory"})

    with pytest.raises(PluginLoadError, match="'bad' from countplugin"):
        load_plugin_verifiers()


def test_raise_with_an_unprintable_or_huge_exception_is_attributed(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    install_plugin(
        tmp_path,
        monkeypatch,
        {
            "huge-error": "countplugin:HugeErrorVerifier",
            "unstringable": "countplugin:UnstringableRaiseVerifier",
        },
    )

    report = verify_document(parse_document("text"), registry=default_registry())

    unstringable = [f for f in report.findings if f.verifier_id == "unstringable"]
    assert [f.status for f in unstringable] == [Status.PASS, Status.ERROR]
    assert unstringable[1].message == (
        "verifier raised _UnstringableError: <unprintable _UnstringableError>"
    )
    [huge] = [f for f in report.findings if f.verifier_id == "huge-error"]
    assert huge.status is Status.ERROR
    assert len(huge.message) < 300
    traceback_text = huge.evidence["traceback"]
    assert len(traceback_text) <= 4000
    # The frames survive a huge message, which is kept only in short form.
    assert traceback_text.startswith("Traceback (most recent call last):")
    assert "in verify" in traceback_text
    assert "x" * 500 not in traceback_text


def test_empty_verifier_ids_is_an_error_not_an_empty_ok_report() -> None:
    with pytest.raises(ValueError, match="no verifier ids"):
        verify_document(parse_document("<code>x = 1</code>"), verifier_ids=[])


def test_register_rejects_a_verifier_without_a_string_id_or_verify() -> None:
    from provedown import VerifierRegistry

    class NoId:
        verifier_id = 1

        def verify(self, document, context):  # type: ignore[no-untyped-def]
            return []

    class NoVerify:
        verifier_id = "no-verify"

    registry = VerifierRegistry()
    with pytest.raises(TypeError, match="verifier_id"):
        registry.register(NoId())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match=r"verify\(\) method"):
        registry.register(NoVerify())  # type: ignore[arg-type]
    assert registry.names() == []


def test_registry_verify_rejects_empty_ids_and_dedupes_repeats() -> None:
    registry = default_registry(plugins=False)
    document = parse_document(
        '<code>x = 1</code> <span class="result" data-code="x">1</span>'
    )

    with pytest.raises(ValueError, match="no verifier ids"):
        registry.verify(document, verifier_ids=[])

    report = registry.verify(
        document, verifier_ids=["python-results", "python-results"]
    )
    assert report.count(Status.PASS) == 1


def test_raising_verifier_traceback_keeps_the_exception_chain(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    install_plugin(
        tmp_path, monkeypatch, {"chained": "countplugin:ChainedErrorVerifier"}
    )

    report = verify_document(parse_document("text"), registry=default_registry())

    [finding] = report.findings
    traceback_text = finding.evidence["traceback"]
    assert "ConnectionError: dns lookup failed for example.org" in traceback_text
    assert "direct cause of the following exception" in traceback_text
    assert "countplugin.SourceFetchError: could not fetch source" in traceback_text


def test_load_error_message_is_guarded_bounded_and_typed(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    install_plugin(
        tmp_path, monkeypatch, {"unstringable": "countplugin:unstringable_broken"}
    )

    with pytest.raises(PluginLoadError) as info:
        load_plugin_verifiers()
    assert str(info.value).endswith(
        "_UnstringableLoadError: <unprintable _UnstringableLoadError>"
    )
    assert main(["list-verifiers"]) == 2
    assert "--no-plugins" in capsys.readouterr().err


def test_load_error_for_a_huge_message_keeps_the_hint_visible(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    install_plugin(tmp_path, monkeypatch, {"huge": "countplugin:huge_broken"})

    assert main(["list-verifiers"]) == 2
    err = capsys.readouterr().err
    assert "ValueError: schema" in err
    assert len(err) < 600
    assert err.rstrip().endswith(
        "(use --no-plugins to run only the built-in verifiers)"
    )


def test_verifier_id_that_raises_is_a_load_error_and_a_register_error(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    from provedown import VerifierRegistry

    install_plugin(
        tmp_path, monkeypatch, {"raising-id": "countplugin:RaisingIdVerifier"}
    )

    with pytest.raises(PluginLoadError) as info:
        load_plugin_verifiers()
    assert str(info.value).endswith(
        ", which raised RuntimeError when its verifier_id was read"
    )

    verifier = sys.modules["countplugin"].RaisingIdVerifier()
    with pytest.raises(
        TypeError, match=r": it raised RuntimeError when its verifier_id was read$"
    ):
        VerifierRegistry().register(verifier)
    other = sys.modules["countplugin"].RaisingVerifyVerifier()
    with pytest.raises(TypeError, match="when its verify attribute was read"):
        VerifierRegistry().register(other)


def test_a_plugin_id_is_read_once_from_load_to_registration(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    install_plugin(
        tmp_path, monkeypatch, {"shifting": "countplugin:ShiftingIdVerifier"}
    )

    registry = default_registry()

    # Registered under the id that was checked, so it cannot take a built-in's.
    assert registry.names() == ["fresh-id", "python-results", "sql-results"]
    assert type(registry.get("python-results")).__name__ == "PythonResultVerifier"


def test_shape_errors_keep_the_plugin_exception_and_name_attribute_errors(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    from provedown import VerifierRegistry

    install_plugin(
        tmp_path, monkeypatch, {"raising-id": "countplugin:RaisingIdVerifier"}
    )

    with pytest.raises(PluginLoadError) as loaded:
        load_plugin_verifiers()
    # The plugin's own exception stays chained for library callers to inspect.
    assert isinstance(loaded.value.__cause__, RuntimeError)
    assert str(loaded.value.__cause__) == "lazy import failed"

    module = sys.modules["countplugin"]
    with pytest.raises(TypeError) as registered:
        VerifierRegistry().register(module.RaisingIdVerifier())
    assert isinstance(registered.value.__cause__, RuntimeError)

    # An AttributeError raised inside a property is not a missing attribute.
    with pytest.raises(
        TypeError, match="it raised AttributeError when its verifier_id was read"
    ):
        VerifierRegistry().register(module.AttributeErrorIdVerifier())


def test_plain_shape_errors_carry_no_internal_chain_and_unset_slots_are_absent(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    from provedown import VerifierRegistry

    install_plugin(tmp_path, monkeypatch, {"dict": "countplugin:not_a_verifier"})

    with pytest.raises(PluginLoadError) as loaded:
        load_plugin_verifiers()
    assert loaded.value.__cause__ is None

    slotted = importlib.import_module("countplugin").UnsetSlotVerifier()
    with pytest.raises(TypeError, match=r": it has no verifier_id$") as registered:
        VerifierRegistry().register(slotted)
    assert registered.value.__cause__ is None


def test_finding_evidence_is_a_deep_copy_with_string_keys() -> None:
    from provedown import Finding, SourceLocation

    location = SourceLocation(path=None, line=1, column=1)
    rows: list[object] = ["first"]
    finding = Finding(
        verifier_id="x",
        status=Status.PASS,
        location=location,
        message="m",
        evidence={"rows": rows, "span": (1, 2)},
    )
    # A plugin reusing its buffer cannot change or break the finding afterwards.
    rows.append(Path("later"))

    assert finding.evidence == {"rows": ["first"], "span": [1, 2]}
    assert finding.to_dict()["evidence"] == {"rows": ["first"], "span": [1, 2]}
    json.dumps(finding.to_dict())

    with pytest.raises(TypeError, match="keys must be strings, not int"):
        Finding(
            verifier_id="x",
            status=Status.PASS,
            location=location,
            message="m",
            evidence={1: "a"},  # type: ignore[dict-item]
        )


def test_finding_location_contents_are_checked_when_the_finding_is_built() -> None:
    from provedown import Finding, SourceLocation

    class BrokenPath(type(Path())):  # type: ignore[misc]
        def __str__(self) -> str:
            raise RuntimeError("no")

    for location, match in (
        (SourceLocation(path="notes.md", line=1, column=1), "path must be a Path"),  # type: ignore[arg-type]
        (SourceLocation(path=None, line=None, column=1), "line must be an int"),  # type: ignore[arg-type]
        (SourceLocation(path=None, line=1, column=2.5), "column must be an int"),  # type: ignore[arg-type]
        (SourceLocation(path=None, line=True, column=1), "line must be an int"),
        (
            SourceLocation(path=BrokenPath("x"), line=1, column=1),
            "could not be rendered",
        ),
    ):
        with pytest.raises(TypeError, match=match):
            Finding(verifier_id="x", status=Status.PASS, location=location, message="m")


def test_finding_to_dict_evidence_is_a_fresh_copy() -> None:
    from provedown import Finding, SourceLocation

    finding = Finding(
        verifier_id="x",
        status=Status.PASS,
        location=SourceLocation(path=None, line=1, column=1),
        message="m",
        evidence={"rows": ["a"]},
    )
    finding.to_dict()["evidence"]["rows"].append("b")

    assert finding.evidence == {"rows": ["a"]}


def test_a_string_document_path_from_a_library_caller_still_verifies() -> None:
    document = parse_document(
        "<pre><code>x = 2</code></pre>"
        '<p><span class="result" data-code="x">2</span></p>',
        path="notes.md",  # type: ignore[arg-type]
    )

    assert document.path == Path("notes.md")
    report = verify_document(document)
    assert report.ok, [finding.message for finding in report.findings]
    assert {
        finding.to_dict()["location"].split(":")[0] for finding in report.findings
    } == {"notes.md"}
