"""Fixture existence checks for local folder demo seed artifacts."""

from pathlib import Path


REQUIRED_FIXTURE_PATHS = [
    Path("ccd/batch_1100.ach"),
    Path("settlement/batch_1100_settlement.dat"),
    Path("scheme-reject/batch_1100_reject.json"),
    Path("returns/batch_1100_return.ach"),
]


def test_local_demo_batch_1100_fixtures_exist() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    fixture_root = repo_root / "demo-data" / "local-folder-demo" / "batch_1100"

    missing = [
        str(relative_path)
        for relative_path in REQUIRED_FIXTURE_PATHS
        if not (fixture_root / relative_path).is_file()
    ]

    assert not missing, (
        "Missing local demo fixture files under "
        f"{fixture_root}: {', '.join(missing)}"
    )
