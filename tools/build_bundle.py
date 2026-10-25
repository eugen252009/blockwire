#!/usr/bin/env python3
"""Build a local, allowlisted handoff bundle. Never copies game dirs or publishes anything."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ["AGENTS.md", "README.md", "SECURITY.md", "THIRD_PARTY.md", "LICENSE", "CHANGELOG.md",
              "TODO.md", ".gitignore", "build.gradle", "settings.gradle", "gradle.properties",
              "gradlew", "gradlew.bat"]
SOURCE_DIRS = ["src/main", "src/contractTest", "docs", "licenses", "gradle", "python/src", "python/tests",
               "examples", "tests", "tools"]
PYTHON_FILES = ["python/pyproject.toml", "python/README.md", "python/LICENSE"]
FORBIDDEN = {"identity.p12", "certificate.pem", "token", "settings.json", ".env"}
IGNORED_DIRS = {"__pycache__", "build", "dist", ".gradle", ".venv", "*.egg-info"}


def source_entries():
    files = [ROOT / name for name in ROOT_FILES + PYTHON_FILES]
    for name in SOURCE_DIRS:
        files.extend(path for path in (ROOT / name).rglob("*") if path.is_file())
    for path in sorted(set(files)):
        relative = path.relative_to(ROOT)
        if any(part in IGNORED_DIRS or part.endswith(".egg-info") for part in relative.parts) or path.suffix == ".pyc":
            continue
        if path.is_symlink() or path.name in FORBIDDEN or any(part.startswith(".") for part in relative.parts if part != ".gitignore"):
            raise ValueError(f"Refusing unexpected source file: {relative}")
        yield "source/" + relative.as_posix(), path.read_bytes(), 0o755 if path.name == "gradlew" else 0o644


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true", help="Package already built matching-version artifacts")
    args = parser.parse_args()
    version = next(line.split("=", 1)[1] for line in (ROOT / "gradle.properties").read_text().splitlines()
                   if line.startswith("mod_version="))
    python_version = tomllib.loads((ROOT / "python/pyproject.toml").read_text())["project"]["version"]
    python_out = ROOT / "build/bundle-python"
    if not args.skip_build:
        subprocess.run(["./gradlew", "--console=plain", "build"], cwd=ROOT, check=True)
        if shutil.which("uv"):
            command = ["uv", "build", "python", "--out-dir", str(python_out)]
        else:
            command = [sys.executable, "-m", "build", "python", "--outdir", str(python_out)]
        subprocess.run(command, cwd=ROOT, check=True)
    entries = {name: (data, mode) for name, data, mode in source_entries()}
    jar = ROOT / f"build/libs/blockwire-{version}.jar"
    sources = ROOT / f"build/libs/blockwire-{version}-sources.jar"
    wheel = python_out / f"blockwire-{python_version}-py3-none-any.whl"
    sdist = python_out / f"blockwire-{python_version}.tar.gz"
    with zipfile.ZipFile(jar) as archive:
        import json
        metadata = json.loads(archive.read("fabric.mod.json"))
        if metadata["version"] != version or metadata["environment"] != "client":
            raise ValueError("Wrong mod artifact/version")
    with zipfile.ZipFile(wheel) as archive:
        metadata_name = next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
        if "\nVersion: "+python_version+"\n" not in archive.read(metadata_name).decode():
            raise ValueError("Wrong Python artifact/version")
    for destination, path in [("mods/"+jar.name, jar), ("source-artifacts/"+sources.name, sources),
                              ("python/"+wheel.name, wheel), ("python/"+sdist.name, sdist)]:
        entries[destination] = (path.read_bytes(), 0o644)
    entries["INSTALL.md"] = ((ROOT / "docs/bundle-install.md").read_bytes(), 0o644)
    checksums = "".join(hashlib.sha256(data).hexdigest()+"  "+name+"\n"
                        for name, (data, _) in sorted(entries.items()))
    entries["SHA256SUMS"] = (checksums.encode(), 0o644)
    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    target = out / f"blockwire-{version}.zip"
    with zipfile.ZipFile(target, "w") as archive:
        for name, (data, mode) in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = (0o100000 | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(digest+"  "+target.name+"\n")
    print(f"LOCAL_BUNDLE_READY {target} files={len(entries)} sha256={digest}")


if __name__ == "__main__":
    main()
