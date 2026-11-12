#!/usr/bin/env python3
"""Export a clean local Git revision as a self-verifying Mac source package."""
import argparse
import ast
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import shutil
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parents[1]
FILES = {"Dockerfile", ".dockerignore", "README.md", "app.py", "requirements.txt",
         "docker-compose.mac.yml", "scripts/run-mac.sh", "scripts/package-mac.py"}
DIRECTORIES = {"frontend", "roadmap_generator", "plugins", "config"}
EXCLUDED = {"node_modules", "dist", ".npm-cache", "__pycache__", ".env", ".env.local"}


def git_read(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def repository_metadata(repo):
    if git_read(repo, "status", "--porcelain").strip():
        raise RuntimeError("Нужен чистый Git-коммит; сохраните изменения локально.")
    revision = git_read(repo, "rev-parse", "HEAD").decode().strip()
    assignments = ast.parse(git_read(repo, "show", "HEAD:roadmap_generator/version.py"))
    version = next(ast.literal_eval(node.value) for node in assignments.body
                   if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "APP_VERSION" for target in node.targets))
    if not isinstance(version, str) or not all(p.isdigit() for p in version.split(".")) or len(version.split(".")) != 3:
        raise RuntimeError("Некорректная APP_VERSION.")
    return revision, version


def file_sha256(file):
    digest = hashlib.sha256()
    with Path(file).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package(repo: Path, output_dir: Path) -> dict:
    """Export sources for the VM builder; this is not a ready Docker image."""
    revision, version = repository_metadata(repo)
    tracked = git_read(repo, "ls-tree", "-rz", "--name-only", "HEAD").decode().split("\0")
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
    source = git_read(repo, "archive", "--format=tar", "HEAD", "--", *selected)
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


def package_image(repo: Path, output_dir: Path, image_path: Path) -> dict:
    """Deliver an existing ARM64 Docker archive matched to the clean Git tree."""
    revision, version = repository_metadata(repo)
    with tarfile.open(image_path) as image:
        manifest = json.load(image.extractfile("manifest.json"))
        if len(manifest) != 1 or len(manifest[0].get("RepoTags", [])) != 1:
            raise RuntimeError("Нужен архив одного образа с одним тегом.")
        config_bytes = image.extractfile(manifest[0]["Config"]).read()
        config = json.loads(config_bytes)
    labels = config.get("config", {}).get("Labels", {})
    if config.get("os") != "linux" or config.get("architecture") != "arm64":
        raise RuntimeError("Пакет Mac требует образ Linux ARM64.")
    if labels.get("org.opencontainers.image.revision") != revision or labels.get("org.opencontainers.image.version") != version:
        raise RuntimeError("Git revision/version образа не совпадают с чистым коммитом.")
    tag = manifest[0]["RepoTags"][0]
    stem = "json-pptx-{}-{}-mac-arm64".format(version, revision[:12])
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / (stem + ".tar.gz")
    if target.exists():
        raise FileExistsError("Пакет уже существует: " + str(target))
    with tempfile.TemporaryDirectory(prefix=".mac-image-", dir=output_dir) as staging:
        folder = Path(staging) / stem
        (folder / "scripts").mkdir(parents=True)
        with Path(image_path).open("rb") as source, (folder / "image.tar.gz").open("wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=1, mtime=0) as compressed:
                shutil.copyfileobj(source, compressed, 1024 * 1024)
        for name in ("docker-compose.mac.yml", "scripts/run-mac.sh", "README.md"):
            (folder / name).write_bytes(git_read(repo, "show", "HEAD:" + name))
        for name, value in (("SOURCE_REVISION", revision), ("VERSION", version), ("image.txt", tag)):
            (folder / name).write_text(value + "\n")
        (folder / "BUILD.json").write_text(json.dumps({
            "version": version, "revision": revision, "platform": "linux/arm64", "image": tag,
            "imageId": "sha256:" + hashlib.sha256(config_bytes).hexdigest(),
            "baseImage": labels.get("org.opencontainers.image.base.name"),
            "hostContainerRunVerified": False}, indent=2) + "\n")
        files = sorted(p for p in folder.rglob("*") if p.is_file())
        (folder / "SHA256SUMS").write_text("".join(
            file_sha256(p) + "  " + p.relative_to(folder).as_posix() + "\n" for p in files))
        temporary = Path(staging) / target.name
        with tarfile.open(temporary, "w:gz", compresslevel=1) as tar:
            tar.add(folder, arcname=stem)
        digest = file_sha256(temporary)
        os.link(temporary, target)
    target.with_suffix(target.suffix + ".sha256").write_text(digest + "  " + target.name + "\n")
    return {"archive": str(target), "directory": stem, "version": version, "revision": revision,
            "sha256": digest, "bytes": target.stat().st_size, "image": tag,
            "platform": "linux/arm64", "kind": "ready-image"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT.parent / "releases")
    kind = parser.add_mutually_exclusive_group(required=True)
    kind.add_argument("--image-tar", type=Path, help="Prepared Linux ARM64 Docker archive")
    kind.add_argument("--source", action="store_true", help="VM build input only; not a ready image")
    args = parser.parse_args()
    result = package_image(ROOT, args.output_dir.resolve(), args.image_tar) if args.image_tar else package(ROOT, args.output_dir.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
