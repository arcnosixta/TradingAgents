"""Tests for entry_validator v2: consistency, lot size, ATR parsing."""

import os
import tempfile

import pytest

from tradingagents.agents.utils.entry_validator import (
    calculate_lot_size,
    parse_atr_from_indicators,
    validate_consistency,
    validate_entry_levels,
)


# ── validate_consistency ──────────────────────────────────────────────

class TestValidateConsistency:
    def test_no_change_when_close(self):
        entry, warnings = validate_consistency(4200.0, 4205.0, max_diff=20)
        assert entry == 4205.0
        assert warnings == []

    def test_no_change_when_equal(self):
        entry, warnings = validate_consistency(4200.0, 4200.0)
        assert entry == 4200.0
        assert warnings == []

    def test_correction_when_far(self):
        entry, warnings = validate_consistency(4200.0, 4255.0, max_diff=20)
        assert entry == 4200.0
        assert len(warnings) == 1
        assert "55 pts" in warnings[0]

    def test_none_trader(self):
        entry, warnings = validate_consistency(None, 4200.0)
        assert entry == 4200.0
        assert warnings == []

    def test_none_pm(self):
        entry, warnings = validate_consistency(4200.0, None)
        assert entry is None
        assert warnings == []


# ── calculate_lot_size ───────────────────────────────────────────────

class TestCalculateLotSize:
    def test_basic_gold(self):
        lot = calculate_lot_size(4200, 4150, 10000, 0.01, 1.0)
        # risk = $100, distance = 50pts, pip_value = $1 → 100/50 = 2.0 → clamped to 1.0
        assert lot == 1.0

    def test_basic_gold_actual(self):
        lot = calculate_lot_size(4200, 4150, 10000, 0.01, 1.0)
        # risk = 100, distance = 50, pip_value = 1 → 100/50 = 2.0 → clamped to 1.0
        assert lot == 1.0

    def test_small_stop(self):
        lot = calculate_lot_size(4200, 4190, 10000, 0.01, 1.0)
        # risk = 100, distance = 10 → 100/10 = 10.0 → clamped to 1.0
        assert lot == 1.0

    def test_large_stop(self):
        lot = calculate_lot_size(4200, 4100, 10000, 0.01, 1.0)
        # risk = 100, distance = 100 → 100/100 = 1.0
        assert lot == 1.0

    def test_zero_stop(self):
        lot = calculate_lot_size(4200, 4200, 10000, 0.01, 1.0)
        assert lot == 0.01  # minimum

    def test_2pct_risk(self):
        lot = calculate_lot_size(4200, 4150, 10000, 0.02, 1.0)
        # risk = 200, distance = 50 → 200/50 = 4.0 → clamped to 1.0
        assert lot == 1.0

    def test_forex_pip_value(self):
        lot = calculate_lot_size(1.1000, 1.0950, 10000, 0.01, 10.0)
        # risk = 100, distance = 0.0050, pip_value = 10 → 100/(0.005*10) = 2000 → clamped
        assert lot == 1.0


# ── parse_atr_from_indicators ────────────────────────────────────────

class TestParseAtrFromIndicators:
    def test_parse_atr_with_period(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("## Technical Indicators\n\nATR (14): 93.21\nRSI: 55.3\n")
            f.flush()
            atr = parse_atr_from_indicators(f.name)
        os.unlink(f.name)
        assert atr == 93.21

    def test_parse_atr_without_period(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("ATR: 45.5\n")
            f.flush()
            atr = parse_atr_from_indicators(f.name)
        os.unlink(f.name)
        assert atr == 45.5

    def test_parse_atr_bold(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("**ATR**: 120.0\n")
            f.flush()
            atr = parse_atr_from_indicators(f.name)
        os.unlink(f.name)
        assert atr == 120.0

    def test_no_atr(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("RSI: 55.3\nMACD: 12.5\n")
            f.flush()
            atr = parse_atr_from_indicators(f.name)
        os.unlink(f.name)
        assert atr is None

    def test_missing_file(self):
        assert parse_atr_from_indicators("/nonexistent/file.md") is None


# ── ATR-dependent stop validation ────────────────────────────────────

class TestAtrStopValidation:
    def test_atr_clamps_wide_stop(self):
        """Stop 300pts with ATR=93 should be clamped to ~140 (1.5*ATR)."""
        result = validate_entry_levels(
            entry_price=4200,
            stop_loss=3900,  # 300pts — way too wide
            take_profit=4400,
            current_price=4200,
            action="Buy",
            atr=93.0,
        )
        assert not result.is_valid
        stop_dist = abs(result.stop_loss - 4200)
        assert stop_dist <= 140  # 1.5 * 93 = 139.5

    def test_atr_clamps_tight_stop(self):
        """Stop 10pts with ATR=93 should be widened to ~47 (0.5*ATR)."""
        result = validate_entry_levels(
            entry_price=4200,
            stop_loss=4190,  # 10pts — too tight
            take_profit=4250,
            current_price=4200,
            action="Buy",
            atr=93.0,
        )
        assert not result.is_valid
        stop_dist = abs(result.stop_loss - 4200)
        assert stop_dist >= 46  # 0.5 * 93 = 46.5 → round(46.5) = 46 (banker's rounding)

    def test_atr_normal_stop_passes(self):
        """Stop 50pts with ATR=93 should pass (between 47 and 140)."""
        result = validate_entry_levels(
            entry_price=4200,
            stop_loss=4150,  # 50pts
            take_profit=4300,
            current_price=4200,
            action="Buy",
            atr=93.0,
        )
        assert result.is_valid

    def test_no_atr_uses_default_bounds(self):
        """Without ATR, default 20-100 bounds apply."""
        result = validate_entry_levels(
            entry_price=4200,
            stop_loss=4150,  # 50pts
            take_profit=4300,
            current_price=4200,
            action="Buy",
            atr=None,
        )
        assert result.is_valid

    def test_sell_stop_atr(self):
        """Sell direction: stop above entry, ATR-clamped."""
        result = validate_entry_levels(
            entry_price=4200,
            stop_loss=4500,  # 300pts above — too wide
            take_profit=4000,
            current_price=4200,
            action="Sell",
            atr=93.0,
        )
        assert not result.is_valid
        stop_dist = abs(result.stop_loss - 4200)
        assert stop_dist <= 140


# ── Existing validate_entry_levels (regression) ──────────────────────

class TestValidateEntryLevelsRegression:
    def test_entry_within_30pts(self):
        result = validate_entry_levels(4200, 4150, 4260, 4187.30, "Buy")
        assert result.is_valid

    def test_entry_too_far(self):
        result = validate_entry_levels(4400, 4350, 4500, 4187.30, "Buy")
        assert not result.is_valid
        assert result.entry_price == 4187.30

    def test_stop_too_large(self):
        result = validate_entry_levels(4200, 4500, 4300, 4187.30, "Sell")
        assert not result.is_valid
        assert abs(result.stop_loss - 4200) <= 100

    def test_hold_always_valid(self):
        result = validate_entry_levels(None, None, None, 4187.30, "Hold")
        assert result.is_valid

    def test_tp_warning_low_rr(self):
        result = validate_entry_levels(4200, 4150, 4220, 4200, "Buy")
        assert result.is_valid  # TP warning, not a fix
        assert any("R:R" in f for f in result.fixes)
