import sys

import pytest

from src.digest import cli


def test_cli_demo_and_maintenance(test_settings, monkeypatch, capsys):
    monkeypatch.setattr(cli, "Settings", lambda: test_settings)
    for command, expected in [
        ("demo", "Your daily email digest"),
        ("cleanup", "Deleted"),
        ("purge", "purged"),
    ]:
        monkeypatch.setattr(sys, "argv", ["digest", command])
        cli.main()
        assert expected in capsys.readouterr().out


def test_cli_failures_do_not_leak_input(test_settings, monkeypatch, capsys):
    monkeypatch.setattr(cli, "Settings", lambda: test_settings)
    monkeypatch.setattr(sys, "argv", ["digest", "delivery-status", "--id", "PRIVATE_INPUT"])
    with pytest.raises(SystemExit):
        cli.main()
    assert "PRIVATE_INPUT" not in capsys.readouterr().err
