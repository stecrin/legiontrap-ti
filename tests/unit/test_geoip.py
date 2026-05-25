"""Unit tests for app/utils/geoip.py."""

import pytest

import app.utils.geoip as geoip_module
from app.utils.geoip import enrich_ip, reset_reader_for_testing

MMDB_AVAILABLE = geoip_module.CITY_DB_PATH.exists()

_EXPECTED_KEYS = {"country_code", "country_name", "city"}


@pytest.fixture(autouse=True)
def reset_reader():
    reset_reader_for_testing()
    yield
    reset_reader_for_testing()


def test_enrich_ip_missing_mmdb_returns_all_none(monkeypatch, tmp_path):
    monkeypatch.setattr(geoip_module, "CITY_DB_PATH", tmp_path / "absent.mmdb")
    result = enrich_ip("1.2.3.4")
    assert result == {"country_code": None, "country_name": None, "city": None}


def test_enrich_ip_returns_dict_with_expected_keys(monkeypatch, tmp_path):
    monkeypatch.setattr(geoip_module, "CITY_DB_PATH", tmp_path / "absent.mmdb")
    result = enrich_ip("1.2.3.4")
    assert set(result.keys()) == _EXPECTED_KEYS


def test_enrich_ip_never_raises_on_invalid_ip_strings(monkeypatch, tmp_path):
    monkeypatch.setattr(geoip_module, "CITY_DB_PATH", tmp_path / "absent.mmdb")
    for bad in ("", "not-an-ip", "999.999.999.999", "::1", "0.0.0.0"):
        result = enrich_ip(bad)
        assert set(result.keys()) == _EXPECTED_KEYS


@pytest.mark.skipif(not MMDB_AVAILABLE, reason="GeoLite2-City.mmdb not provisioned")
def test_enrich_ip_returns_country_for_public_ip():
    result = enrich_ip("8.8.8.8")
    assert result["country_code"] is not None
    assert len(result["country_code"]) == 2
