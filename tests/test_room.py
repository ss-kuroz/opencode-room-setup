"""Tests for scripts/room.py merge, render, and uninstall logic."""

import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "config" / "room.json"

spec_module = importlib.util.spec_from_file_location("room", REPO_ROOT / "scripts" / "room.py")
room = importlib.util.module_from_spec(spec_module)
spec_module.loader.exec_module(room)


def load_spec():
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def minimal_config(provider: bool = False) -> dict:
    config = {"version": 1, "daemon": {"listen": "127.0.0.1:6767", "agentProfiles": []}, "agents": {}}
    if provider:
        config["agents"]["providers"] = {}
    return config


class RenderTest(unittest.TestCase):
    def test_renders_one_profile_per_spec_entry(self):
        spec = load_spec()
        profiles = room.render_profiles(spec)
        self.assertEqual([p["name"] for p in profiles], [e["name"] for e in spec["agentProfiles"]])
        for profile, entry in zip(profiles, spec["agentProfiles"]):
            self.assertEqual(profile["provider"], entry["providerId"])
            self.assertEqual(profile["model"], entry["model"])
            self.assertEqual(profile["thinkingOptionId"], entry["thinkingOptionId"])
            self.assertEqual(profile["modeId"], entry["modeId"])
            self.assertEqual(profile["featureValues"], {"auto_accept": entry["autoAccept"]})
            self.assertTrue(profile["notes"].strip())
            self.assertIn("~/.config/opencode-room/", profile["notes"])

    def test_every_profile_provider_is_declared(self):
        spec = load_spec()
        declared = {p["id"] for p in spec["providers"]}
        for entry in spec["agentProfiles"]:
            self.assertIn(entry["providerId"], declared)

    def test_renders_one_derived_provider_per_spec_entry(self):
        spec = load_spec()
        rendered = room.render_providers(spec)
        self.assertEqual(
            list(rendered), [p["id"] for p in spec["providers"]]
        )
        for entry in spec["providers"]:
            provider = rendered[entry["id"]]
            self.assertEqual(provider["extends"], spec["providerId"])
            self.assertEqual(provider["label"], entry["label"])
            self.assertEqual(provider["models"], entry["models"])
            self.assertNotIn("command", provider)

    def test_derived_provider_models_are_detached_from_the_spec(self):
        spec = load_spec()
        original = spec["providers"][0]["models"][0]["label"]
        rendered = room.render_providers(spec)
        rendered[spec["providers"][0]["id"]]["models"][0]["label"] = "mutated"
        self.assertEqual(spec["providers"][0]["models"][0]["label"], original)

    def test_render_omits_thinking_option_when_spec_lacks_it(self):
        spec = load_spec()
        for entry in spec["agentProfiles"]:
            entry.pop("thinkingOptionId", None)
        for profile in room.render_profiles(spec):
            self.assertNotIn("thinkingOptionId", profile)


class NativeAgentPolicyTest(unittest.TestCase):
    def test_derived_providers_disable_native_child_agents(self):
        spec = load_spec()
        self.assertIs(spec["nativeAgents"], False)
        for provider_id, provider in room.render_providers(spec).items():
            policy = json.loads(provider["env"][room.NATIVE_AGENT_ENV_KEY])
            self.assertIn(
                {"action": "subagent", "resource": "*", "effect": "deny"},
                policy["permissions"],
                provider_id,
            )
            for builtin_subagent in ("general", "explore"):
                self.assertIs(policy["agents"][builtin_subagent]["disabled"], True, provider_id)

    def test_base_provider_keeps_native_child_agents(self):
        spec = load_spec()
        entry = room.desired_provider_entry(spec)
        self.assertNotIn("env", entry)
        self.assertEqual(entry["enabled"], True)
        self.assertEqual(entry["command"]["mode"], "replace")

    def test_spec_can_keep_native_agents(self):
        spec = load_spec()
        spec["nativeAgents"] = True
        for provider in room.render_providers(spec).values():
            self.assertNotIn("env", provider)

    def test_overlay_is_stable_across_renders(self):
        spec = load_spec()
        self.assertEqual(
            room.render_providers(spec), room.render_providers(load_spec())
        )


class SpecValidationTest(unittest.TestCase):
    def test_shipped_spec_is_valid(self):
        self.assertEqual(room.validate_spec(load_spec()), [])

    def test_rejects_missing_or_non_boolean_native_agents(self):
        for bad in (None, "false", 0):
            spec = load_spec()
            if bad is None:
                spec.pop("nativeAgents")
            else:
                spec["nativeAgents"] = bad
            self.assertNotEqual(room.validate_spec(spec), [], bad)

    def test_rejects_provider_ids_paseo_cannot_derive(self):
        for bad in ("opencode", "OpenCode-Lead", "opencode_lead", "9lead"):
            spec = load_spec()
            spec["providers"][0]["id"] = bad
            self.assertTrue(room.validate_spec(spec), bad)

    def test_rejects_duplicate_provider_ids(self):
        spec = load_spec()
        spec["providers"][1]["id"] = spec["providers"][0]["id"]
        self.assertNotEqual(room.validate_spec(spec), [])

    def test_rejects_missing_label_or_empty_models(self):
        spec = load_spec()
        spec["providers"][0]["label"] = "  "
        self.assertNotEqual(room.validate_spec(spec), [])
        spec = load_spec()
        spec["providers"][0]["models"] = []
        self.assertNotEqual(room.validate_spec(spec), [])

    def test_rejects_two_defaults_in_one_catalog(self):
        spec = load_spec()
        models = spec["providers"][0]["models"]
        models.append(dict(models[0], id="ollama-cloud/other"))
        self.assertNotEqual(room.validate_spec(spec), [])
        spec = load_spec()
        for option in spec["providers"][0]["models"][0]["thinkingOptions"]:
            option["isDefault"] = True
        self.assertNotEqual(room.validate_spec(spec), [])

    def test_rejects_profile_naming_an_undeclared_provider(self):
        spec = load_spec()
        spec["agentProfiles"][0]["providerId"] = "opencode-ghost"
        self.assertNotEqual(room.validate_spec(spec), [])

    def test_rejects_duplicate_profile_names_and_roles(self):
        spec = load_spec()
        spec["agentProfiles"][1]["name"] = spec["agentProfiles"][0]["name"]
        self.assertNotEqual(room.validate_spec(spec), [])
        spec = load_spec()
        spec["agentProfiles"][1]["role"] = spec["agentProfiles"][0]["role"]
        self.assertNotEqual(room.validate_spec(spec), [])


class ResolveBinaryTest(unittest.TestCase):
    def test_resolves_npm_cmd_shim_to_packaged_exe(self):
        with tempfile.TemporaryDirectory() as tmp:
            shim = Path(tmp) / "opencode.cmd"
            shim.write_text(
                '@ECHO off\n'
                'GOTO start\n'
                ':find_dp0\n'
                'SET dp0=%~dp0\n'
                'EXIT /b\n'
                ':start\n'
                'SETLOCAL\n'
                'CALL :find_dp0\n'
                '"%dp0%\\node_modules\\@opencode\\cli\\bin\\opencode.exe"   %*\n',
                encoding="utf-8",
            )
            exe = Path(tmp) / "node_modules" / "@opencode" / "cli" / "bin" / "opencode.exe"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"stub")
            real_which = room.shutil.which
            room.shutil.which = lambda name: str(shim)
            try:
                self.assertEqual(room.resolve_opencode_binary(), str(exe))
            finally:
                room.shutil.which = real_which

    def test_missing_binary_fails_loud(self):
        real_which = room.shutil.which
        room.shutil.which = lambda name: None
        try:
            with self.assertRaises(room.RoomError):
                room.resolve_opencode_binary()
        finally:
            room.shutil.which = real_which

    def test_unresolvable_shim_fails_loud(self):
        with tempfile.TemporaryDirectory() as tmp:
            shim = Path(tmp) / "opencode.cmd"
            shim.write_text('@echo off\n', encoding="utf-8")
            real_which = room.shutil.which
            room.shutil.which = lambda name: str(shim)
            try:
                with self.assertRaises(room.RoomError):
                    room.resolve_opencode_binary()
            finally:
                room.shutil.which = real_which


class ProviderMergeTest(unittest.TestCase):
    def setUp(self):
        self._real_resolve = room.resolve_opencode_binary
        room.resolve_opencode_binary = lambda: "X:\\tools\\opencode.exe"

    def tearDown(self):
        room.resolve_opencode_binary = self._real_resolve

    def test_creates_managed_entry_when_missing(self):
        spec = load_spec()
        config = minimal_config()
        changed = room.merge_provider(config, spec)
        self.assertTrue(changed)
        entry = config["agents"]["providers"][spec["providerId"]]
        self.assertIs(entry["enabled"], True)
        self.assertEqual(entry["command"], {"mode": "replace", "argv": ["X:\\tools\\opencode.exe"]})

    def test_repairs_managed_keys_and_preserves_others(self):
        spec = load_spec()
        config = minimal_config(provider=True)
        config["agents"]["providers"][spec["providerId"]] = {
            "enabled": False,
            "env": {"X": "1"},
        }
        changed = room.merge_provider(config, spec)
        self.assertTrue(changed)
        entry = config["agents"]["providers"][spec["providerId"]]
        self.assertIs(entry["enabled"], True)
        self.assertEqual(entry["command"], {"mode": "replace", "argv": ["X:\\tools\\opencode.exe"]})
        self.assertEqual(entry["env"], {"X": "1"})

    def test_is_idempotent(self):
        spec = load_spec()
        config = minimal_config(provider=True)
        room.merge_provider(config, spec)
        before = json.dumps(config["agents"]["providers"][spec["providerId"]], sort_keys=True)
        changed = room.merge_provider(config, spec)
        self.assertFalse(changed)
        self.assertEqual(
            json.dumps(config["agents"]["providers"][spec["providerId"]], sort_keys=True), before
        )


class DerivedProviderMergeTest(unittest.TestCase):
    def test_creates_every_derived_entry(self):
        spec = load_spec()
        config = minimal_config()
        changed = room.merge_providers(config, spec)
        self.assertTrue(changed)
        desired = room.render_providers(spec)
        providers = config["agents"]["providers"]
        self.assertEqual(list(providers), list(desired))
        for provider_id, want in desired.items():
            self.assertEqual(providers[provider_id], want)

    def test_repairs_managed_keys_and_preserves_unrelated_ones(self):
        spec = load_spec()
        config = minimal_config(provider=True)
        target = spec["providers"][0]["id"]
        config["agents"]["providers"][target] = {
            "label": "stale",
            "enabled": False,
            "env": {"X": "1"},
            "paseoTools": {"enabled": False},
        }
        changed = room.merge_providers(config, spec)
        self.assertTrue(changed)
        entry = config["agents"]["providers"][target]
        self.assertEqual(entry["label"], spec["providers"][0]["label"])
        self.assertEqual(entry["extends"], spec["providerId"])
        self.assertEqual(entry["env"], room.native_agent_env())
        self.assertEqual(entry["paseoTools"], {"enabled": False})
        self.assertIs(entry["enabled"], False)

    def test_keeping_native_agents_drops_the_overlay(self):
        spec = load_spec()
        config = minimal_config(provider=True)
        room.merge_providers(config, spec)
        spec["nativeAgents"] = True
        self.assertTrue(room.merge_providers(config, spec))
        for provider in config["agents"]["providers"].values():
            self.assertNotIn("env", provider)

    def test_is_idempotent(self):
        spec = load_spec()
        config = minimal_config(provider=True)
        room.merge_providers(config, spec)
        before = json.dumps(config["agents"]["providers"], sort_keys=True)
        self.assertFalse(room.merge_providers(config, spec))
        self.assertEqual(json.dumps(config["agents"]["providers"], sort_keys=True), before)

    def test_drops_managed_keys_the_spec_no_longer_carries(self):
        spec = load_spec()
        config = minimal_config(provider=True)
        room.merge_providers(config, spec)
        target = spec["providers"][0]["id"]
        spec["providers"][0].pop("description")
        self.assertTrue(room.merge_providers(config, spec))
        self.assertNotIn("description", config["agents"]["providers"][target])

    def test_rejects_non_object_providers(self):
        config = {"agents": {"providers": []}}
        with self.assertRaises(room.RoomError):
            room.merge_providers(config, load_spec())

    def test_removes_only_derived_providers(self):
        spec = load_spec()
        config = minimal_config(provider=True)
        room.merge_providers(config, spec)
        config["agents"]["providers"]["operator-provider"] = {
            "extends": "acp",
            "label": "Operator provider",
            "command": ["whatever"],
        }
        changed = room.unmerge_providers(config, list(room.render_providers(spec)))
        self.assertTrue(changed)
        self.assertEqual(list(config["agents"]["providers"]), ["operator-provider"])

    def test_unmerge_is_a_noop_when_nothing_managed(self):
        config = minimal_config(provider=True)
        self.assertFalse(room.unmerge_providers(config, ["opencode-lead"]))


class ProfileMergeTest(unittest.TestCase):
    def test_adds_all_profiles_with_ids(self):
        config = minimal_config()
        changed = room.merge_profiles(config, room.render_profiles(load_spec()))
        self.assertTrue(changed)
        profiles = config["daemon"]["agentProfiles"]
        self.assertEqual(len(profiles), 3)
        for profile in profiles:
            self.assertTrue(profile["id"].startswith("agent_profile_"))
            self.assertNotIn("id", room.render_profiles(load_spec())[0])

    def test_is_idempotent(self):
        config = minimal_config()
        room.merge_profiles(config, room.render_profiles(load_spec()))
        before = json.dumps(config, sort_keys=True)
        changed = room.merge_profiles(config, room.render_profiles(load_spec()))
        self.assertFalse(changed)
        self.assertEqual(json.dumps(config, sort_keys=True), before)

    def test_update_preserves_id_and_position(self):
        config = minimal_config()
        other = {"id": "agent_profile_other", "name": "Operator profile", "provider": "opencode"}
        config["daemon"]["agentProfiles"].append(other)
        desired = room.render_profiles(load_spec())
        room.merge_profiles(config, desired)
        lead = next(p for p in config["daemon"]["agentProfiles"] if p["name"] == "opencode-lead")
        # Change one desired note and re-merge: same id, same slot, unrelated profile kept.
        desired[1] = dict(desired[1], notes=desired[1]["notes"] + "\nUpdated.")
        changed = room.merge_profiles(config, desired)
        self.assertTrue(changed)
        self.assertEqual(
            next(p for p in config["daemon"]["agentProfiles"] if p["name"] == "opencode-lead")["id"],
            lead["id"],
        )
        self.assertIn(other, config["daemon"]["agentProfiles"])

    def test_update_drops_managed_keys_missing_from_desired(self):
        config = minimal_config()
        desired = room.render_profiles(load_spec())
        room.merge_profiles(config, desired)
        peer = next(p for p in config["daemon"]["agentProfiles"] if p["name"] == "opencode-peer")
        self.assertEqual(peer["thinkingOptionId"], "low")
        trimmed = []
        for want in desired:
            entry = dict(want)
            if entry["name"] == "opencode-peer":
                entry.pop("thinkingOptionId")
            trimmed.append(entry)
        changed = room.merge_profiles(config, trimmed)
        self.assertTrue(changed)
        peer = next(p for p in config["daemon"]["agentProfiles"] if p["name"] == "opencode-peer")
        self.assertNotIn("thinkingOptionId", peer)

    def test_rejects_non_list_agentProfiles(self):
        config = {"daemon": {"agentProfiles": "nope"}}
        with self.assertRaises(room.RoomError):
            room.merge_profiles(config, room.render_profiles(load_spec()))


class DaemonReloadTest(unittest.TestCase):
    def test_reload_targets_the_paseo_home_not_the_operator_home(self):
        recorded = {}

        real_which = shutil.which
        real_run = subprocess.run

        def fake_which(name):
            return "paseo" if name == "paseo" else None

        def fake_run(cmd, **kwargs):
            recorded["cmd"] = cmd

            class Result:
                returncode = 0
                stderr = ""
                stdout = ""

            return Result()

        room.shutil.which = fake_which
        room.subprocess.run = fake_run
        try:
            note = room.daemon_reload(Path("/home/op"))
        finally:
            room.shutil.which = real_which
            room.subprocess.run = real_run
        self.assertEqual(note, "")
        self.assertEqual(
            recorded["cmd"],
            ["paseo", "--home", str(Path("/home/op") / ".paseo"), "daemon", "reload"],
        )


class UnmergeTest(unittest.TestCase):
    def test_removes_only_room_profiles(self):
        config = minimal_config()
        desired = room.render_profiles(load_spec())
        room.merge_profiles(config, desired)
        config["daemon"]["agentProfiles"].append(
            {"id": "agent_profile_keep", "name": "Operator profile"}
        )
        changed = room.unmerge_profiles(config, [p["name"] for p in desired])
        self.assertTrue(changed)
        self.assertEqual(
            [p["name"] for p in config["daemon"]["agentProfiles"]], ["Operator profile"]
        )

    def test_noop_when_nothing_managed(self):
        config = minimal_config()
        self.assertFalse(room.unmerge_profiles(config, ["opencode-lead"]))


class SyncFlowTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self.paseo_home = self.home / ".paseo"
        self.paseo_home.mkdir()
        (self.paseo_home / "config.json").write_text(
            json.dumps(minimal_config()), encoding="utf-8"
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_sync_then_verify_then_uninstall(self):
        spec = load_spec()
        desired = room.render_profiles(spec)
        config = room.read_config(self.home)
        room.merge_provider(config, spec)
        room.merge_providers(config, spec)
        room.merge_profiles(config, desired)
        room.write_config_atomic(self.paseo_home / "config.json", config)
        room.install_protocol(self.home)
        self.assertEqual(room.verify_installed(self.home, spec, desired), [])

        config = room.read_config(self.home)
        room.unmerge_profiles(config, [e["name"] for e in spec["agentProfiles"]])
        room.write_config_atomic(self.paseo_home / "config.json", config)
        problems = room.verify_installed(self.home, spec, desired)
        self.assertEqual(len(problems), 3)  # all three room profiles missing

    def test_verify_reports_derived_provider_drift(self):
        spec = load_spec()
        desired = room.render_profiles(spec)
        config = room.read_config(self.home)
        room.merge_provider(config, spec)
        room.merge_providers(config, spec)
        room.merge_profiles(config, desired)
        room.install_protocol(self.home)
        room.write_config_atomic(self.paseo_home / "config.json", config)
        config = room.read_config(self.home)
        target = spec["providers"][0]["id"]
        config["agents"]["providers"][target]["models"][0]["label"] = "drifted"
        room.write_config_atomic(self.paseo_home / "config.json", config)
        problems = room.verify_installed(self.home, spec, desired)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn(target, problems[0])
        self.assertIn("models", problems[0])

    def test_verify_reports_a_seat_that_regained_native_agents(self):
        spec = load_spec()
        desired = room.render_profiles(spec)
        config = room.read_config(self.home)
        room.merge_provider(config, spec)
        room.merge_providers(config, spec)
        room.merge_profiles(config, desired)
        room.install_protocol(self.home)
        room.write_config_atomic(self.paseo_home / "config.json", config)
        config = room.read_config(self.home)
        target = spec["providers"][1]["id"]
        config["agents"]["providers"][target].pop("env")
        room.write_config_atomic(self.paseo_home / "config.json", config)
        problems = room.verify_installed(self.home, spec, desired)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn(target, problems[0])
        self.assertIn("env", problems[0])

    def test_uninstall_removes_both_layers(self):
        spec = load_spec()
        desired = room.render_profiles(spec)
        config = room.read_config(self.home)
        room.merge_provider(config, spec)
        room.merge_providers(config, spec)
        room.merge_profiles(config, desired)
        room.write_config_atomic(self.paseo_home / "config.json", config)
        room.install_protocol(self.home)
        config = room.read_config(self.home)
        self.assertTrue(room.unmerge_providers(config, list(room.render_providers(spec))))
        self.assertTrue(room.unmerge_profiles(config, [e["name"] for e in spec["agentProfiles"]]))
        room.write_config_atomic(self.paseo_home / "config.json", config)
        problems = room.verify_installed(self.home, spec, desired)
        self.assertEqual(len(problems), 6)  # 3 derived providers + 3 profiles missing

    def test_protocol_install_is_idempotent_and_removable(self):
        self.assertTrue(room.install_protocol(self.home))
        self.assertFalse(room.install_protocol(self.home))
        self.assertTrue(room.remove_protocol(self.home))
        self.assertFalse((self.home / room.PROTOCOL_INSTALL_SUBPATH).exists())

    def test_read_config_fails_loud_without_paseo(self):
        empty_home = Path(tempfile.mkdtemp())
        try:
            with self.assertRaises(room.RoomError):
                room.read_config(empty_home)
        finally:
            empty_home.rmdir()

    def home_config(self):
        return room.read_config(self.home)


class SourceCheckTest(unittest.TestCase):
    def test_source_verify_passes(self):
        self.assertEqual(room.verify_sources(), [])


if __name__ == "__main__":
    unittest.main()