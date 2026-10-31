"""Offline CPU tests for tools/recipe.py.

These tests prove parsing, pinning, rendering and argv construction only.
They do NOT prove native deployment, correctness or performance, and a fresh
prepare/render is explicitly not serving-qualified.
"""

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "recipe.py"
LOCK = REPO / "config" / "recipe.lock.json"
PATCH = REPO / "patches" / "upstream-tp8-launcher.patch"
EXAMPLE = REPO / "config" / "tp8.env.example"


def load_recipe():
    spec = importlib.util.spec_from_file_location("recipe_under_test", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_env(**over):
    values = {
        "HEAD_HOST": "spark1",
        "HEAD_IP": "198.51.100.1",
        "WORKER_IPS": " ".join(f"198.51.100.{i}" for i in range(2, 9)),
        "WORKER_HOSTS": " ".join(f"spark{i}" for i in range(2, 9)),
        "WORKER_USER": "",
        "WORKER_DIR": "/srv/test-operator/dsv41-tp8",
        "MODEL_DIR": "/srv/test-operator/NewModels/DeepSeek-V4.1-Flash-1017",
        "ENGRAM_DIR": "/srv/test-operator/dsv41-engram",
        "WORKER_ENGRAM_DIR": "/srv/test-operator/dsv41-tp8/engram",
        "SSH_IDENTITY": "/srv/test-operator/.ssh/id_ed25519_shared",
        "FABRIC_IFACE": "enp1s0f1np1",
        "NCCL_SOCKET_IFNAME": "enP7s7",
        "GLOO_SOCKET_IFNAME": "enP7s7",
        "IB_HCA": "rocep1s0f0,rocep1s0f1",
        "PORT": "8888",
        "DIST_PORT": "20000",
        "DSPARK_BLOCK_SIZE": "5",
        "BUILD_DOCKERFILE": "Dockerfile.canary-roce",
        "API_KEY": "",
    }
    values.update(over)
    return values


def write_env(directory, values, name=".env"):
    path = Path(directory) / name
    body = ["# test env", ""]
    for key, value in values.items():
        body.append(f"{key}={value}")
    body.append("")
    path.write_text("\n".join(body), encoding="utf-8")
    return path


class FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeSubprocess:
    """Records argv; never touches the OS."""

    def __init__(self, handler=None):
        self.calls = []
        self.handler = handler or (lambda args, kwargs: FakeProc())

    def run(self, args, **kwargs):
        assert not kwargs.get("shell"), "shell=True must never be used"
        self.calls.append((list(args), dict(kwargs)))
        return self.handler(list(args), dict(kwargs))

    def command_lines(self):
        return [" ".join(call[0]) for call in self.calls]


class RecipeTest(unittest.TestCase):
    def setUp(self):
        self.recipe = load_recipe()
        self._real_subprocess = self.recipe.subprocess
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self.recipe.subprocess = self._real_subprocess
        self._tmp.cleanup()

    def fake(self, handler=None):
        fake = FakeSubprocess(handler)
        self.recipe.subprocess = fake
        return fake

    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = self.recipe.main(argv)
        return rc, out.getvalue(), err.getvalue()

    # ---------- parsing ----------

    def test_parse_rejects_command_substitution(self):
        for value in ("$(id)", "`id`"):
            path = self.tmp / "bad.env"
            path.write_text(f"A={value}\n", encoding="utf-8")
            with self.assertRaises(self.recipe.RecipeError):
                self.recipe.parse_env_file(path)

    def test_parse_rejects_newline_injection(self):
        path = self.tmp / "bad.env"
        path.write_text('A=ok\nB="two\nlines"\n', encoding="utf-8")
        with self.assertRaises(self.recipe.RecipeError):
            self.recipe.parse_env_file(path)

    def test_parse_rejects_duplicate_and_bad_names(self):
        path = self.tmp / "dup.env"
        path.write_text("A=1\nA=2\n", encoding="utf-8")
        with self.assertRaises(self.recipe.RecipeError):
            self.recipe.parse_env_file(path)
        path.write_text("1BAD=2\n", encoding="utf-8")
        with self.assertRaises(self.recipe.RecipeError):
            self.recipe.parse_env_file(path)

    def test_parse_strips_quotes_and_comments(self):
        path = self.tmp / "ok.env"
        path.write_text("# comment\n\nexport FOO='a b'\nBAR=\"c,d\"\nBAZ=1\n", encoding="utf-8")
        cfg = self.recipe.parse_env_file(path)
        self.assertEqual(cfg["FOO"], "a b")
        self.assertEqual(cfg["BAR"], "c,d")
        self.assertEqual(cfg["BAZ"], "1")

    def test_rejects_nonempty_secret_without_echoing_value(self):
        path = self.tmp / "secret.env"
        marker = "sk-super-secret-value"
        path.write_text(f"API_KEY={marker}\n", encoding="utf-8")
        with self.assertRaises(self.recipe.RecipeError) as ctx:
            self.recipe.parse_env_file(path)
        self.assertIn("API_KEY", str(ctx.exception))
        self.assertNotIn(marker, str(ctx.exception))

    def test_rejects_unknown_sensitive_key(self):
        path = self.tmp / "secret.env"
        marker = "hunter2-marker"
        path.write_text(f"SOME_DEPLOY_TOKEN={marker}\n", encoding="utf-8")
        with self.assertRaises(self.recipe.RecipeError) as ctx:
            self.recipe.parse_env_file(path)
        self.assertIn("SOME_DEPLOY_TOKEN", str(ctx.exception))
        self.assertNotIn(marker, str(ctx.exception))

    def test_rejects_tp4_launcher(self):
        path = self.tmp / "launch.env"
        path.write_text("DSV41_LAUNCHER=tp4\n", encoding="utf-8")
        with self.assertRaises(self.recipe.RecipeError):
            self.recipe.parse_env_file(path)

    # ---------- plan ----------

    def test_plan_requires_every_key(self):
        values = valid_env()
        del values["WORKER_HOSTS"]
        rc, _, err = self.run_main(["plan", "--env-file", str(write_env(self.tmp, values))])
        self.assertEqual(rc, 2)
        self.assertIn("WORKER_HOSTS", err)

    def test_plan_requires_seven_unique_workers(self):
        dup = " ".join(f"198.51.100.{i}" for i in (2, 2, 3, 4, 5, 6, 7))
        rc, _, err = self.run_main(["plan", "--env-file", str(write_env(self.tmp, valid_env(WORKER_IPS=dup)))])
        self.assertEqual(rc, 2)
        self.assertIn("duplicate", err.lower())

    def test_plan_allows_placeholders_but_warns(self):
        values = valid_env(WORKER_HOSTS=" ".join(f"worker{i}.example.invalid" for i in range(1, 8)))
        rc, out, _ = self.run_main(["plan", "--env-file", str(write_env(self.tmp, values))])
        self.assertEqual(rc, 0)
        self.assertIn("placeholder", out.lower())
        self.assertIn("CONTEXT_LENGTH=1048576", out)
        self.assertIn("MAX_TOTAL_TOKENS=6600000", out)
        self.assertIn("MAX_RUNNING_REQUESTS=32", out)
        self.assertIn("CHUNKED_PREFILL_SIZE=4096", out)
        self.assertIn("MEM_FRACTION_STATIC=0.9", out)
        self.assertIn("SGLANG_ROCE_ALLREDUCE=1", out)
        self.assertIn("DSV41_CACHE_GIB=0", out)
        self.assertIn("NOT hash-verified", out)
        self.assertIn("six", out)  # DSPARK_BLOCK_SIZE=5 -> six speculative tokens

    def test_plan_detects_divergence(self):
        rc, out, _ = self.run_main([
            "plan", "--env-file",
            str(write_env(self.tmp, valid_env(CONTEXT_LENGTH="409600", TP_SIZE="3"))),
        ])
        self.assertEqual(rc, 0)
        self.assertIn("divergences", out)
        self.assertIn("CONTEXT_LENGTH", out)

    def test_plan_accepts_shipped_example(self):
        self.assertTrue(EXAMPLE.is_file(), EXAMPLE)
        rc, out, err = self.run_main(["plan", "--env-file", str(EXAMPLE)])
        self.assertEqual(rc, 0, err)
        self.assertIn("placeholder", out.lower())
        self.assertIn("MODEL_DIR", out)
        self.assertIn("FABRIC_IFACE", out)
        self.assertNotIn("API_KEY=", out)

    # ---------- prepare ----------

    def test_prepare_refuses_non_owned_directory(self):
        target = self.tmp / "existing"
        target.mkdir()
        (target / "keep.txt").write_text("user data\n", encoding="utf-8")
        rc, _, err = self.run_main(["prepare", "--directory", str(target)])
        self.assertEqual(rc, 2)
        self.assertIn("refusing", err.lower())
        self.assertEqual((target / "keep.txt").read_text(encoding="utf-8"), "user data\n")

    def test_prepare_refuses_recipe_repo(self):
        rc, _, err = self.run_main(["prepare", "--directory", str(REPO)])
        self.assertEqual(rc, 2)
        self.assertIn("refusing", err.lower())

    def test_prepare_allows_only_ignored_runtime_subtree(self):
        root = self.tmp / "recipe-checkout"
        (root / "config").mkdir(parents=True)
        (root / "patches").mkdir()
        (root / "config/recipe.lock.json").write_bytes(LOCK.read_bytes())
        (root / "patches/upstream-tp8-launcher.patch").write_bytes(PATCH.read_bytes())
        original = self.recipe.repo_root
        setattr(self.recipe, "repo_root", lambda: root)
        self.addCleanup(setattr, self.recipe, "repo_root", original)
        commit = json.loads(LOCK.read_text())["upstream_commit"]
        self.fake(lambda args, kwargs: FakeProc(stdout=commit + "\n") if "rev-parse" in args else FakeProc())
        target = root / ".runtime/upstream"
        rc, _, err = self.run_main(["prepare", "--directory", str(target)])
        self.assertEqual(rc, 0, err)
        self.assertTrue((target / self.recipe.MARKER_NAME).is_file())
        rc, _, err = self.run_main(["prepare", "--directory", str(root / "tools/runtime")])
        self.assertEqual(rc, 2)
        self.assertIn("refusing", err)
        self.assertFalse((root / "tools/runtime").exists())

    def test_prepare_flow_pins_commit_and_writes_marker(self):
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        commit = lock["upstream_commit"]

        def handler(args, kwargs):
            if "rev-parse" in args:
                return FakeProc(stdout=commit + "\n")
            return FakeProc()

        fake = self.fake(handler)
        target = self.tmp / "runtime"
        rc, _, err = self.run_main(["prepare", "--directory", str(target)])
        self.assertEqual(rc, 0, err)

        lines = fake.command_lines()
        self.assertTrue(any(line.endswith("init -q") for line in lines))
        self.assertTrue(any("fetch --depth 1 origin " + commit in line for line in lines))
        self.assertTrue(any("checkout" in line and commit in line for line in lines))
        apply_lines = [line for line in lines if "apply" in line]
        self.assertTrue(any("--check" in line for line in apply_lines))
        self.assertTrue(any("--check" not in line for line in apply_lines))
        joined = "\n".join(lines)
        self.assertFalse(any(Path(argv[0]).name == "docker" for argv, _ in fake.calls))
        self.assertFalse(any(len(argv) > 1 and argv[0] == "git" and argv[1] == "clone"
                             for argv, _ in fake.calls))

        marker = json.loads((target / self.recipe.MARKER_NAME).read_text(encoding="utf-8"))
        self.assertEqual(marker["upstream_commit"], commit)
        self.assertEqual(marker["upstream_url"], lock["upstream_url"])
        self.assertEqual(marker["tool_version"], self.recipe.TOOL_VERSION)
        self.assertTrue(marker["source_only"])
        self.assertFalse(marker["weights_downloaded"])
        self.assertFalse(marker["image_built"])
        self.assertEqual(marker["patch_sha256"], self.recipe.sha256_file(PATCH))

    def test_prepare_refuses_mismatched_marker(self):
        target = self.tmp / "runtime"
        target.mkdir()
        (target / self.recipe.MARKER_NAME).write_text(
            json.dumps(
                {
                    "upstream_commit": "0" * 40,
                    "upstream_url": "https://example.invalid/x.git",
                    "patch_sha256": "0" * 64,
                }
            ),
            encoding="utf-8",
        )
        fake = self.fake()
        rc, _, err = self.run_main(["prepare", "--directory", str(target)])
        self.assertEqual(rc, 2)
        self.assertIn("refusing", err.lower())
        self.assertEqual(fake.calls, [])

    # ---------- render ----------

    def make_prepared_runtime(self, commit, patch_sha):
        runtime = self.tmp / "runtime"
        runtime.mkdir(exist_ok=True)
        (runtime / self.recipe.MARKER_NAME).write_text(
            json.dumps(
                {
                    "schema_version": self.recipe.SCHEMA_VERSION,
                    "upstream_commit": commit,
                    "upstream_url": json.loads(LOCK.read_text())["upstream_url"],
                    "patch_sha256": patch_sha,
                }
            ),
            encoding="utf-8",
        )
        return runtime

    def render_fake(self, commit):
        def handler(args, kwargs):
            if "rev-parse" in args:
                return FakeProc(stdout=commit + "\n")
            return FakeProc()

        return self.fake(handler)

    def test_render_requires_prepared_marker(self):
        env = write_env(self.tmp, valid_env())
        runtime = self.tmp / "runtime"
        runtime.mkdir()
        self.fake()
        rc, _, err = self.run_main(["render", "--env-file", str(env), "--runtime", str(runtime)])
        self.assertEqual(rc, 2)
        self.assertIn("prepare", err)

    def test_render_refuses_placeholders(self):
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        env = write_env(self.tmp, valid_env(WORKER_HOSTS=" ".join(f"w{i}.example.invalid" for i in range(1, 8))))
        runtime = self.make_prepared_runtime(lock["upstream_commit"], self.recipe.sha256_file(PATCH))
        self.render_fake(lock["upstream_commit"])
        rc, _, err = self.run_main(["render", "--env-file", str(env), "--runtime", str(runtime)])
        self.assertEqual(rc, 2)
        self.assertIn("placeholder", err.lower())
        self.assertFalse((runtime / ".env.tp8").exists())

    def test_render_refuses_shipped_example(self):
        self.assertTrue(EXAMPLE.is_file(), EXAMPLE)
        runtime = self.tmp / "runtime"
        runtime.mkdir()
        rc, _, err = self.run_main([
            "render", "--env-file", str(EXAMPLE), "--runtime", str(runtime)
        ])
        self.assertEqual(rc, 2)
        self.assertIn("placeholder", err.lower())
        self.assertFalse((runtime / ".env.tp8").exists())

    def test_render_emits_env_and_wrapper(self):
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        env = write_env(self.tmp, valid_env(CONTEXT_LENGTH="409600", TP_SIZE="3"))
        runtime = self.make_prepared_runtime(lock["upstream_commit"], self.recipe.sha256_file(PATCH))
        self.render_fake(lock["upstream_commit"])
        rc, _, err = self.run_main(["render", "--env-file", str(env), "--runtime", str(runtime)])
        self.assertEqual(rc, 0, err)

        cfg = self.recipe.parse_env_file(runtime / ".env.tp8")
        for key, value in self.recipe.CANONICAL_PROFILE.items():
            self.assertEqual(cfg[key], value, key)
        self.assertEqual(cfg["API_KEY"], "")
        self.assertEqual(cfg["HF_REPO"], lock["model_id"])
        self.assertEqual(cfg["HF_REVISION"], lock["recipe_model_revision"])
        rendered = (runtime / ".env.tp8").read_text(encoding="utf-8")
        self.assertIn("1048576", rendered)
        self.assertNotIn("sk-", rendered)
        self.assertNotIn("TOKEN=", rendered)
        self.assertEqual((runtime / ".env.tp8").stat().st_mode & 0o777, 0o600)

        wrapper = (runtime / "start-tp8.sh").read_text(encoding="utf-8")
        self.assertIn('ENV_FILE="$ROOT/.env.tp8"', wrapper)
        self.assertIn("unset DSV41_LAUNCHER", wrapper)
        self.assertNotIn("DSV41_LAUNCHER=tp4", wrapper)
        self.assertNotIn("export DSV41_LAUNCHER", wrapper)
        self.assertIn('exec "$ROOT/start.sh" "$@"', wrapper)
        self.assertTrue(os.access(runtime / "start-tp8.sh", os.X_OK))
        self.assertIn("not serving-qualified", wrapper)

    def test_render_rechecks_patch_and_head(self):
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        env = write_env(self.tmp, valid_env())
        runtime = self.make_prepared_runtime(lock["upstream_commit"], self.recipe.sha256_file(PATCH))

        def handler(args, kwargs):
            if "rev-parse" in args:
                return FakeProc(stdout=lock["upstream_commit"] + "\n")
            if "-R" in args:
                return FakeProc(returncode=1, stderr="patch does not apply")
            return FakeProc()

        self.fake(handler)
        rc, _, err = self.run_main(["render", "--env-file", str(env), "--runtime", str(runtime)])
        self.assertEqual(rc, 2)
        self.assertIn("patch", err.lower())
        self.assertFalse((runtime / ".env.tp8").exists())

    # ---------- run ----------

    def test_run_dry_run_prints_argv_and_does_not_execute(self):
        env = write_env(self.tmp, valid_env())
        runtime = self.tmp / "runtime"
        runtime.mkdir()
        fake = self.fake()
        rc, out, _ = self.run_main(
            ["run", "serve", "--env-file", str(env), "--runtime", str(runtime)]
        )
        self.assertEqual(rc, 0)
        self.assertIn("DRY RUN", out)
        self.assertIn("argv=", out)
        self.assertIn("serve", out)
        self.assertIn("not serving-qualified", out)
        self.assertEqual(fake.calls, [])
        self.assertFalse((runtime / ".env.tp8").exists())

    def test_run_execute_requires_both_flags(self):
        env = write_env(self.tmp, valid_env())
        runtime = self.tmp / "runtime"
        runtime.mkdir()
        fake = self.fake()
        rc, _, err = self.run_main(
            ["run", "serve", "--env-file", str(env), "--runtime", str(runtime), "--execute"]
        )
        self.assertEqual(rc, 2)
        self.assertIn("ack-unqualified-port", err)
        self.assertEqual(fake.calls, [])

    def test_run_execute_with_both_flags_uses_sanitized_env(self):
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        env = write_env(self.tmp, valid_env())
        runtime = self.make_prepared_runtime(lock["upstream_commit"], self.recipe.sha256_file(PATCH))
        fake = self.render_fake(lock["upstream_commit"])
        rc, _, err = self.run_main(["render", "--env-file", str(env), "--runtime", str(runtime)])
        self.assertEqual(rc, 0, err)

        fake.calls.clear()
        os.environ["API_KEY"] = "should-not-leak"
        try:
            rc, _, err = self.run_main([
                "run", "doctor", "--env-file", str(env), "--runtime", str(runtime),
                "--execute", "--ack-unqualified-port",
            ])
        finally:
            del os.environ["API_KEY"]
        self.assertEqual(rc, 0, err)
        exec_calls = [(a, k) for a, k in fake.calls if a and a[0].endswith("start-tp8.sh")]
        self.assertEqual(len(exec_calls), 1)
        argv, kwargs = exec_calls[0]
        self.assertEqual(argv[1], "doctor")
        self.assertNotEqual(kwargs.get("shell"), True)
        self.assertNotIn("API_KEY", kwargs["env"])
        self.assertNotIn("HF_TOKEN", kwargs["env"])
        self.assertNotIn("DSV41_LAUNCHER", kwargs["env"])

    def test_run_refuses_execute_when_render_unqualified(self):
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        env = write_env(self.tmp, valid_env())
        runtime = self.make_prepared_runtime(lock["upstream_commit"], self.recipe.sha256_file(PATCH))
        self.render_fake(lock["upstream_commit"])
        rc, _, err = self.run_main([
            "run", "serve", "--env-file", str(env), "--runtime", str(runtime),
            "--execute", "--ack-unqualified-port",
        ])
        self.assertEqual(rc, 2)
        self.assertIn("render", err.lower())

    def test_run_rejects_unknown_action(self):
        env = write_env(self.tmp, valid_env())
        with self.assertRaises(SystemExit):
            self.recipe.main(["run", "rm-rf", "--env-file", str(env), "--runtime", str(self.tmp)])

    # ---------- lock / CLI integration ----------

    def test_lock_matches_builtin_profile(self):
        lock = self.recipe.load_lock(LOCK)
        canonical = self.recipe.canonical_from_lock(lock)
        self.assertEqual(list(canonical.items()), list(self.recipe.CANONICAL_PROFILE.items()))
        self.assertEqual(lock["upstream_commit"], "64b02dea8681fb1d8e3a659ea432a8e9e9ba3995")
        self.assertIn("@sha256:", lock["base_image"])

    def test_cli_help_runs_for_real(self):
        proc = subprocess.run(
            [sys.executable, str(TOOL), "--help"], text=True, capture_output=True, shell=False
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for command in ("plan", "prepare", "render", "run"):
            self.assertIn(command, proc.stdout)

    def test_cli_plan_runs_for_real(self):
        env = write_env(self.tmp, valid_env())
        proc = subprocess.run(
            [sys.executable, str(TOOL), "plan", "--env-file", str(env)],
            text=True, capture_output=True, shell=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("CONTEXT_LENGTH=1048576", proc.stdout)
        self.assertIn("SGLANG_ROCE_ALLREDUCE=1", proc.stdout)
        self.assertIn("64b02dea8681fb1d8e3a659ea432a8e9e9ba3995", proc.stdout)

    def test_cli_plan_accepts_shipped_example_for_real(self):
        proc = subprocess.run(
            [sys.executable, str(TOOL), "plan", "--env-file", str(EXAMPLE)],
            text=True, capture_output=True, shell=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("placeholder", proc.stdout.lower())

    def test_cli_dryrun_runs_for_real(self):
        env = write_env(self.tmp, valid_env())
        runtime = self.tmp / "runtime"
        runtime.mkdir()
        proc = subprocess.run(
            [sys.executable, str(TOOL), "run", "doctor",
             "--env-file", str(env), "--runtime", str(runtime)],
            text=True, capture_output=True, shell=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("DRY RUN", proc.stdout)
        self.assertIn("start-tp8.sh", proc.stdout)

    def test_cli_rejects_command_substitution_without_echo(self):
        env = self.tmp / "evil.env"
        env.write_text("MODEL_DIR=$(touch /tmp/pwned-recipe-test)\n", encoding="utf-8")
        marker = Path("/tmp/pwned-recipe-test")
        if marker.exists():
            marker.unlink()
        proc = subprocess.run(
            [sys.executable, str(TOOL), "plan", "--env-file", str(env)],
            text=True, capture_output=True, shell=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("MODEL_DIR", proc.stderr)
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)