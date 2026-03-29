"""Group: Orchestrator

Tests for main.py — SelfModel (parsing, loading, writing) and
TakenokoAgent (config loading, family management).
"""

from __future__ import annotations


import pytest

from interface.bus import FamilyPrefix, MessageBus
from interface.llm import LLMConfig
from interface.logging import ModuleLogger
from interface.permissions import PermissionManager
from main import SelfModel, TakenokoAgent


# ── SelfModel ──


class TestSelfModelParseSections:
    def test_empty_content(self):
        result = SelfModel._parse_sections("")
        assert result == {}

    def test_single_section(self):
        content = "## Agent\nThis is the agent section.\nMore text.\n"
        result = SelfModel._parse_sections(content)
        assert "Agent" in result
        assert "This is the agent section." in result["Agent"]

    def test_multiple_sections(self):
        content = (
            "## Agent\nAgent info.\n\n"
            "## Reaction\nReaction info.\n\n"
            "## Prediction\nPrediction info.\n"
        )
        result = SelfModel._parse_sections(content)
        assert len(result) == 3
        assert "Agent" in result
        assert "Reaction" in result
        assert "Prediction" in result

    def test_content_before_first_header_ignored(self):
        content = "Preamble text\n## Section1\nBody1\n"
        result = SelfModel._parse_sections(content)
        assert len(result) == 1
        assert "Section1" in result

    def test_empty_section_body(self):
        content = "## Empty\n## Next\nSome body.\n"
        result = SelfModel._parse_sections(content)
        assert result["Empty"] == ""
        assert "Some body." in result["Next"]


class TestSelfModelLoadAll:
    @pytest.mark.asyncio
    async def test_load_all_missing_file_returns_empty(self, mock_permissions, mock_logger):
        model = SelfModel("/nonexistent/self.md", mock_permissions, mock_logger)
        result = await model.load_all()
        assert result == {}

    @pytest.mark.asyncio
    async def test_load_all_parses_sections(self, mock_permissions, mock_logger, tmp_path):
        self_md = tmp_path / "self.md"
        self_md.write_text(
            "## Agent\nAgent description.\n\n"
            "## Re\nReaction family info.\n\n"
            "## Pr\nPrediction family info.\n",
            encoding="utf-8",
        )
        model = SelfModel(str(self_md), mock_permissions, mock_logger)
        result = await model.load_all()
        assert len(result) == 3
        assert "Agent" in result
        assert "Re" in result
        assert "Pr" in result


class TestSelfModelLoadPart:
    @pytest.mark.asyncio
    async def test_load_part_returns_section(self, mock_permissions, mock_logger, tmp_path):
        self_md = tmp_path / "self.md"
        self_md.write_text(
            "## Re\nReaction details.\n\n## Pr\nPrediction details.\n",
            encoding="utf-8",
        )
        model = SelfModel(str(self_md), mock_permissions, mock_logger)
        await model.load_all()
        re_section = await model.load_part("Re")
        assert "Reaction details." in re_section

    @pytest.mark.asyncio
    async def test_load_part_missing_section_returns_empty(self, mock_permissions, mock_logger, tmp_path):
        self_md = tmp_path / "self.md"
        self_md.write_text("## Re\nOnly Re.\n", encoding="utf-8")
        model = SelfModel(str(self_md), mock_permissions, mock_logger)
        await model.load_all()
        result = await model.load_part("Nonexistent")
        assert result == ""


class TestSelfModelWritePart:
    @pytest.mark.asyncio
    async def test_write_part_with_valid_permissions(self, mock_permissions, mock_logger, tmp_path):
        self_md = tmp_path / "self.md"
        self_md.write_text("## Re\nOld content.\n", encoding="utf-8")
        model = SelfModel(str(self_md), mock_permissions, mock_logger)
        await model.load_all()

        # Re can write its own section
        await model.write_part("Re", "New content.", requester=FamilyPrefix.Re)
        result = await model.load_part("Re")
        assert result == "New content."

    @pytest.mark.asyncio
    async def test_write_part_raises_on_permission_denied(self, mock_permissions, mock_logger, tmp_path):
        self_md = tmp_path / "self.md"
        self_md.write_text("## Pr\nPr content.\n", encoding="utf-8")
        model = SelfModel(str(self_md), mock_permissions, mock_logger)
        await model.load_all()

        with pytest.raises(PermissionError, match="lacks WRITE_SELF_MD"):
            await model.write_part("Pr", "Hacked!", requester=FamilyPrefix.Mo)

    @pytest.mark.asyncio
    async def test_pr_can_write_any_section(self, mock_permissions, mock_logger, tmp_path):
        self_md = tmp_path / "self.md"
        self_md.write_text("## Mo\nMotion content.\n", encoding="utf-8")
        model = SelfModel(str(self_md), mock_permissions, mock_logger)
        await model.load_all()

        await model.write_part("Mo", "Updated by Pr.", requester=FamilyPrefix.Pr)
        result = await model.load_part("Mo")
        assert result == "Updated by Pr."


# ── TakenokoAgent ──


class TestTakenokoAgentLoadConfig:
    def test_load_config_reads_yaml(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "agent:\n  name: TestAgent\nfamilies:\n  Re:\n    model: gpt-4o\n",
            encoding="utf-8",
        )
        agent = TakenokoAgent(config_path=str(config_file))
        config = agent._load_config()
        assert config["agent"]["name"] == "TestAgent"
        assert config["families"]["Re"]["model"] == "gpt-4o"

    def test_load_config_missing_file_raises(self):
        agent = TakenokoAgent(config_path="/nonexistent/config.yaml")
        with pytest.raises(FileNotFoundError):
            agent._load_config()


class TestTakenokoAgentBuildLLMConfig:
    def test_build_llm_config_extracts_family(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "agent:\n  name: Test\n"
            "families:\n"
            "  Pr:\n"
            "    model: gpt-4o\n"
            "    temperature: 0.5\n"
            "    max_tokens: 8192\n"
            "    prompt: prompts/prediction/pr_default.md\n",
            encoding="utf-8",
        )
        agent = TakenokoAgent(config_path=str(config_file))
        agent._config = agent._load_config()
        llm_config = agent._build_llm_config(FamilyPrefix.Pr)
        assert llm_config.model_name == "gpt-4o"
        assert llm_config.temperature == 0.5
        assert llm_config.max_tokens == 8192
        assert llm_config.system_prompt_path == "prompts/prediction/pr_default.md"

    def test_build_llm_config_defaults_for_missing_family(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("agent:\n  name: Test\nfamilies: {}\n", encoding="utf-8")
        agent = TakenokoAgent(config_path=str(config_file))
        agent._config = agent._load_config()
        llm_config = agent._build_llm_config(FamilyPrefix.Mo)
        assert llm_config.model_name == "gpt-4o"
        assert llm_config.temperature == 0.7
        assert llm_config.max_tokens == 4096
        assert llm_config.system_prompt_path is None


class TestTakenokoAgentGetFamily:
    @pytest.mark.asyncio
    async def test_get_family_returns_module(self):
        """Test that get_family returns a module after start()."""
        agent = TakenokoAgent(
            config_path="admin/yamls/default.yaml"
        )
        # Manually set up enough to test get_family without full start()
        logger = ModuleLogger("SYS", "test")
        bus = MessageBus(logger, queue_limits={"Pr": 10, "Re": 5, "Ev": 5, "Me": 5, "Mo": 5})
        permissions = PermissionManager(logger)

        from prediction.pr_main_module import PredictionModule

        pr = PredictionModule(
            bus=bus,
            logger=ModuleLogger("Pr", "main"),
            llm_config=LLMConfig(),
            permissions=permissions,
        )
        agent._families[FamilyPrefix.Pr] = pr

        result = agent.get_family(FamilyPrefix.Pr)
        assert result is pr

    def test_get_family_raises_on_missing(self):
        agent = TakenokoAgent()
        with pytest.raises(KeyError, match="Family.*not found"):
            agent.get_family(FamilyPrefix.Re)
