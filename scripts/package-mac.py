#!/usr/bin/env python3
"""Export a clean local Git revision as a self-verifying Mac source package."""
import argparse
import ast
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parents[1]
FILES = {"Dockerfile", ".dockerignore", "README.md", "app.py", "requirements.txt",
         "docker-compose.mac.yml", "scripts/run-mac.sh", "scripts/package-mac.py"}
DIRECTORIES = {"frontend", "roadmap_generator", "plugins", "config"}
EXCLUDED = {"node_modules", "dist", ".npm-cache", "__pycache__", ".env", ".env.local"}


def package(repo: Path, output_dir: Path) -> dict:
    """Return metadata for an archive made only from the clean committed tree."""
    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args])

    if git("status", "--porcelain").strip():
        raise RuntimeError("Нужен чистый Git-коммит; сохраните изменения локально.")
    revision = git("rev-parse", "HEAD").decode().strip()
    assignments = ast.parse(git("show", "HEAD:roadmap_generator/version.py"))
    version = next(ast.literal_eval(node.value) for node in assignments.body
                   if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "APP_VERSION" for target in node.targets))
    if not isinstance(version, str) or not all(p.isdigit() for p in version.split(".")) or len(version.split(".")) != 3:
        raise RuntimeError("Некорректная APP_VERSION.")
    tracked = git("ls-tree", "-rz", "--name-only", "HEAD").decode().split("\0")
    selected = [name for name in tracked if name
                and (name in FILES or PurePosixPath(name).parts[0] in DIRECTORIES)
                and not EXCLUDED.intersection(PurePosixPath(name).parts)]
    missing = {"Dockerfile", "app.py", "docker-compose.mac.yml", "scripts/run-mac.sh"} - set(selected)
    if missing:
        raise RuntimeError("В коммите отсутствуют файлы пакета: " + ", ".join(sorted(missing)))
    stem = "json-pptx-{}-{}-mac-source".format(version, revision[:12])
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / (stem + ".tar.gz")
    if target.exists():
        raise FileExistsError("Пакет уже существует: " + str(target))
    source = git("archive", "--format=tar", "HEAD", "--", *selected)
    checksums = []
    with tempfile.TemporaryDirectory(prefix=".mac-package-", dir=output_dir) as staging:
        temporary = Path(staging) / target.name
        with tarfile.open(fileobj=io.BytesIO(source), mode="r:") as tree, tarfile.open(temporary, "w:gz") as archive:
            for member in tree:
                if not (member.isfile() or member.isdir()):
                    raise RuntimeError("В пакете не допускаются ссылки: " + member.name)
                content = tree.extractfile(member).read() if member.isfile() else None
                if content is not None:
                    checksums.append(hashlib.sha256(content).hexdigest() + "  " + member.name)
                member.name = stem + "/" + member.name
                archive.addfile(member, io.BytesIO(content) if content is not None else None)
            for name, value in (("SOURCE_REVISION", revision), ("VERSION", version)):
                content = (value + "\n").encode()
                member = tarfile.TarInfo(stem + "/" + name)
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
                checksums.append(hashlib.sha256(content).hexdigest() + "  " + name)
            content = ("\n".join(sorted(checksums)) + "\n").encode()
            member = tarfile.TarInfo(stem + "/SHA256SUMS")
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        os.link(temporary, target)  # Atomic publication; never overwrite an existing package.
    target.with_suffix(target.suffix + ".sha256").write_text(digest + "  " + target.name + "\n")
    return {"archive": str(target), "directory": stem, "version": version,
            "revision": revision, "sha256": digest, "bytes": target.stat().st_size}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT.parent / "releases")
    args = parser.parse_args()
    print(json.dumps(package(ROOT, args.output_dir.resolve()), ensure_ascii=False, indent=2))
