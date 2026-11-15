import importlib
import re

import pytest

from common import config


def test_project_code_regex():
    assert config.is_project_code("FVE-2024-03")
    for bad in ("FVE-24-3", "fve-2024-03", "FVE-2024-003", "FVE-2024-03 ", "FVE-2024-03\n", ""):
        assert not config.is_project_code(bad), bad
    assert config.PROJECT_CODE_RE == r"^FVE-\d{4}-\d{2}$"


def test_categories_are_the_10_codes():
    assert list(config.CATEGORIES) == [
        "PANELS",
        "INVERTERS",
        "BATTERIES",
        "STRUCTURES",
        "CABLES",
        "EARTHWORKS",
        "GRID",
        "DESIGN",
        "SURVEY",
        "OTHER",
    ]
    groups = {code: group for code, (_, group) in config.CATEGORIES.items()}
    assert {c for c, g in groups.items() if g == "technology"} == {"PANELS", "INVERTERS", "BATTERIES"}
    assert {c for c, g in groups.items() if g == "construction"} == {
        "STRUCTURES",
        "CABLES",
        "EARTHWORKS",
        "GRID",
    }
    assert {c for c, g in groups.items() if g == "services"} == {"DESIGN", "SURVEY", "OTHER"}
    assert config.CATEGORIES["EARTHWORKS"] == ("Earthworks", "construction")


def test_banks_have_codes_and_formats():
    assert list(config.BANKS) == ["RB", "UCB", "KB", "CS"]
    assert {code: b.bank_code for code, b in config.BANKS.items()} == {
        "RB": "5500",
        "UCB": "2700",
        "KB": "0100",
        "CS": "0800",
    }
    assert {code: b.format for code, b in config.BANKS.items()} == {
        "RB": "GPC",
        "UCB": "GPC",
        "KB": "GPC",
        "CS": "STA",
    }
    assert config.BANKS["RB"].frequency == "daily"
    assert {b.frequency for code, b in config.BANKS.items() if code != "RB"} == {"monthly"}
    for bank in config.BANKS.values():
        assert re.fullmatch(r"[1-9]\d*", bank.account), bank
        assert re.fullmatch(r"\d{4}", bank.bank_code), bank


def test_raw_sources_cover_every_source():
    assert set(config.RAW_SOURCES) == {
        "master",
        "budgets",
        "isdoc",
        "invoice_pdf",
        "accounting",
        "bank_gpc",
        "bank_sta",
        "bank_txt",
        "kpc",
        "photos",
        "video",
        "docs",
    }
    assert {s for s, r in config.RAW_SOURCES.items() if r.keep_project} == {"video", "docs"}


def test_dataset_switch(monkeypatch):
    try:
        monkeypatch.setenv("FVE_DATASET", "x10")
        x10 = importlib.reload(config)
        assert x10.DATASET == "x10"
        assert x10.CLEAN_DB == "fve_clean_x10"
        assert x10.DW_DB == "fve_dw_x10"
        assert x10.LAKE_ROOT == "/bench/x10/lake"
        assert x10.LAKE_CLEAN == "/bench/x10/lake/clean"
        assert x10.SOURCES_DIR.name == "sources_x10"
        assert x10.OUT_DIR.name == "out_x10"

        monkeypatch.setenv("FVE_DATASET", "x100")
        with pytest.raises(ValueError, match="FVE_DATASET"):
            importlib.reload(config)

        monkeypatch.delenv("FVE_DATASET")
        main = importlib.reload(config)
        assert (main.DATASET, main.CLEAN_DB, main.LAKE_ROOT) == ("main", "fve_clean", "/lake")
        assert main.SOURCES_DIR.name == "sources"
        # Both datasets' folders are known whichever is active (generators.scale).
        assert [d.name for d in main.dataset_dirs("x10")] == ["sources_x10", "out_x10"]
        assert main.dataset_dirs("main") == (main.SOURCES_DIR, main.OUT_DIR)
        with pytest.raises(ValueError):
            main.dataset_dirs("x100")
    finally:
        monkeypatch.delenv("FVE_DATASET", raising=False)
        importlib.reload(config)
