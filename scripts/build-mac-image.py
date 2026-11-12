#!/usr/bin/env python3
"""Assemble a local ARM64 image without exposing the main Mac's Docker API."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def verify_linux_extensions(directory):
    """Reject host-native extensions accidentally installed into the Linux layer."""
    count = 0
    for file in Path(directory).rglob("*"):
        if not file.is_file():
            continue
        if file.suffix in (".dylib", ".pyd"):
            raise RuntimeError("Non-Linux dependency: " + str(file))
        if ".so" not in file.name:
            continue
        with file.open("rb") as stream:
            header = stream.read(20)
        if len(header) < 20 or header[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<H", header, 18)[0] != 183:
            raise RuntimeError("Expected an ARM64 Linux ELF extension: " + str(file))
        count += 1
    return count


def build(output_dir, node, crane):
    spec = importlib.util.spec_from_file_location("package_mac", ROOT / "scripts/package-mac.py")
    delivery = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(delivery)
    revision, version = delivery.repository_metadata(ROOT)
    base = (ROOT / "docker/base-mac-image.txt").read_text().strip()
    if not re.fullmatch(r"python:3\.14-trixie@sha256:[0-9a-f]{64}", base):
        raise RuntimeError("Use the pinned official Python base image")
    if not node or not crane:
        raise RuntimeError("Specify --node and --crane paths in the VM")
    runtime = ROOT.parent / "runtime"
    runtime.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="ready-image-", dir=runtime))
    source_meta = delivery.package(ROOT, work)
    with tarfile.open(source_meta["archive"]) as source_archive:
        source_archive.extractall(work, filter="data")
    source = work / source_meta["directory"]
    node = Path(node).resolve()
    npm = node.parent.parent / "lib/node_modules/npm/bin/npm-cli.js"
    env = dict(os.environ, PATH=str(node.parent) + os.pathsep + os.environ["PATH"])
    for args in (("ci", "--no-audit", "--no-fund", "--cache", str(runtime / "npm-cache")),
                 ("run", "typecheck"), ("run", "build")):
        subprocess.run([str(node), str(npm), *args], cwd=source / "frontend", env=env, check=True)

    layer_root = work / "layer"
    app = layer_root / "app"
    app.mkdir(parents=True)
    for name in ("app.py", "roadmap_generator", "plugins", "config"):
        target = app / name
        if (source / name).is_dir():
            shutil.copytree(source / name, target)
        else:
            shutil.copy2(source / name, target)
    shutil.copytree(source / "frontend/dist", app / "frontend/dist")
    for name in ("data", "templates_library"):
        (app / name).mkdir()
    site = layer_root / "usr/local/lib/python3.14/site-packages"
    site.mkdir(parents=True)
    pip = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-compile",
           "--only-binary=:all:", "--python-version", "3.14", "--implementation", "cp", "--abi", "cp314"]
    for platform in ("manylinux_2_41_aarch64", "manylinux_2_39_aarch64", "manylinux_2_36_aarch64",
                     "manylinux_2_34_aarch64", "manylinux_2_28_aarch64", "manylinux_2_17_aarch64", "manylinux2014_aarch64"):
        pip.extend(["--platform", platform])
    subprocess.run([*pip, "--target", str(site), "-r", str(source / "requirements.txt")], check=True)
    shutil.rmtree(site / "bin", ignore_errors=True)  # Runtime uses python -m uvicorn.
    extensions = verify_linux_extensions(site)
    packages = json.loads(subprocess.check_output(
        [sys.executable, "-m", "pip", "list", "--path", str(site), "--format=json", "--disable-pip-version-check"], text=True))
    layer = work / "application-layer.tar"

    def ownership(member):
        member.uid = member.gid = 1000 if member.name == "app" or member.name.startswith("app/") else 0
        member.uname = member.gname = ""
        return member

    with tarfile.open(layer, "w") as tar:
        for directory in ("app", "usr"):
            tar.add(layer_root / directory, arcname=directory, filter=ownership)
    auth = work / "registry-anonymous"
    auth.mkdir()
    (auth / "config.json").write_text('{"auths":{}}\n')
    image_env = dict(os.environ, DOCKER_CONFIG=str(auth))
    image_tag = "json-pptx:{}-{}-arm64".format(version, revision[:12])
    image = work / "image.tar"
    subprocess.run([str(crane), "mutate", base, "--platform", "linux/arm64", "--append", str(layer),
        "--env", "PYTHONUNBUFFERED=1", "--env", "PYTHONDONTWRITEBYTECODE=1", "--env", "HOME=/app",
        "--label", "org.opencontainers.image.title=JsonPptx",
        "--label", "org.opencontainers.image.revision=" + revision,
        "--label", "org.opencontainers.image.version=" + version,
        "--label", "org.opencontainers.image.base.name=" + base,
        "--user", "1000:1000", "--workdir", "/app", "--exposed-ports", "8000/tcp",
        "--cmd", "python,-m,uvicorn,app:app,--host,0.0.0.0,--port,8000",
        "--tag", image_tag, "--output", str(image)], env=image_env, check=True)
    subprocess.run([str(crane), "validate", "--tarball", str(image)], check=True)
    result = delivery.package_image(ROOT, output_dir, image)
    result.update({"baseImage": base, "arm64ExtensionsVerified": extensions, "pythonPackages": packages,
        "frontendNode": subprocess.check_output([str(node), "--version"], text=True).strip(),
        "imageArchiveValidated": True, "containerRunVerified": False, "workDirectory": str(work)})
    (output_dir / "ready-image.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default=shutil.which("node"))
    parser.add_argument("--crane", default=shutil.which("crane"))
    parser.add_argument("--output-dir", type=Path, default=ROOT.parent / "releases")
    args = parser.parse_args()
    build(args.output_dir.resolve(), args.node, args.crane)
