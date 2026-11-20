#!/usr/bin/env python3
"""Run every check of the upstream memory-review change on this machine and write a report (see README.md).

    python run.py [--work DIR] [--only NAME,...] [--skip-e2e] [--quick] [--jobs N] [--hermes-ref REF] [--holo-ref REF]
    python run.py --only live --work DIR --sidecar-python PATH --bge-model-dir DIR

It fetches Hermes and the holographic plugin at their pinned commits, lets Hermes' own setup (PM) provision Python
3.14, Node, pnpm and the test environment inside DIR, applies each PR's patches to a clean base and runs that PR's
tests (plan.py), plus HOLO-1 and the adapter's self-checks. Use a dedicated DIR: it resets its test checkouts.
Hermes state and reports are separate from the installed app; download tools may use package caches.
Standard library only, Python 3.9+.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import plan

KIT = Path(__file__).resolve().parent
DOCS = KIT.parent
PROJECT = DOCS.parent.parent
SYSTEM = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
ORDER = ("holo", "adapter", "pr1", "pr2", "pr3", "pr4", "pr5", "pr6", "pr7", "all")
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
# The tester's own credentials stay out of every test process and every log.
_SECRET = re.compile(r"(_API_KEY|_TOKEN|_SECRET|_PASSWORD|_ACCESS_KEY)$|^(GH_TOKEN|GITHUB_TOKEN)$", re.I)
_GIT = ("git", "-c", "core.longpaths=true", "-c", "advice.detachedHead=false")


def platform_tag() -> str:
    machine = platform.machine().lower()
    machine = {"amd64": "x64", "x86_64": "x64", "aarch64": "arm64"}.get(machine, machine)
    return f"{SYSTEM}-{machine}"


def git_bash() -> str:
    """The bash that ships with Git for Windows (not WSL's bash.exe); plain bash elsewhere."""
    if SYSTEM != "windows":
        return "bash"
    exec_path = Path(subprocess.run(["git", "--exec-path"], capture_output=True, text=True, check=True).stdout.strip())
    for parent in exec_path.parents:
        if (parent / "bin" / "bash.exe").is_file():
            return str(parent / "bin" / "bash.exe")
    raise SystemExit("Git Bash not found: install Git for Windows (https://git-scm.com/download/win)")


# --- what an output says ------------------------------------------------------------------------------------------

def _lines(out: str, pattern: str) -> list[str]:
    return [line.strip() for line in out.splitlines() if re.search(pattern, line)]


def parse_backend(out):  # scripts/run_tests.sh
    return (_lines(out, r"^=== Summary:")[-1:] or [""])[0], sorted(set(_lines(out, r"^FAILED ")))


def parse_pytest(out):
    return (_lines(out, r"\d+ (passed|failed)")[-1:] or [""])[0], sorted(set(_lines(out, r"^FAILED ")))


def parse_vitest(out):
    summary = " | ".join(_lines(out, r"^\s*(Test Files|Tests)\s"))
    return summary, sorted(set(_lines(out, r"^\s*(FAIL|×)\s")))[:40]


def parse_playwright(out):
    return " | ".join(_lines(out, r"^\s*\d+ (passed|failed|flaky|skipped|did not run)")), _lines(out, r"^\s+\d+\) \[")


def parse_check(out):
    line = (_lines(out, r"^scripts/check: \d+ checks")[-1:] or [""])[0]
    failed = line.split("FAILED: ", 1)[1].split(", ") if "FAILED: " in line else []
    return line, failed


def parse_tail(out):
    rest = [line for line in out.splitlines() if line.strip() and not line.startswith(("$ ", "# cwd"))]
    return (rest[-1].strip()[:200] if rest else ""), []


# --- the run ------------------------------------------------------------------------------------------------------

class Kit:
    def __init__(self, args):
        self.args = args
        self.work = Path(args.work).expanduser().resolve()
        self.hermes, self.plugin, self.holo_base = self.work / "hermes-agent", self.work / "plugin", self.work / "holo-base"
        suffix = "-live" if args.only == "live" else ""
        self.out = KIT / "results" / (platform_tag() + suffix)
        self.logs = self.out / "logs"
        self.bash = git_bash()
        self.env: dict[str, str] = {}
        self.testpy = ""
        self.base = self.holo_ref = ""
        self.built = ""  # the state whose desktop build is current
        self.steps: list[dict] = []
        self.meta = {"platform": platform_tag(), "os": platform.platform(), "started": time.strftime("%Y-%m-%d %H:%M:%S"),
                     "kit_commit": self._kit_commit(), "work": str(self.work), "jobs": args.jobs}

    @staticmethod
    def _kit_commit() -> str:
        head = subprocess.run(["git", "-C", str(PROJECT), "rev-parse", "HEAD"], capture_output=True, text=True)
        dirty = subprocess.run(["git", "-C", str(PROJECT), "status", "--porcelain", "--", "docs", "memory"],
                               capture_output=True, text=True).stdout.strip()
        return head.stdout.strip() + (" (with local changes)" if dirty else "")

    # running and recording

    def call(self, name, cmd, cwd, env=None, timeout=5400):
        """Run *cmd* with its output in logs/<name>.log; (exit code, output, seconds)."""
        env = self.env if env is None else env
        exe = self.bash if cmd[0] == "bash" else (shutil.which(cmd[0], path=env.get("PATH")) or cmd[0])
        log = self.logs / f"{name}.log"
        start = time.time()
        with open(log, "w", encoding="utf-8", errors="replace") as fh:
            fh.write(f"$ {' '.join(map(str, cmd))}\n# cwd {cwd}\n\n")
            fh.flush()
            try:
                code = subprocess.run([exe, *map(str, cmd[1:])], cwd=cwd, env=env, stdout=fh, stderr=subprocess.STDOUT,
                                      stdin=subprocess.DEVNULL, timeout=timeout).returncode
            except subprocess.TimeoutExpired:
                code = 124
                fh.write(f"\n# timed out after {timeout} s\n")
            except OSError as exc:
                code = 127
                fh.write(f"\n# could not start: {exc}\n")
        return code, _ANSI.sub("", log.read_text(encoding="utf-8", errors="replace")), time.time() - start

    def step(self, name, state, kind, cmd, cwd, parse=parse_tail, env=None, expect="", timeout=5400):
        code, out, seconds = self.call(name, cmd, cwd, env, timeout)
        summary, failures = parse(out)
        status = "passed" if code == 0 else "failed"
        note = ""
        if code != 0 and failures:
            reasons = [self._known(kind, failure, out) for failure in failures]
            if all(reasons):
                status, note = "known", "; ".join(sorted(set(reasons)))
        if kind == "e2e" and code != 0 and re.search(r"\b\d+ passed", summary) and "failed" not in summary \
                and "EPERM" in out:  # Windows cannot remove a temp dir still in use; the tests passed
            status, note = "passed", "exit code from removing a busy temp dir (EPERM); all tests passed"
        self.record(name, state, kind, status, summary, failures, seconds, expect, note)
        return status in ("passed", "known")

    def record(self, name, state, kind, status, summary="", failures=(), seconds=0.0, expect="", note=""):
        self.steps.append({"step": name, "state": state, "kind": kind, "status": status, "summary": summary,
                           "failures": list(failures)[:40], "seconds": round(seconds, 1), "expect": expect,
                           "note": note, "log": f"logs/{name}.log"})
        print(f"[{status:>7}] {name}: {summary or note}", flush=True)
        self.write_report()

    @staticmethod
    def _known(kind, failure, out) -> str:
        for known_kind, text, systems, why, *evidence in plan.KNOWN:
            if (known_kind == kind and SYSTEM in systems and text in failure
                    and all(re.search(pattern, out) for pattern in evidence)):
                return f"{text}: {why}"
        return ""

    def git(self, name, repo, *args, state="setup"):
        return self.step(name, state, "git", [*_GIT, "-C", str(repo), *args], self.work, env=os.environ)

    # preparing

    def prepare(self):
        self.work.mkdir(parents=True, exist_ok=True)
        for sub in ("home", "tools", "tmp"):
            (self.work / sub).mkdir(exist_ok=True)
        if not (self.hermes / ".git").exists():
            subprocess.run([*_GIT, "init", "-q", str(self.hermes)], check=True)
            subprocess.run([*_GIT, "-C", str(self.hermes), "remote", "add", "origin", plan.HERMES_URL], check=True)
            subprocess.run([*_GIT, "-C", str(self.hermes), "config", "core.longpaths", "true"], check=True)
        # origin/main is the base: scripts/check reads its ratchet settings from there, as CI reads them from main.
        if not self.git("setup-fetch-hermes", self.hermes, "fetch", "--depth=1", "origin",
                        f"{self.args.hermes_ref}:refs/remotes/origin/main"):
            raise SystemExit("could not fetch Hermes; see results logs")
        self.base = subprocess.run(["git", "-C", str(self.hermes), "rev-parse", "origin/main"],
                                   capture_output=True, text=True, check=True).stdout.strip()
        self.reset_hermes()
        if not (self.plugin / ".git").exists():  # a full clone: the plugin's compat test checks out an old tag
            if not self.git("setup-clone-plugin", self.work, "clone", "-q", plan.HOLO_URL, str(self.plugin)):
                raise SystemExit("could not clone the holographic plugin; see results logs")
        self.holo_ref = subprocess.run(["git", "-C", str(self.plugin), "rev-parse", self.args.holo_ref],
                                       capture_output=True, text=True, check=True).stdout.strip()
        shutil.rmtree(self.holo_base, ignore_errors=True)
        tar = subprocess.run(["git", "-C", str(self.plugin), "archive", "--format=tar", self.holo_ref],
                             capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(tar)) as archive:
            archive.extractall(self.holo_base)
        self.meta.update(hermes_base=self.base, holo_base=self.holo_ref)

    def reset_hermes(self):
        """The base, clean: tracked files restored, files a patch added removed (ignored ones, the installs, stay)."""
        subprocess.run([*_GIT, "-C", str(self.hermes), "checkout", "-q", "--force", "--detach", self.base], check=True)
        subprocess.run([*_GIT, "-C", str(self.hermes), "clean", "-q", "-fd"], check=True)

    def provision(self):
        """Hermes' own setup provisions everything inside the work dir; then its environment is composed once."""
        base = {k: v for k, v in os.environ.items()
                if not k.startswith(("HERMES_", "MEMORY_REVIEW_")) and k not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV")
                and not _SECRET.search(k)}
        tmp = str(self.work / "tmp")
        base.update(HERMES_HOME=str(self.work / "home"), HERMES_RUNTIME_DIR=str(self.work / "tools"),
                    TMP=tmp, TEMP=tmp, TMPDIR=tmp, PYTHONIOENCODING="utf-8")
        if not self.step("env-setup", "setup", "env",
                         ["bash", "setup-hermes.sh", "--runtime-only", f"--test-environment={plan.TEST_EXTRAS}"],
                         self.hermes, env=base, timeout=7200):
            raise SystemExit("Hermes setup failed; see results logs/env-setup.log")
        compose = ('set -e; . scripts/_activation.sh; script="$(hermes_compose_env "$PWD" sh)"; '
                   'hermes_apply_env "$script"; '
                   'exec python -c "import json, os, sys; sys.stdout.write(json.dumps(dict(os.environ)))"')
        done = subprocess.run([self.bash, "-c", compose], cwd=self.hermes, env=base, capture_output=True, text=True)
        if done.returncode != 0:  # the environment itself is never written anywhere: it holds the tester's variables
            (self.logs / "env-compose.log").write_text(done.stderr, encoding="utf-8")
            self.record("env-compose", "setup", "env", "failed", note="see logs/env-compose.log")
            raise SystemExit("could not compose the Hermes environment")
        self.env = {k: v for k, v in json.loads(done.stdout).items() if not _SECRET.search(k)}
        self.env.update(HERMES_HOME=base["HERMES_HOME"], HERMES_RUNTIME_DIR=base["HERMES_RUNTIME_DIR"])
        probe = ("import sys; from pathlib import Path; from pm.testenv import testenv_python; "
                 "print(testenv_python(Path('.').resolve()) or '')")
        self.testpy = subprocess.run([shutil.which("python", path=self.env["PATH"]) or "python", "-c", probe],
                                     cwd=self.hermes, env=self.env, capture_output=True, text=True).stdout.strip()
        if not self.testpy:
            self.record("env-testpython", "setup", "env", "failed", note="no test interpreter after setup")
            raise SystemExit("Hermes setup left no test interpreter")
        self.versions()
        if not self.step("env-pnpm-install", "setup", "env", ["pnpm", "install", "--frozen-lockfile"], self.hermes):
            raise SystemExit("pnpm install failed; see results logs/env-pnpm-install.log")
        if not self.step("env-electron-runtime", "setup", "env",
                         ["node", "scripts/build/electron-runtime.mjs", "--source", "."], self.hermes):
            raise SystemExit("the Electron runtime could not be prepared; see results logs")

    def versions(self):
        def version(cmd):
            exe = shutil.which(cmd[0], path=self.env["PATH"]) or cmd[0]
            done = subprocess.run([exe, *cmd[1:]], env=self.env, capture_output=True, text=True)
            return (done.stdout or done.stderr).strip().splitlines()[0] if done.returncode == 0 else "?"
        self.meta.update(test_python=version([self.testpy, "--version"]), node=version(["node", "--version"]),
                         pnpm=version(["pnpm", "--version"]), git=version(["git", "--version"]))

    # the plugin and the adapter

    def holo(self):
        self.reset_hermes()
        subprocess.run([*_GIT, "-C", str(self.plugin), "checkout", "-q", "--force", "--detach", self.holo_ref], check=True)
        subprocess.run([*_GIT, "-C", str(self.plugin), "clean", "-q", "-fd"], check=True)
        if not self.git("holo-apply", self.plugin, "apply", str(DOCS / "patches" / plan.HOLO_PATCH), state="holo"):
            return
        env = {k: v for k, v in self.env.items() if k != "PYTHONPATH"}
        env["HERMES_AGENT_REPO"] = str(self.hermes)
        pytest = [self.testpy, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
        self.step("holo-new-tests", "holo", "pytest",
                  [*pytest, "tests/test_holographic_config_schema.py", "tests/test_holographic_save_config.py"],
                  self.plugin, parse_pytest, env, expect="7 passed")
        if not self.args.quick:
            self.step("holo-full-suite", "holo", "pytest", [*pytest, "-rfE"], self.plugin, parse_pytest, env,
                      expect="3698 passed, 16 skipped on Windows")
        ruff = [self.testpy, "-m", "ruff"] if self._has_module("ruff") else ["ruff"]
        self.step("holo-ruff", "holo", "lint", [*ruff, "check", "."], self.plugin, env=env, expect="All checks passed!")
        validate = ("import sys; sys.argv = ['hermes', 'plugins', 'validate', sys.argv[1]]; "
                    "from hermes_cli.main import main; main()")
        # HERMES_HOME stays the work dir's home: the CLI finds its PM install there, and nothing real is in it.
        self.step("holo-validate", "holo", "validate", ["python", "-c", validate, str(self.plugin)], self.hermes,
                  expect="Validation passed.")

    def _has_module(self, name) -> bool:
        return subprocess.run([self.testpy, "-c", f"import {name}"], env=self.env, capture_output=True).returncode == 0

    def adapter(self):
        adapter = PROJECT / "memory" / "plugin" / "holographic-semantic"
        if not (adapter / "config_schema.py").is_file():
            self.record("adapter", "adapter", "self-check", "failed",
                        note="memory/plugin/holographic-semantic/config_schema.py is missing: pull the commit that "
                             "has the adapter changes (RUNBOOK-HERMES.md S0.4)")
            return
        env = {k: v for k, v in self.env.items() if k != "PYTHONPATH"}
        self.step("adapter-catalog", "adapter", "self-check", [self.testpy, "memory/plugin/test_catalog.py"], PROJECT,
                  env=env, expect="ok × 10")
        self.step("adapter-sidecar-sync", "adapter", "self-check", [self.testpy, "memory/sidecar/test_sync.py"],
                  PROJECT, env=env, expect="ok × 4")

    # the Hermes PRs

    def state(self, name):
        spec = plan.STATES[name]
        self.reset_hermes()
        self.built = ""
        for patch in spec["patches"]:
            if not self.git(f"{name}-apply-{patch}", self.hermes, "apply", "--whitespace=nowarn",
                            str(DOCS / "patches" / plan.PATCHES[patch]), state=name):
                return
        subprocess.run(["git", "-C", str(self.hermes), "add", "-A"], check=True)
        desktop = self.hermes / "apps" / "desktop"
        expect = spec.get("expect", "")
        self.step(f"{name}-check", name, "check", ["python", "scripts/check", "--staged"], self.hermes, parse_check)
        if spec.get("backend"):
            self.step(f"{name}-backend", name, "backend",
                      ["bash", "scripts/run_tests.sh", "--jobs", str(self.args.jobs), *spec["backend"]],
                      self.hermes, parse_backend, expect=expect)
        vitest = ["pnpm", "exec", "vitest", "run", f"--maxWorkers={self.args.jobs}"]
        if spec.get("vitest"):
            self.step(f"{name}-vitest", name, "vitest", [*vitest, *spec["vitest"]], desktop,
                      parse_vitest, expect=expect)
        if spec.get("electron"):
            self.step(f"{name}-vitest-electron", name, "vitest",
                      [*vitest, "--project", "electron", "electron/connection-config.test.ts"],
                      desktop, parse_vitest, expect="126 passed")
        if spec.get("typecheck"):
            self.step(f"{name}-typecheck", name, "typecheck", ["pnpm", "run", "typecheck"], desktop)
        if spec.get("lint"):
            self.step(f"{name}-lint", name, "lint", ["pnpm", "run", "lint"], desktop, expect="0 errors")
        if self.args.skip_e2e:
            return
        if spec.get("e2e"):
            self.e2e(name, f"{name}-e2e", list(spec["e2e"]))
        if spec.get("adapter_e2e"):
            self.adapter_e2e(name)

    def adapter_e2e(self, state, extra=None):
        desktop = self.hermes / "apps" / "desktop"
        for filename in ("real-adapter.local.spec.ts", "real-sidecar-fixture.ts"):
            shutil.copyfile(DOCS / filename, desktop / "e2e" / filename)
        env = {"HERMES_OPTIMIZATION_ROOT": str(PROJECT), "MEMORY_REVIEW_SHOTS": str(self.out / "screenshots"),
               "HOLOGRAPHIC_SRC": str(self.holo_base), "SEED_PYTHON": self.testpy}
        self.e2e(state, f"{state}-adapter-e2e", ["e2e/real-adapter.local.spec.ts"], dict(env, **(extra or {})))

    def live(self):
        """Build the combined candidate and drive the settings job using the actual BGE-M3 sidecar."""
        self.reset_hermes()
        if not self.git("live-apply-all", self.hermes, "apply", "--whitespace=nowarn",
                        str(DOCS / "hermes-agent-memory-review.patch"), state="live"):
            return
        self.adapter_e2e("live", {"MEMORY_REVIEW_SIDECAR_PYTHON": str(self.args.sidecar_python),
                                 "MEMORY_REVIEW_BGE_MODEL_DIR": str(self.args.bge_model_dir)})

    def e2e(self, state, name, specs, extra=None):
        desktop = self.hermes / "apps" / "desktop"
        if self.built != state:
            if not self.step(f"{state}-desktop-build", state, "build", ["pnpm", "run", "build"], desktop):
                return
            self.built = state
        prefix = []
        if SYSTEM == "linux" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            if not shutil.which("xvfb-run"):
                self.record(name, state, "e2e", "failed", note="no display and no xvfb-run: install xvfb (README)")
                return
            prefix = ["xvfb-run", "-a", "--server-args=-screen 0 1280x1024x24"]
        env = dict(self.env, **(extra or {}))
        # A PM-provisioned checkout has no repo .venv for Electron's source backend to discover.
        env["HERMES_DESKTOP_PYTHON"] = self.testpy
        self.step(name, state, "e2e", [*prefix, "pnpm", "exec", "playwright", "test", *specs], desktop,
                  parse_playwright, env=env, timeout=3600)

    # the report

    def write_report(self):
        self.out.mkdir(parents=True, exist_ok=True)
        data = {"meta": self.meta, "steps": self.steps}
        (self.out / "report.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        counts = {s: sum(1 for step in self.steps if step["status"] == s) for s in ("passed", "known", "failed")}
        lines = [f"# Test report: {self.meta['platform']}", ""]
        lines += [f"- {key}: `{value}`" for key, value in self.meta.items()]
        lines += ["", f"**{counts['passed']} passed, {counts['known']} known failures, {counts['failed']} failed**", "",
                  "| Step | Status | Result | Expected | s |", "|---|---|---|---|---|"]
        for step in self.steps:
            result = (step["summary"] or step["note"]).replace("|", "/")
            lines.append(f"| {step['step']} | {step['status']} | {result} | {step['expect']} | {step['seconds']} |")
        for step in (s for s in self.steps if s["status"] in ("failed", "known")):
            lines += ["", f"## {step['step']} ({step['status']})", "", step["note"] or "", f"Log: `{step['log']}`", ""]
            lines += [f"- `{failure}`" for failure in step["failures"]]
        (self.out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # a GBK or cp1252 console cannot print every character a tool emits
        stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--work", default=str(Path.home() / "hkit"), help="where everything is fetched and installed")
    parser.add_argument("--only", default="", help=f"comma-separated subset of: {', '.join(ORDER)}; or 'live' by itself")
    parser.add_argument("--skip-e2e", action="store_true", help="no desktop build, no Electron tests")
    parser.add_argument("--quick", action="store_true", help="skip the holographic plugin's full suite (~10 min)")
    parser.add_argument("-j", "--jobs", type=int, default=4, help="maximum Vitest and backend workers (default: 4)")
    parser.add_argument("--hermes-ref", default=plan.HERMES_BASE, help="Hermes commit or branch (default: the pin)")
    parser.add_argument("--holo-ref", default=plan.HOLO_BASE, help="holographic commit (default: the pin)")
    parser.add_argument("--sidecar-python", type=Path, help="separate Python with memory/sidecar requirements (live only)")
    parser.add_argument("--bge-model-dir", type=Path, help="local BAAI/bge-m3 weights and tokenizer (live only)")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be a positive integer")
    if args.only == "live":
        if args.skip_e2e or args.sidecar_python is None or args.bge_model_dir is None:
            parser.error("--only live requires --sidecar-python and --bge-model-dir, and runs Electron")
        # Do not resolve a venv launcher symlink to the base Python (common on macOS).
        args.sidecar_python = args.sidecar_python.expanduser().absolute()
        args.bge_model_dir = args.bge_model_dir.expanduser().resolve()
        if not args.sidecar_python.is_file() or not (args.bge_model_dir / "modules.json").is_file():
            parser.error("provide an existing sidecar Python and a complete local BGE-M3 SentenceTransformer folder")
        selected = ["live"]
    else:
        if args.sidecar_python is not None or args.bge_model_dir is not None:
            parser.error("sidecar arguments require --only live")
        requested = set(args.only.split(",")) if args.only else set(ORDER)
        if requested - set(ORDER):
            parser.error(f"unknown --only selection: {', '.join(sorted(requested - set(ORDER)))}")
        selected = [name for name in ORDER if name in requested]
    kit = Kit(args)
    shutil.rmtree(kit.out, ignore_errors=True)
    kit.logs.mkdir(parents=True)
    try:
        kit.prepare()
        kit.provision()
        for name in selected:
            {"holo": kit.holo, "adapter": kit.adapter, "live": kit.live}.get(name, lambda n=name: kit.state(n))()
    except KeyboardInterrupt:
        kit.meta["interrupted"] = True
    finally:
        kit.meta["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
        kit.write_report()
    failed = [step["step"] for step in kit.steps if step["status"] == "failed"]
    print(f"\nreport: {kit.out / 'report.md'}" + (f"\nfailed: {', '.join(failed)}" if failed else "\nno failures"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
