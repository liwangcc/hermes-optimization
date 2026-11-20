"""What the test kit verifies: the pinned bases, each Hermes PR's patch stack and its tests (RUNBOOK-HERMES.md
section 5), the holographic HOLO-1 checks, the adapter's self-checks, and the failures already known on an
untouched base."""

HERMES_URL = "https://github.com/NousResearch/hermes-agent.git"
HERMES_BASE = "152fe18976002e9a987422b7c6102c805d61264b"  # main on 2026-11-19, the base every patch was made on
HOLO_URL = "https://github.com/itpartypattaya/hermes-plugin-holographic.git"
HOLO_BASE = "76689f954f500d49a7ef2eb73d0e868a5b43b53e"  # 0.30.1, the base of holo-1-config-schema.patch
# audio-io brings numpy into Hermes' own test environment: the holographic suite and the sidecar self-check need it.
TEST_EXTRAS = "all,audio-io"

PATCHES = {
    "01": "01-profile-families.patch",
    "02": "02-composer-offers.patch",
    "03": "03-memory-capacity.patch",
    "04": "04-memory-checkup.patch",
    "05": "05-checkup-reminder.patch",
    "06": "06-catalog-suggestion.patch",
    "07": "07-memory-provider-jobs.patch",
    "all": "../hermes-agent-memory-review.patch",
}
HOLO_PATCH = "holo-1-config-schema.patch"

_PR1_VITEST = (
    "src/store/session-states.test.ts", "src/store/session-states-profile-rename.test.ts",
    "src/store/session-tiles-connection-scope.test.ts", "src/store/composer-queued-pick.test.ts",
    "src/store/preview-status-edge-cases.test.ts", "src/store/preview-status-lifecycle.test.ts",
    "src/lib/browser-profile-prefs.test.ts", "src/lib/browser-desktop-bridge-saved-connections.test.ts",
    "src/sdk/profile-routing.test.ts", "src/sdk/open-session-refresh-in-place.test.ts",
    "src/app/profiles/rename-profile-dialog.test.tsx",
)
_I18N = ("src/i18n", "scripts/i18n-keys.test.mjs")

# One state per PR: apply patches in order to a clean base. "expect" documents the pinned Windows test scope.
STATES = {
    "pr1": {"patches": ("01",), "vitest": _PR1_VITEST, "typecheck": True,
            "expect": "vitest 11 files / 210 tests"},
    "pr2": {"patches": ("02",), "vitest": ("src/app/chat/composer/status-stack",), "typecheck": True,
            "expect": "vitest 15 files / 42 tests"},
    "pr3": {"patches": ("03",), "backend": ("tests/hermes_cli/test_web_memory_layers.py",),
            "vitest": ("src/app/settings/memory", "src/app/command-center", *_I18N), "typecheck": True,
            "expect": "backend 6; vitest 21 files / 119 tests"},
    "pr4": {"patches": ("03", "04"),
            "backend": ("tests/agent/test_memory_checkup.py", "tests/hermes_cli/test_web_memory_checkup.py",
                        "tests/hermes_cli/test_serve_handler_ledger.py"),
            "vitest": ("src/app/command-center", "src/store/memory-checkup.test.ts", "src/app/settings/memory", *_I18N),
            "electron": True, "e2e": ("e2e/memory-checkup.spec.ts",),
            "expect": "vitest 23 files / 126 tests; electron 126"},
    "pr5": {"patches": ("01", "02", "03", "04", "05"),
            "vitest": ("src/store/memory-checkup-reminder.test.ts", "src/components/memory-checkup",
                       "src/app/command-center", "src/app/chat/composer/status-stack"),
            "e2e": ("e2e/memory-checkup.spec.ts", "e2e/boot.spec.ts"), "expect": "e2e passed"},
    "pr6": {"patches": ("03", "04", "06"),
            "backend": ("tests/hermes_cli/test_web_memory_layers.py", "tests/hermes_cli/test_web_memory_checkup.py"),
            "vitest": ("src/app/settings/memory", *_I18N), "expect": "backend 12; vitest 18 files / 111 tests"},
    "pr7": {"patches": ("07",),
            "backend": ("tests/hermes_cli/test_memory_actions.py", "tests/hermes_cli/test_serve_handler_ledger.py",
                        "tests/ci/test_docs_drift.py"),
            "vitest": ("src/app/settings/memory", *_I18N), "electron": True, "e2e": ("e2e/memory-provider-jobs.spec.ts",),
            "typecheck": True, "expect": "vitest 18 files / 106 tests; electron 126"},
    # All seven together: the neighbours of every module the patches touch, lint, and the real adapter in the app.
    "all": {"patches": ("all",),
            "backend": ("tests/hermes_cli/test_web_memory_layers.py", "tests/hermes_cli/test_web_memory_checkup.py",
                        "tests/agent/test_memory_checkup.py", "tests/hermes_cli/test_memory_actions.py",
                        "tests/hermes_cli/test_serve_handler_ledger.py", "tests/ci/test_docs_drift.py",
                        "tests/agent/test_memory_provider.py", "tests/tools/test_memory_tool.py",
                        "tests/hermes_cli/test_web_server.py", "tests/hermes_cli/test_memory_setup.py",
                        "tests/hermes_cli/test_memory_provider_seams_hosted.py",
                        "tests/hermes_cli/test_memory_provider_core_sentinels.py",
                        "tests/hermes_cli/test_web_memory_provider_setup_install.py",
                        "tests/hermes_cli/test_profile_memory_config.py", "tests/plugins/memory"),
            "vitest": ("src/app/settings/memory", "src/app/command-center", "src/store", "src/components/memory-checkup",
                       "src/app/chat/composer/status-stack", *_I18N),
            "typecheck": True, "lint": True, "adapter_e2e": True, "expect": "lint 0 errors; adapter e2e 2 passed"},
}

# Failures reproduced on the untouched base: (step kind, text in the failure, platforms, why, optional log regex).
KNOWN = (
    ("backend", "FAILED tests/plugins/memory/test_byterover_multiplex_child_env.py::"
     "test_secondary_profile_child_uses_its_own_key_not_defaults", {"windows"},
     "POSIX PATH assertion on a correct Windows path; fails on untouched main",
     r'''(?m)^>[ \t]+assert env\["PATH"\]\.startswith\("/opt/brv/bin"\)\n'''
     r'''E[ \t]+AssertionError: assert False\nE[^\n]*\nE[^\n]*= '\\\\opt\\\\brv\\\\bin;'''),
    ("backend", "TestMemoryFileLockPermissions", {"windows"}, "NTFS has no POSIX mode bits; fails on untouched main"),
    ("check", "shims", {"windows"}, "fails on untouched main on Windows"),
    ("check", "line-endings", {"windows"}, "fails on untouched main on Windows (times out after 120 s)"),
    ("check", "no-tmp", {"windows", "macos", "linux"}, "plugin-catalog/layersift.yaml, a catalog entry on main"),
)
