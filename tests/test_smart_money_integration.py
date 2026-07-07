"""Tests for Smart Money agent integration into the pipeline."""

import os
import sys

import pytest

# Add opencode_pipeline to path so we can import orchestrator
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "opencode_pipeline"))


class TestPipelineStages:
    """Verify Smart Money stages are correctly positioned in PIPELINE_STAGES."""

    def test_smart_money_4h_exists(self):
        from orchestrator import PIPELINE_STAGES

        roles = [s[0] for s in PIPELINE_STAGES]
        assert "smart_money_4h" in roles

    def test_smart_money_15m_exists(self):
        from orchestrator import PIPELINE_STAGES

        roles = [s[0] for s in PIPELINE_STAGES]
        assert "smart_money_15m" in roles

    def test_total_stages_14(self):
        from orchestrator import PIPELINE_STAGES

        assert len(PIPELINE_STAGES) == 14

    def test_smart_money_after_fundamentals(self):
        from orchestrator import PIPELINE_STAGES

        roles = [s[0] for s in PIPELINE_STAGES]
        fi_idx = roles.index("fundamentals")
        sm4h_idx = roles.index("smart_money_4h")
        sm15m_idx = roles.index("smart_money_15m")
        assert fi_idx < sm4h_idx < sm15m_idx

    def test_smart_money_before_researchers(self):
        from orchestrator import PIPELINE_STAGES

        roles = [s[0] for s in PIPELINE_STAGES]
        sm15m_idx = roles.index("smart_money_15m")
        bull_idx = roles.index("bull_researcher")
        assert sm15m_idx < bull_idx

    def test_smart_money_prompt_files_exist(self):
        prompts_dir = os.path.join(
            os.path.dirname(__file__), "..", "opencode_pipeline", "prompts"
        )
        assert os.path.exists(os.path.join(prompts_dir, "smart_money_15m.md"))
        assert os.path.exists(os.path.join(prompts_dir, "smart_money_4h.md"))

    def test_smart_money_output_files(self):
        from orchestrator import PIPELINE_STAGES

        outputs = {s[0]: s[2] for s in PIPELINE_STAGES}
        assert outputs["smart_money_4h"] == "reports/smart_money_4h.md"
        assert outputs["smart_money_15m"] == "reports/smart_money_15m.md"


class TestSmartMoneyPrompts:
    """Verify Smart Money prompts have required content."""

    def _read_prompt(self, name):
        path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "opencode_pipeline",
            "prompts",
            f"{name}.md",
        )
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_15m_has_current_price(self):
        content = self._read_prompt("smart_money_15m")
        assert "{current_price}" in content

    def test_15m_has_instrument_context(self):
        content = self._read_prompt("smart_money_15m")
        assert "{instrument_context}" in content

    def test_15m_has_output_format(self):
        content = self._read_prompt("smart_money_15m")
        assert "STRUCTURE:" in content
        assert "ENTRY_SETUP:" in content
        assert "VOLUME_PROFILE:" in content

    def test_15m_writes_correct_file(self):
        content = self._read_prompt("smart_money_15m")
        assert "reports/smart_money_15m.md" in content

    def test_4h_has_current_price(self):
        content = self._read_prompt("smart_money_4h")
        assert "{current_price}" in content

    def test_4h_has_instrument_context(self):
        content = self._read_prompt("smart_money_4h")
        assert "{instrument_context}" in content

    def test_4h_has_output_format(self):
        content = self._read_prompt("smart_money_4h")
        assert "HTF_STRUCTURE:" in content
        assert "KEY_LEVELS:" in content
        assert "TRADE_PLAN:" in content

    def test_4h_writes_correct_file(self):
        content = self._read_prompt("smart_money_4h")
        assert "reports/smart_money_4h.md" in content


class TestPromptsReferenceSmartMoney:
    """Verify downstream prompts reference Smart Money reports."""

    def _read_prompt(self, name):
        path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "opencode_pipeline",
            "prompts",
            f"{name}.md",
        )
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_research_manager_reads_sm(self):
        content = self._read_prompt("research_manager")
        assert "smart_money_4h.md" in content
        assert "smart_money_15m.md" in content

    def test_portfolio_manager_reads_sm(self):
        content = self._read_prompt("portfolio_manager")
        assert "smart_money_4h.md" in content
        assert "smart_money_15m.md" in content

    def test_trader_reads_sm(self):
        content = self._read_prompt("trader")
        assert "smart_money_4h.md" in content
        assert "smart_money_15m.md" in content

    def test_bull_researcher_reads_sm(self):
        content = self._read_prompt("bull_researcher")
        assert "smart_money_4h.md" in content

    def test_bear_researcher_reads_sm(self):
        content = self._read_prompt("bear_researcher")
        assert "smart_money_4h.md" in content

    def test_risk_aggressive_reads_sm(self):
        content = self._read_prompt("risk_aggressive")
        assert "smart_money_15m.md" in content

    def test_risk_conservative_reads_sm(self):
        content = self._read_prompt("risk_conservative")
        assert "smart_money_15m.md" in content

    def test_risk_neutral_reads_sm(self):
        content = self._read_prompt("risk_neutral")
        assert "smart_money_15m.md" in content
