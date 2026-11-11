import sys
from pathlib import Path

import pytest
from pytest import CaptureFixture, MonkeyPatch

from provedown import (
    VERIFIER_ENTRY_POINT_GROUP,
    PluginLoadError,
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
    monkeypatch.delitem(sys.modules, "countplugin", raising=False)


def test_no_plugins_installed_leaves_the_builtin_verifiers() -> None:
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
