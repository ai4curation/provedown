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
