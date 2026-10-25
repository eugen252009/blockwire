#!/usr/bin/env python3
"""Prepare a local Modrinth mod upload kit. No upload/network API/publishing support."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import struct
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_FILES = {"identity.p12", "certificate.pem", "settings.json", "token", "accounts.json", ".env"}
FORBIDDEN_DIRS = {"run", "saves", "config", ".venv", "__pycache__"}


def audit_jar(path: Path, version: str, minecraft: str) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate archive entries")
        for name in names:
            member = PurePosixPath(name)
            if member.is_absolute() or ".." in member.parts or "\\" in name:
                raise ValueError("Unsafe archive path")
            if member.name in FORBIDDEN_FILES or FORBIDDEN_DIRS.intersection(member.parts):
                raise ValueError("Runtime configuration or identity material in mod")
            if name.startswith("dev/blockbridge/") or (name.startswith("dev/blockwire/") and
                    any(marker in name for marker in ["ContractTest", "TlsFixture"])):
                raise ValueError("Stale namespace or test classes in mod")
        metadata = json.loads(archive.read("fabric.mod.json"))
        if metadata.get("id") != "blockwire" or metadata.get("name") != "Blockwire":
            raise ValueError("Wrong mod identity")
        if metadata.get("version") != version or metadata.get("environment") != "client":
            raise ValueError("Wrong version or environment")
        dependencies = metadata.get("depends", {})
        if dependencies.get("minecraft") != minecraft or dependencies.get("java") != ">=25" or not dependencies.get("fabric-api"):
            raise ValueError("Wrong or missing runtime requirements")
        if metadata.get("entrypoints", {}).get("client") != ["dev.blockwire.Blockwire"]:
            raise ValueError("Wrong client entrypoint")
        bytecode = archive.read("dev/blockwire/Blockwire.class")
        if len(bytecode) < 8 or bytecode[:4] != b"\xca\xfe\xba\xbe" or struct.unpack(">H", bytecode[6:8])[0] != 69:
            raise ValueError("Expected Java 25 bytecode")
        for required in ["LICENSE_blockwire", "META-INF/licenses/BouncyCastle.txt", "THIRD_PARTY.md",
                         "assets/blockwire/icon.png", "blockwire.mixins.json"]:
            if required not in names:
                raise ValueError("Missing resource/license: "+required)
        mixins = json.loads(archive.read("blockwire.mixins.json"))
        for mixin in mixins.get("client", []):
            class_file = (mixins["package"]+"."+mixin).replace(".", "/")+".class"
            if class_file not in names:
                raise ValueError("Missing mixin class")
        nested = [name for name in names if name.startswith("META-INF/jars/") and name.endswith(".jar")]
        declared = [item["file"] for item in metadata.get("jars", [])]
        if len(nested) != 3 or set(nested) != set(declared):
            raise ValueError("Missing or undeclared bundled certificate libraries")
        for member in nested:
            with zipfile.ZipFile(io.BytesIO(archive.read(member))) as library:
                if "fabric.mod.json" not in library.namelist():
                    raise ValueError("Nested library lacks Fabric metadata")
        return {"status": "PASS", "mod_id": metadata["id"], "version": version,
                "environment": "client", "java_release": 25, "entries": len(names),
                "nested_libraries": nested, "required_dependency": "fabric-api"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true", help="Inspect/package an existing matching build")
    args = parser.parse_args()
    properties = dict(line.split("=", 1) for line in (ROOT / "gradle.properties").read_text().splitlines()
                      if "=" in line and not line.startswith("#"))
    version, minecraft = properties["mod_version"], properties["minecraft_version"]
    if not args.skip_build:
        subprocess.run(["./gradlew", "--console=plain", "build"], cwd=ROOT, check=True)
    main_jar = ROOT / f"build/libs/blockwire-{version}.jar"
    sources = ROOT / f"build/libs/blockwire-{version}-sources.jar"
    report = audit_jar(main_jar, version, minecraft)  # Validate before creating an upload kit.
    source_bytes = sources.read_bytes()
    out = ROOT / f"dist/modrinth/{version}"
    (out / "optional-sources").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(main_jar, out / main_jar.name)
    (out / "optional-sources" / sources.name).write_bytes(source_bytes)
    with zipfile.ZipFile(main_jar) as archive:
        (out / "project-icon.png").write_bytes(archive.read("assets/blockwire/icon.png"))
    digest = hashlib.sha256(main_jar.read_bytes()).hexdigest()
    prior = json.loads((ROOT / "docs/evidence/rename.json").read_text())
    report["artifact_sha256"] = digest
    report["packaged_graphical_smoke"] = ("PASS_IDENTICAL_PREVIOUSLY_TESTED_JAR"
        if prior["artifact_sha256"] == digest else "NOT_RUN_FOR_THIS_ARTIFACT")
    report["published"] = False
    (out / "packaging-report.json").write_text(json.dumps(report, indent=2)+"\n")
    settings = {"format": "blockwire.manual-modrinth-settings.v1", "not_an_api_upload_request": True,
                "project_name": "Blockwire", "suggested_slug": "blockwire", "slug_availability": "NOT CHECKED",
                "project_type": "mod", "version_number": version, "version_type": "alpha",
                "loaders": ["fabric"], "game_versions": [minecraft], "client_side": "required",
                "server_side": "unsupported", "java": 25, "license": "MIT",
                "primary_file": main_jar.name,
                "required_dependencies": [{"slug": "fabric-api", "dependency_type": "required"}],
                "owner_repository_issue_contact_and_sdk_url": "OPERATOR MUST SUPPLY"}
    (out / "modrinth-settings.json").write_text(json.dumps(settings, indent=2)+"\n")
    shutil.copyfile(ROOT / "docs/modrinth-description.md", out / "DESCRIPTION.md")
    (out / "RELEASE_NOTES.md").write_text(f"""# Blockwire {version} — Alpha

Initial unpublished alpha candidate: authenticated TLS client bridge; native player,
inventory and menu controls; optional external Python/MCP adapter; descriptive goals,
progress/cancellation and opt-in skill providers. Flat full-block walking only.
Includes the Blockwire rename with legacy configuration and TLS identity compatibility.

Not a general pathfinder or damage-immunity feature. Full Survival/two-client and
cross-platform qualification remain open. This folder is prepared locally only.
""")
    (out / "UPLOAD_INSTRUCTIONS.md").write_text(f"""# Manual Modrinth upload

Primary file: **{main_jar.name}**. Upload this JAR as a Fabric **mod** alpha for
Minecraft {minecraft}. Require Fabric API; client required, server unsupported.
Java 25 and Fabric Loader 0.20.1+ are required. About 9 MB; certificate libraries
are nested in the JAR with their notices. Do not upload the handoff ZIP or an mrpack.

The optional-sources/ JAR is a developer source attachment, NOT an installable mod.
Use project-icon.png for the project icon. Copy/edit DESCRIPTION.md and
RELEASE_NOTES.md; modrinth-settings.json is a manual reference, not an API payload.
The Python/MCP package is external: Modrinth does not automatically install it.

Before publication, supply actual owner/repository/issue/contact/SDK download URLs,
check name/slug availability and dependencies, review qualification limits and obtain
explicit publication approval. No URL, account ownership or approval is invented.
No file here has been uploaded. Keep this entire folder out of the mods directory.
""")
    checksums = []
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            checksums.append(hashlib.sha256(path.read_bytes()).hexdigest()+"  "+path.relative_to(out).as_posix())
    (out / "SHA256SUMS").write_text("\n".join(checksums)+"\n")
    print("MODRINTH_UPLOAD_KIT_READY "+str(out))
    print("PRIMARY_MOD_JAR "+str(out / main_jar.name))
    print("SHA256 "+digest)


if __name__ == "__main__":
    main()
