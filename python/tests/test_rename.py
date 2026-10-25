"""Compatibility boundaries for the Blockwire rename; no live connections."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from blockwire import Bridge
from blockwire.client import _environment
from blockwire.skills import SkillDefinition, SkillParameters, SkillResult, default_registry, load_selected_plugins


class RenameContracts(unittest.TestCase):
    def test_legacy_imports_share_class_identity(self):
        from block_bridge import Bridge as LegacyBridge, Player as LegacyPlayer
        from blockwire import Player
        from block_bridge.skills import SkillDefinition as LegacyDefinition
        from block_bridge.skills.core import SkillParameters as LegacyParameters
        self.assertIs(LegacyBridge, Bridge)
        self.assertIs(LegacyPlayer, Player)
        self.assertIs(LegacyDefinition, SkillDefinition)
        self.assertIs(LegacyParameters, SkillParameters)

    def test_legacy_environment_fallback_and_new_precedence(self):
        for suffix in ["CONFIG", "URL", "CERT_FILE", "TOKEN_FILE", "SKILLS"]:
            old, new = "BLOCK_BRIDGE_"+suffix, "BLOCKWIRE_"+suffix
            with self.subTest(suffix=suffix), patch.dict(os.environ, {old: "legacy"}, clear=True):
                self.assertEqual(_environment(new), "legacy")
                with patch.dict(os.environ, {new: "preferred"}):
                    self.assertEqual(_environment(new), "preferred")

    def test_legacy_config_credentials_and_certificate_path_are_not_rewritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config/block-bridge/settings.json"
            path.parent.mkdir(parents=True)
            content = json.dumps(dict(enabled=True, server_ip="127.0.0.1", port=8882, mcp_api_key="a"*64))
            path.write_text(content)
            path.chmod(0o600)
            with patch.dict(os.environ, {"BLOCK_BRIDGE_CONFIG": str(path)}, clear=True):
                connection = Bridge.from_env()
            self.assertEqual(connection.url, "wss://127.0.0.1:8882/v1")
            self.assertEqual(connection.certificate, path.parent / "tls/certificate.pem")
            self.assertEqual(path.read_text(), content)
            self.assertFalse((path.parent.parent / "blockwire").exists())
            self.assertEqual(Bridge.TLS_NAME, "block-bridge.invalid")

    def test_legacy_provider_group_still_requires_explicit_opt_in(self):
        class Provider:
            name = "legacy_fixture"
            def load(self):
                def register(registry):
                    registry.register(SkillDefinition("legacy_fixture", "Trusted legacy test provider", SkillParameters,
                        lambda ctx, goal: SkillResult(status="succeeded", reason="observed", text="fixture"),
                        controls_player=False))
                return register
        def installed(*, group):
            return [Provider()] if group == "block_bridge.skills" else []
        with patch("blockwire.skills.core.entry_points", side_effect=installed):
            registry = default_registry()
            load_selected_plugins(registry, "")
            self.assertEqual(len(registry.describe()), 1)
            load_selected_plugins(registry, "legacy_fixture")
            self.assertEqual(len(registry.describe()), 2)


if __name__ == "__main__":
    unittest.main()
