"""Standard-library regression tests for the testkit runner (python -m unittest -v test_run)."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import run


class TestKitCommands(unittest.TestCase):
    def setUp(self):
        self.kit = run.Kit.__new__(run.Kit)
        self.kit.hermes = Path("kit-hermes")
        self.kit.testpy = str(Path("kit-test-venv/python").resolve())
        self.kit.env = {"HERMES_HOME": "kit-home"}
        self.kit.args = SimpleNamespace(jobs=3, skip_e2e=True)
        self.kit.step = Mock()

    def test_jobs_caps_backend_and_both_vitest_projects(self):
        self.kit.reset_hermes = Mock()
        self.kit.git = Mock(return_value=True)
        with patch.object(run.subprocess, "run"):
            self.kit.state("pr4")
        commands = {call.args[0]: call.args[3] for call in self.kit.step.call_args_list}
        self.assertEqual(commands["pr4-backend"][:4], ["bash", "scripts/run_tests.sh", "--jobs", "3"])
        for name in ("pr4-vitest", "pr4-vitest-electron"):
            self.assertIn("--maxWorkers=3", commands[name])
            self.assertFalse(any(arg.startswith("--minWorkers") for arg in commands[name]))

    def test_pr7_includes_i18n_coverage(self):
        self.kit.reset_hermes = Mock()
        self.kit.git = Mock(return_value=True)
        with patch.object(run.subprocess, "run"):
            self.kit.state("pr7")
        vitest = next(call.args[3] for call in self.kit.step.call_args_list if call.args[0] == "pr7-vitest")
        self.assertIn("src/i18n", vitest)
        self.assertIn("scripts/i18n-keys.test.mjs", vitest)

    def test_e2e_uses_pm_test_interpreter_without_leaking_into_other_steps(self):
        self.kit.built = "all"
        with patch.object(run, "SYSTEM", "windows"):
            self.kit.e2e("all", "all-adapter-e2e", ["e2e/real-adapter.local.spec.ts"], {"HOLOGRAPHIC_SRC": "holo-base"})
        call = self.kit.step.call_args
        self.assertEqual(call.args[3][:4], ["pnpm", "exec", "playwright", "test"])
        self.assertEqual(call.kwargs["env"], {"HERMES_HOME": "kit-home", "HOLOGRAPHIC_SRC": "holo-base",
                                             "HERMES_DESKTOP_PYTHON": self.kit.testpy})
        self.assertNotIn("HERMES_DESKTOP_PYTHON", self.kit.env)

    def test_live_applies_the_combined_patch_and_passes_both_sidecar_inputs(self):
        self.kit.reset_hermes = Mock()
        self.kit.git = Mock(return_value=True)
        self.kit.adapter_e2e = Mock()
        self.kit.args.sidecar_python = Path("test-venv/python")
        self.kit.args.bge_model_dir = Path("bge-m3")
        self.kit.live()
        self.assertTrue(self.kit.git.call_args.args[-1].endswith("hermes-agent-memory-review.patch"))
        self.kit.adapter_e2e.assert_called_once_with("live", {
            "MEMORY_REVIEW_SIDECAR_PYTHON": str(self.kit.args.sidecar_python),
            "MEMORY_REVIEW_BGE_MODEL_DIR": "bge-m3",
        })
        self.assertNotIn("live", run.ORDER)


class TestWindowsKnownFailure(unittest.TestCase):
    failure = ("FAILED tests/plugins/memory/test_byterover_multiplex_child_env.py::"
               "test_secondary_profile_child_uses_its_own_key_not_defaults")
    windows_path = r"\opt\brv\bin;C:\Windows"
    output = (f'>       assert env["PATH"].startswith("/opt/brv/bin")\n'
              f'E       AssertionError: assert False\n'
              f'E        +  where False = <method>(\'/opt/brv/bin\')\n'
              f'E        +    where <method> = {windows_path!r}.startswith\n\n'
              f'{failure}\n')

    def test_expected_windows_path_failure_is_known(self):
        with patch.object(run, "SYSTEM", "windows"):
            self.assertTrue(run.Kit._known("backend", self.failure, self.output))

    def test_same_test_failing_for_any_other_reason_is_not_known(self):
        with patch.object(run, "SYSTEM", "windows"):
            self.assertFalse(run.Kit._known("backend", self.failure, 'E KeyError: "BRV_API_KEY"'))
            self.assertFalse(run.Kit._known("backend", self.failure, self.output.replace(repr(self.windows_path), "'C:/Wrong'")))
            self.assertFalse(run.Kit._known("backend", self.failure.replace("secondary", "primary"), self.output))
        with patch.object(run, "SYSTEM", "linux"):
            self.assertFalse(run.Kit._known("backend", self.failure, self.output))


if __name__ == "__main__":
    unittest.main()
