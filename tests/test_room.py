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
            self.assertEqual(profile["provider"], spec["providerId"])
            self.assertEqual(profile["model"], entry["model"])
            self.assertEqual(profile["modeId"], entry["modeId"])
            self.assertEqual(profile["featureValues"], {"auto_accept": entry["autoAccept"]})
            self.assertTrue(profile["notes"].strip())
            self.assertIn("~/.config/amp-room/", profile["notes"])


class ProviderMergeTest(unittest.TestCase):
    def test_creates_provider_when_missing(self):
        spec = load_spec()
        config = minimal_config()
        changed = room.merge_provider(config, spec)
        self.assertTrue(changed)
        entry = config["agents"]["providers"][spec["providerId"]]
        self.assertEqual(entry["command"], spec["provider"]["command"])
        self.assertIs(entry["enabled"], True)

    def test_never_touches_existing_provider(self):
        spec = load_spec()
        config = minimal_config(provider=True)
        original = {"extends": "acp", "command": ["amp-acp"], "env": {"AMP_CLI_PATH": "X:\\amp.exe"}}
        config["agents"]["providers"][spec["providerId"]] = dict(original)
        changed = room.merge_provider(config, spec)
        self.assertFalse(changed)
        self.assertEqual(config["agents"]["providers"][spec["providerId"]], original)


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
        other = {"id": "agent_profile_other", "name": "Operator profile", "provider": "amp-acp"}
        config["daemon"]["agentProfiles"].append(other)
        desired = room.render_profiles(load_spec())
        room.merge_profiles(config, desired)
        lead = next(p for p in config["daemon"]["agentProfiles"] if p["name"] == "SLP - Lead")
        # Change one desired note and re-merge: same id, same slot, unrelated profile kept.
        desired[1] = dict(desired[1], notes=desired[1]["notes"] + "\nUpdated.")
        changed = room.merge_profiles(config, desired)
        self.assertTrue(changed)
        self.assertEqual(
            next(p for p in config["daemon"]["agentProfiles"] if p["name"] == "SLP - Lead")["id"],
            lead["id"],
        )
        self.assertIn(other, config["daemon"]["agentProfiles"])

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
        self.assertFalse(room.unmerge_profiles(config, ["SLP - Lead"]))


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
        room.merge_profiles(config, desired)
        room.write_config_atomic(self.paseo_home / "config.json", config)
        room.install_protocol(self.home)
        self.assertEqual(room.verify_installed(self.home, spec, desired), [])

        config = room.read_config(self.home)
        room.unmerge_profiles(config, [e["name"] for e in spec["agentProfiles"]])
        room.write_config_atomic(self.paseo_home / "config.json", config)
        problems = room.verify_installed(self.home, spec, desired)
        self.assertEqual(len(problems), 3)  # all three room profiles missing

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