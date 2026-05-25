"""Unit tests for app/utils/asn.py."""

import pytest

import app.utils.asn as asn_module
from app.utils.asn import enrich_asn, reset_asn_reader_for_testing

ASN_DB_AVAILABLE = asn_module.ASN_DB_PATH.exists()

_EXPECTED_KEYS = {"asn", "asn_org"}


@pytest.fixture(autouse=True)
def reset_reader():
    reset_asn_reader_for_testing()
    yield
    reset_asn_reader_for_testing()


def test_enrich_asn_missing_mmdb_returns_all_none(monkeypatch, tmp_path):
    monkeypatch.setattr(asn_module, "ASN_DB_PATH", tmp_path / "absent.mmdb")
    result = enrich_asn("1.2.3.4")
    assert result == {"asn": None, "asn_org": None}


def test_enrich_asn_returns_dict_with_expected_keys(monkeypatch, tmp_path):
    monkeypatch.setattr(asn_module, "ASN_DB_PATH", tmp_path / "absent.mmdb")
    result = enrich_asn("1.2.3.4")
    assert set(result.keys()) == _EXPECTED_KEYS


def test_enrich_asn_never_raises_on_invalid_ip_strings(monkeypatch, tmp_path):
    monkeypatch.setattr(asn_module, "ASN_DB_PATH", tmp_path / "absent.mmdb")
    for bad in ("", "not-an-ip", "999.999.999.999", "::1", "0.0.0.0"):
        result = enrich_asn(bad)
        assert set(result.keys()) == _EXPECTED_KEYS


@pytest.mark.skipif(not ASN_DB_AVAILABLE, reason="GeoLite2-ASN.mmdb not provisioned")
def test_enrich_asn_returns_asn_number_for_public_ip():
    result = enrich_asn("8.8.8.8")
    assert result["asn"] is not None
    assert isinstance(result["asn"], int)
    assert result["asn_org"] is not None
