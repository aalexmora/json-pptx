"""Delivery boundaries: local Git snapshot, package integrity and local Docker."""
import hashlib
import importlib.util
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

    def launcher(self):
        script = ROOT / "scripts/run-mac.sh"
        self.assertTrue(script.is_file(), "Mac Docker launcher is missing")
        folder = self.work / "Mac package"
        (folder / "scripts").mkdir(parents=True)
        shutil.copyfile(script, folder / "scripts/run-mac.sh")
        (folder / "docker-compose.mac.yml").write_text("services: {}\n")
        (folder / "SOURCE_REVISION").write_text("a" * 40 + "\n")
        (folder / "VERSION").write_text("1.24.1\n")
        files = [p for p in folder.rglob("*") if p.is_file()]
        (folder / "SHA256SUMS").write_text("".join(
            hashlib.sha256(p.read_bytes()).hexdigest() + "  " + str(p.relative_to(folder)) + "\n"
            for p in files))
        docker = self.work / "docker fixture"
        docker.write_text('''#!/bin/bash
set -e
if [[ "$1 $2 $3" == "context inspect desktop-linux" ]]; then
  echo "${TEST_ENDPOINT:-unix:///local/docker.sock}"; exit 0
fi
[[ "$1 $2" == "--context desktop-linux" ]] || { echo "Wrong Docker context" >&2; exit 90; }
shift 2
case "$1" in
  info) echo linux/arm64 ;;
  compose)
    if [[ " $* " == *" up "* ]]; then echo 'fixture-startup-failed' >&2; exit 42; fi
    ;;
  *) exit 91 ;;
esac
''')
        docker.chmod(0o755)
        env = dict(os.environ, JSON_PPTX_DOCKER=str(docker), DOCKER_HOST="tcp://wrong-host:2375")
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


if __name__ == "__main__":
    unittest.main()
