"""Exercise the launch script shipped on the camera SD card."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
try:
    spec = importlib.util.spec_from_file_location("roll_log_launcher", SCRIPTS / "package_gr3_roll_log.py")
    packager = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(packager)
finally:
    sys.path.pop(0)


class RollLogLauncherTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.service = root / "service"
        self.service.mkdir()
        self.logs = root / "log"
        self.logs.mkdir()
        self.lock = root / "boot-lock"
        self.ram = root / "worker-ram.log"
        self.ram_copy = root / "worker-ram-copy.log"
        self.script = packager.LOG_START
        for path, stand_in in (
            ("/tmp/m10v-worker-1101.log", self.ram),
            ("/media/storage1/M10V/R16RAM.TXT", self.ram_copy),
            ("/media/storage1/SCRIPT/MCW1101", self.service),
            ("/media/storage1/M10V", self.logs),
            ("/tmp/m10v-companion-1101.lock", self.lock),
        ):
            self.script = self.script.replace(path.encode(), str(stand_in).encode())

    def launch(self):
        return subprocess.run(["sh"], input=self.script, capture_output=True).returncode

    def install(self, exit_code):
        executable = self.service / "SERVICE.BIN"
        executable.write_text(f"#!/bin/sh\necho ROLL_EXEC\necho ROLL_WORKER\nexit {exit_code}\n")
        executable.chmod(0o700)

    def log(self):
        path = self.logs / 'R16BOOT.TXT'
        return path.read_text().splitlines() if path.exists() else []

    def wait_for(self, marker):
        until = time.monotonic() + 2
        while time.monotonic() < until:
            lines = self.log()
            if marker in lines:
                return lines
            time.sleep(0.01)
        self.fail('missing supervisor marker ' + marker)

    def test_waits_for_the_executable_and_launches_once(self):
        self.install(0)
        self.assertEqual(self.launch(), 0)
        self.assertTrue(self.lock.exists())
        log = self.wait_for("R16_SERVICE_EXIT_0")
        self.assertIn("R16_EXEC_SD_BEGIN", log)
        self.assertIn("ROLL_EXEC", log)
        self.assertIn("R16_EXEC_SD_END_0", log)
        self.assertEqual(self.launch(), 0)
        self.assertEqual(self.log(), log)

    def test_repeated_loader_snapshots_ram_without_restarting_service(self):
        self.install(0)
        self.assertEqual(self.launch(), 0)
        self.wait_for('R16_SERVICE_EXIT_0')
        self.ram.write_text('R16_ENTRY_BEFORE_SD\nPROCESS_START\n')
        self.assertEqual(self.launch(), 0)
        self.assertEqual(self.ram_copy.read_text(), self.ram.read_text())
        self.assertEqual(self.log().count('ROLL_EXEC'), 1)
        self.assertIn('R16_RAM_COPIED', self.log())
        self.assertTrue(any(line.startswith('R16_IMAGE_SHA256 ') or
                            line == 'R16_IMAGE_SHA256_UNAVAILABLE' for line in self.log()))

    def test_launcher_returns_while_sole_service_remains_alive(self):
        gate = self.service / 'finish'
        executable = self.service / 'SERVICE.BIN'
        executable.write_text('#!/bin/sh\necho ROLL_WORKER\n'
                              'while [ ! -f "' + str(gate) + '" ]; do sleep 0.02; done\n')
        executable.chmod(0o700)
        process = subprocess.Popen(['sh'], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            try:
                process.communicate(self.script, timeout=0.5)
            except subprocess.TimeoutExpired:
                self.fail('launcher waits for worker termination instead of supervising in background')
            self.assertEqual(process.returncode, 0)
            self.assertFalse(gate.exists())
        finally:
            gate.touch()
            process.communicate(timeout=2)
            self.wait_for("R16_SERVICE_EXIT_0")

    def test_only_pre_worker_failure_releases_the_boot_lock(self):
        self.assertEqual(self.launch(), 1)
        self.assertFalse(self.lock.exists())
        self.assertIn("R16_IMAGE_UNREADABLE", self.log())
        self.install(1)
        self.assertEqual(self.launch(), 0)
        lines = self.wait_for('R16_SERVICE_EXIT_1')
        self.assertTrue(self.lock.exists())
        self.assertIn('R16_EXEC_SD_END_1', lines)
        self.assertIn('R16_IMAGE_UNREADABLE', lines)
        self.assertEqual(self.launch(), 0)
        self.assertEqual(self.log(), lines)

    def test_readable_but_non_executable_sd_file_uses_ram_copy(self):
        self.install(0)
        (self.service / "SERVICE.BIN").chmod(0o600)
        self.assertEqual(self.launch(), 0)
        text = self.wait_for("R16_SERVICE_EXIT_0")
        self.assertIn("R16_EXEC_SD_END_126", text)
        self.assertIn("R16_EXEC_TMP_BEGIN", text)
        self.assertIn("R16_EXEC_TMP_END_0", text)
        self.assertEqual(text.count("ROLL_WORKER"), 1)
