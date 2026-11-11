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

PLUGIN_MODULE = '''
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
'''


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

    with pytest.raises(PluginLoadError, match="'python-results'"):
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
