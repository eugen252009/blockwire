"""Artifact contract checks on isolated copies of the real built JAR."""
from pathlib import Path
import json
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from tools.package_modrinth import ROOT, audit_jar, release_notes


class ModrinthPackageContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        props = dict(line.split("=", 1) for line in (ROOT / "gradle.properties").read_text().splitlines() if "=" in line)
        cls.version, cls.minecraft = props["mod_version"], props["minecraft_version"]
        cls.jar = ROOT / f"build/libs/blockwire-{cls.version}.jar"
        with zipfile.ZipFile(cls.jar) as archive:
            cls.entries = {name: archive.read(name) for name in archive.namelist()}
        cls.metadata = json.loads(cls.entries["fabric.mod.json"])

    def rejected_copy(self, expected, *, metadata=None, added=None, removed=None):
        entries = dict(self.entries)
        if metadata is not None:
            entries["fabric.mod.json"] = json.dumps(metadata).encode()
        entries.update(added or {})
        for name in removed or []:
            entries.pop(name)
        with tempfile.TemporaryDirectory(prefix="blockwire-modrinth-test-") as folder:
            path = Path(folder) / "mutated.jar"
            with zipfile.ZipFile(path, "w") as archive:
                for name, content in entries.items():
                    archive.writestr(name, content)
            with self.assertRaisesRegex(ValueError, expected):
                audit_jar(path, self.version, self.minecraft)

    def test_real_artifact_is_a_client_mod(self):
        result = audit_jar(self.jar, self.version, self.minecraft)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["environment"], "client")
        self.assertEqual(len(result["nested_libraries"]), 3)

    def test_optional_modmenu_entrypoint_and_no_bundled_api(self):
        self.assertNotIn("modmenu", self.metadata["depends"])
        self.assertIn("modmenu", self.metadata["suggests"])
        self.assertEqual(self.metadata["entrypoints"]["modmenu"], ["dev.blockwire.compat.BlockwireModMenu"])
        self.assertIn("dev/blockwire/BlockwireSettingsScreen.class", self.entries)
        self.assertFalse(any(name.startswith("com/terraformersmc/") for name in self.entries))
        self.rejected_copy("optional, unbundled", metadata={**self.metadata,
            "depends": {**self.metadata["depends"], "modmenu": "*"}})
        self.rejected_copy("optional, unbundled", added={"com/terraformersmc/modmenu/api/ModMenuApi.class": b"fixture"})

    def test_rejects_missing_current_feature_classes(self):
        for name in ["VisibilityView", "BlockwireSettingsScreen", "LocalSettingsModel"]:
            with self.subTest(feature=name):
                self.rejected_copy("Missing feature class", removed=[f"dev/blockwire/{name}.class"])

    def test_release_notes_match_version_and_current_features(self):
        notes = release_notes(self.version)
        self.assertEqual(notes.splitlines()[0], f"# Blockwire {self.version} — Alpha")
        self.assertIn("Mod Menu", notes)
        self.assertIn("64 blocks", notes)
        self.assertIn("NOT implemented", notes)

    def test_release_notes_refuse_missing_or_wrong_version(self):
        with tempfile.TemporaryDirectory(prefix="blockwire-release-notes-") as folder:
            root = Path(folder)
            with patch("tools.package_modrinth.ROOT", root), self.assertRaises(FileNotFoundError):
                release_notes(self.version)
            path = root / "docs/releases" / (self.version+".md")
            path.parent.mkdir(parents=True)
            path.write_text("# Wrong release\n")
            with patch("tools.package_modrinth.ROOT", root), self.assertRaisesRegex(ValueError, "version mismatch"):
                release_notes(self.version)

    def test_rejects_server_metadata(self):
        self.rejected_copy("environment", metadata={**self.metadata, "environment": "*"})

    def test_rejects_wrong_version(self):
        self.rejected_copy("version", metadata={**self.metadata, "version": "wrong"})

    def test_rejects_missing_required_api(self):
        dependencies = dict(self.metadata["depends"])
        dependencies.pop("fabric-api")
        self.rejected_copy("runtime requirements", metadata={**self.metadata, "depends": dependencies})

    def test_rejects_runtime_identity(self):
        self.rejected_copy("identity material", added={"config/blockwire/tls/identity.p12": b"fixture"})

    def test_rejects_test_and_stale_classes(self):
        for name in ["dev/blockwire/TlsFixture.class", "dev/blockbridge/BlockBridge.class"]:
            with self.subTest(name=name):
                self.rejected_copy("Stale namespace or test classes", added={name: b"fixture"})

    def test_rejects_missing_license(self):
        self.rejected_copy("Missing resource/license", removed=["META-INF/licenses/BouncyCastle.txt"])

    def test_rejects_missing_nested_libraries(self):
        self.rejected_copy("Missing or undeclared", metadata={**self.metadata, "jars": []})

    def test_rejects_wrong_java_target(self):
        content = bytearray(self.entries["dev/blockwire/Blockwire.class"])
        content[6:8] = (61).to_bytes(2, "big")
        self.rejected_copy("Java 25", added={"dev/blockwire/Blockwire.class": bytes(content)})


if __name__ == "__main__":
    unittest.main()
