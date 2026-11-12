"""Delivery boundaries: local Git snapshot, package integrity and local Docker."""
import hashlib
import gzip
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MacDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="json-pptx delivery ")
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)

    def packager(self):
        script = ROOT / "scripts/package-mac.py"
        self.assertTrue(script.is_file(), "Mac source packager is missing")
        spec = importlib.util.spec_from_file_location("package_mac", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def repository(self):
        repo = self.work / "source repo"
        repo.mkdir()
        files = {
            ".gitignore": "data/\n",
            "README.md": "Committed source\n",
            "Dockerfile": "FROM python:3.14-slim\n",
            "docker-compose.mac.yml": "services: {}\n",
            "app.py": "# application\n",
            "requirements.txt": "",
            "scripts/run-mac.sh": "#!/bin/bash\n",
            "scripts/package-mac.py": "# packager\n",
            "roadmap_generator/version.py": 'APP_VERSION = "1.24.1"\n',
            "frontend/src/main.tsx": "// app\n",
            "frontend/package.json": "{}\n",
            "frontend/package-lock.json": "{}\n",
            "frontend/node_modules/private-binary": "do not export\n",
            "frontend/dist/index.html": "do not export\n",
            "Requirements/private.json": "do not export\n",
            ".env": "PRIVATE=do-not-export\n",
        }
        for name, content in files.items():
            target = repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c",
                        "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
        (repo / "data").mkdir()
        (repo / "data/profile.json").write_text("private runtime")
        return repo

    def test_export_excludes_dependencies_private_data_and_generated_files(self):
        result = self.packager().package(self.repository(), self.work / "releases")
        archive = Path(result["archive"])
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), result["sha256"])
        with tarfile.open(archive) as tar:
            files = {m.name.split("/", 1)[1]: tar.extractfile(m).read()
                     for m in tar.getmembers() if m.isfile()}
        self.assertEqual(files["README.md"], b"Committed source\n")
        self.assertIn("scripts/run-mac.sh", files)
        self.assertIn("frontend/src/main.tsx", files)
        self.assertEqual(files["SOURCE_REVISION"].decode().strip(), result["revision"])
        self.assertFalse(any(p.startswith(("frontend/node_modules/", "frontend/dist/", "Requirements/", "data/"))
                             or p == ".env" for p in files))
        for line in files["SHA256SUMS"].decode().splitlines():
            digest, name = line.split("  ", 1)
            self.assertEqual(hashlib.sha256(files[name]).hexdigest(), digest)

    def test_dirty_source_is_refused(self):
        module = self.packager()
        repo = self.repository()
        (repo / "app.py").write_text("uncommitted change")
        with self.assertRaisesRegex(RuntimeError, "[Cc]lean|[Dd]irty|чист"):
            module.package(repo, self.work / "releases")

    def test_failed_export_leaves_no_partial_archive_and_can_be_retried(self):
        module = self.packager()
        repo = self.repository()
        (repo / "frontend/src/external").symlink_to("/etc/passwd")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c",
                        "user.email=test@example.invalid", "commit", "-qm", "symlink"], check=True)
        output = self.work / "releases"
        for _ in range(2):
            with self.assertRaisesRegex(RuntimeError, "ссылки"):
                module.package(repo, output)
            self.assertEqual(list(output.iterdir()), [])

    def image(self, repo, architecture="arm64", revision=None):
        revision = revision or subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        config = json.dumps({"os": "linux", "architecture": architecture,
            "config": {"Labels": {"org.opencontainers.image.revision": revision,
                                   "org.opencontainers.image.version": "1.24.1"}},
            "rootfs": {"type": "layers", "diff_ids": []}}).encode()
        name = hashlib.sha256(config).hexdigest() + ".json"
        image = self.work / (architecture + "-image.tar")
        with tarfile.open(image, "w") as tar:
            for filename, content in [(name, config), ("manifest.json", json.dumps(
                    [{"Config": name, "RepoTags": ["json-pptx:test-arm64"], "Layers": []}]).encode())]:
                member = tarfile.TarInfo(filename)
                member.size = len(content)
                tar.addfile(member, io.BytesIO(content))
        return image

    def test_ready_package_contains_loadable_image_instead_of_application_sources(self):
        module = self.packager()
        self.assertTrue(callable(getattr(module, "package_image", None)), "Ready image packaging is missing")
        repo = self.repository()
        image = self.image(repo)
        result = module.package_image(repo, self.work / "releases", image)
        with tarfile.open(result["archive"]) as tar:
            files = {m.name.split("/", 1)[1]: tar.extractfile(m).read()
                     for m in tar.getmembers() if m.isfile()}
        self.assertEqual(gzip.decompress(files["image.tar.gz"]), image.read_bytes())
        self.assertEqual(files["image.txt"], b"json-pptx:test-arm64\n")
        self.assertIn("scripts/run-mac.sh", files)
        self.assertIn("docker-compose.mac.yml", files)
        self.assertNotIn("app.py", files)
        self.assertNotIn("frontend/src/main.tsx", files)

    def test_ready_package_rejects_unrelated_architecture_or_revision(self):
        module = self.packager()
        self.assertTrue(callable(getattr(module, "package_image", None)), "Ready image packaging is missing")
        repo = self.repository()
        for architecture, revision in [("amd64", None), ("arm64", "0" * 40)]:
            with self.subTest(architecture=architecture, revision=revision):
                with self.assertRaises(RuntimeError):
                    module.package_image(repo, self.work / "releases", self.image(repo, architecture, revision))

    def launcher(self):
        script = ROOT / "scripts/run-mac.sh"
        self.assertTrue(script.is_file(), "Mac Docker launcher is missing")
        folder = self.work / "Mac package"
        (folder / "scripts").mkdir(parents=True)
        shutil.copyfile(script, folder / "scripts/run-mac.sh")
        (folder / "docker-compose.mac.yml").write_text("services: {}\n")
        (folder / "SOURCE_REVISION").write_text("a" * 40 + "\n")
        (folder / "VERSION").write_text("1.24.1\n")
        (folder / "image.txt").write_text("json-pptx:fixture-arm64\n")
        (folder / "image.tar.gz").write_bytes(b"image fixture")
        files = [p for p in folder.rglob("*") if p.is_file()]
        (folder / "SHA256SUMS").write_text("".join(
            hashlib.sha256(p.read_bytes()).hexdigest() + "  " + str(p.relative_to(folder)) + "\n"
            for p in files))
        docker = self.work / "docker fixture"
        docker.write_text('''#!/bin/bash
set -e
printf '%s\\n' "$*" >> "$TEST_DOCKER_CALLS"
if [[ "$1 $2 $3" == "context inspect desktop-linux" ]]; then
  echo "${TEST_ENDPOINT:-unix:///local/docker.sock}"; exit 0
fi
[[ "$1 $2" == "--context desktop-linux" ]] || { echo "Wrong Docker context" >&2; exit 90; }
shift 2
case "$1" in
  info) echo linux/arm64 ;;
  load) ;;
  image)
    if [[ "$*" == *'{{.Id}}'* ]]; then echo sha256:new;
    else printf 'linux/arm64|%040d|1.24.1\\n' 0 | sed 's/0000000000000000000000000000000000000000/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/'; fi ;;
  container)
    case "$*" in
      *'{{.Image}}'*) echo sha256:old ;;
      *'{{.State.Running}}'*) echo true ;;
      *'/app/data'*) echo 'volume|json-pptx-mac_roadmap-data|true' ;;
      *'/app/templates_library'*) echo 'volume|json-pptx-mac_roadmap-templates|true' ;;
      *) exit 92 ;;
    esac ;;
  run) [[ "${TEST_BACKUP_FAIL:-0}" == 0 ]] || { echo fixture-backup-failed >&2; exit 43; } ;;
  compose)
    if [[ " $* " == *" ps "* && "${TEST_EXISTING:-0}" == 1 ]]; then echo existing-container; fi
    if [[ " $* " == *" up "* ]]; then
      [[ "${TEST_COMPOSE_FAIL:-42}" == 0 ]] || { echo fixture-startup-failed >&2; exit 42; }
    fi
    ;;
  *) exit 91 ;;
esac
''')
        docker.chmod(0o755)
        curl = self.work / "curl"
        curl.write_text('#!/bin/bash\necho \'{"status":"ok","version":"1.24.1"}\'\n')
        curl.chmod(0o755)
        env = dict(os.environ, JSON_PPTX_DOCKER=str(docker), DOCKER_HOST="tcp://wrong-host:2375",
                   TEST_DOCKER_CALLS=str(self.work / "docker-calls"), JSON_PPTX_BACKUP_DIR=str(self.work / "backups"))
        return folder, env

    def run_launcher(self, folder, env, action):
        return subprocess.run(["bash", str(folder / "scripts/run-mac.sh"), action],
                              env=env, text=True, capture_output=True)

    def test_local_desktop_context_is_used_even_if_docker_host_is_remote(self):
        folder, env = self.launcher()
        result = self.run_launcher(folder, env, "check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_remote_endpoint_is_refused(self):
        folder, env = self.launcher()
        env["TEST_ENDPOINT"] = "tcp://remote-host:2375"
        result = self.run_launcher(folder, env, "check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unix", result.stdout + result.stderr)

    def test_tampering_is_refused_before_docker(self):
        folder, env = self.launcher()
        (folder / "docker-compose.mac.yml").write_text("changed after download")
        result = self.run_launcher(folder, env, "verify")
        self.assertNotEqual(result.returncode, 0)

    def test_start_failure_is_not_reported_as_success(self):
        folder, env = self.launcher()
        result = self.run_launcher(folder, env, "start")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fixture-startup-failed", result.stdout + result.stderr)
        self.assertNotIn("Приложение готово", result.stdout + result.stderr)

    def test_start_loads_prebuilt_image_without_building_or_pulling(self):
        folder, env = self.launcher()
        env["TEST_COMPOSE_FAIL"] = "0"
        result = self.run_launcher(folder, env, "start")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Приложение готово", result.stdout)
        calls = Path(env["TEST_DOCKER_CALLS"]).read_text()
        self.assertIn(" load --input ", calls)
        self.assertIn("--no-build", calls)
        self.assertIn("--pull never", calls)
        self.assertNotIn(" --build ", calls)

    def test_failed_backup_prevents_recreation_and_resumes_previous_container(self):
        folder, env = self.launcher()
        env.update(TEST_EXISTING="1", TEST_BACKUP_FAIL="1", TEST_COMPOSE_FAIL="0")
        result = self.run_launcher(folder, env, "start")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fixture-backup-failed", result.stdout + result.stderr)
        calls = Path(env["TEST_DOCKER_CALLS"]).read_text()
        self.assertNotIn(" up ", calls)
        self.assertIn(" stop", calls)
        self.assertIn(" start", calls)


if __name__ == "__main__":
    unittest.main()
