"""Artifact contract checks on isolated copies of the real built JAR."""
from pathlib import Path
import json
import tempfile
import unittest
import zipfile

from tools.package_modrinth import ROOT, audit_jar


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
