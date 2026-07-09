"""Unit tests for modsmith.utils.

Covers:
- is_valid_mod_id
- is_valid_java_identifier
- is_valid_java_package
- to_class_name
"""

import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modsmith.utils import (
    is_valid_mod_id,
    is_valid_java_identifier,
    is_valid_java_package,
    safe_delete_tree,
    to_class_name,
    run_process,
    set_hide_windows,
)


class TestIsValidModId(unittest.TestCase):
    """Tests for is_valid_mod_id."""

    # -- valid cases -----------------------------------------------------------

    def test_simple_lowercase(self):
        self.assertTrue(is_valid_mod_id("mymod"))

    def test_with_digits(self):
        self.assertTrue(is_valid_mod_id("mymod123"))

    def test_with_underscore(self):
        self.assertTrue(is_valid_mod_id("my_mod"))

    def test_single_letter(self):
        self.assertTrue(is_valid_mod_id("a"))

    def test_real_mod_id(self):
        self.assertTrue(is_valid_mod_id("easypeasygunpowder"))

    # -- invalid cases ---------------------------------------------------------

    def test_uppercase_letter(self):
        self.assertFalse(is_valid_mod_id("MyMod"))

    def test_all_uppercase(self):
        self.assertFalse(is_valid_mod_id("MYMOD"))

    def test_starts_with_digit(self):
        self.assertFalse(is_valid_mod_id("1mymod"))

    def test_contains_space(self):
        self.assertFalse(is_valid_mod_id("my mod"))

    def test_contains_hyphen(self):
        self.assertFalse(is_valid_mod_id("my-mod"))

    def test_contains_dot(self):
        self.assertFalse(is_valid_mod_id("my.mod"))

    def test_empty_string(self):
        self.assertFalse(is_valid_mod_id(""))

    def test_only_digits(self):
        self.assertFalse(is_valid_mod_id("123"))


class TestIsValidJavaIdentifier(unittest.TestCase):
    """Tests for is_valid_java_identifier."""

    # -- valid cases -----------------------------------------------------------

    def test_simple_name(self):
        self.assertTrue(is_valid_java_identifier("myVar"))

    def test_pascal_case(self):
        self.assertTrue(is_valid_java_identifier("EasyPeasyGunpowder"))

    def test_starts_with_underscore(self):
        self.assertTrue(is_valid_java_identifier("_myVar"))

    def test_starts_with_dollar(self):
        self.assertTrue(is_valid_java_identifier("$myVar"))

    def test_contains_digits(self):
        self.assertTrue(is_valid_java_identifier("myVar2"))

    def test_all_uppercase(self):
        self.assertTrue(is_valid_java_identifier("MYMOD"))

    # -- keyword cases ---------------------------------------------------------

    def test_keyword_class(self):
        self.assertFalse(is_valid_java_identifier("class"))

    def test_keyword_int(self):
        self.assertFalse(is_valid_java_identifier("int"))

    def test_keyword_new(self):
        self.assertFalse(is_valid_java_identifier("new"))

    def test_literal_true(self):
        self.assertFalse(is_valid_java_identifier("true"))

    def test_literal_false(self):
        self.assertFalse(is_valid_java_identifier("false"))

    def test_literal_null(self):
        self.assertFalse(is_valid_java_identifier("null"))

    # -- invalid format cases --------------------------------------------------

    def test_starts_with_digit(self):
        self.assertFalse(is_valid_java_identifier("1myVar"))

    def test_contains_dot(self):
        self.assertFalse(is_valid_java_identifier("my.Var"))

    def test_contains_hyphen(self):
        self.assertFalse(is_valid_java_identifier("my-Var"))

    def test_contains_space(self):
        self.assertFalse(is_valid_java_identifier("my Var"))

    def test_empty_string(self):
        self.assertFalse(is_valid_java_identifier(""))


class TestIsValidJavaPackage(unittest.TestCase):
    """Tests for is_valid_java_package."""

    # -- valid cases -----------------------------------------------------------

    def test_two_segments(self):
        self.assertTrue(is_valid_java_package("com.example"))

    def test_three_segments(self):
        self.assertTrue(is_valid_java_package("com.example.mymod"))

    def test_real_package(self):
        self.assertTrue(is_valid_java_package("com.ardaryusz.easypeasygunpowder"))

    def test_mixed_case_segments(self):
        # Java identifiers allow uppercase; we don't enforce lowercase convention.
        self.assertTrue(is_valid_java_package("com.Example.mymod"))

    # -- invalid cases ---------------------------------------------------------

    def test_single_segment(self):
        self.assertFalse(is_valid_java_package("mymod"))

    def test_empty_string(self):
        self.assertFalse(is_valid_java_package(""))

    def test_segment_starts_with_digit(self):
        self.assertFalse(is_valid_java_package("com.1example"))

    def test_segment_with_hyphen(self):
        self.assertFalse(is_valid_java_package("com.my-mod"))

    def test_segment_is_keyword(self):
        # "class" is a Java keyword — not a valid identifier.
        self.assertFalse(is_valid_java_package("com.class.mymod"))

    def test_trailing_dot(self):
        self.assertFalse(is_valid_java_package("com.example."))

    def test_leading_dot(self):
        self.assertFalse(is_valid_java_package(".com.example"))

    def test_double_dot(self):
        self.assertFalse(is_valid_java_package("com..example"))


class TestToClassName(unittest.TestCase):
    """Tests for to_class_name."""

    def test_space_separated(self):
        self.assertEqual(to_class_name("Easy Peasy Gunpowder"), "EasyPeasyGunpowder")

    def test_already_pascal(self):
        self.assertEqual(to_class_name("MyMod"), "MyMod")

    def test_underscore_separated(self):
        self.assertEqual(to_class_name("my_mod_name"), "MyModName")

    def test_hyphen_separated(self):
        self.assertEqual(to_class_name("my-mod-name"), "MyModName")

    def test_mixed_separators(self):
        self.assertEqual(to_class_name("my mod-name_test"), "MyModNameTest")

    def test_trailing_numbers(self):
        result = to_class_name("cool mod 2")
        self.assertEqual(result, "CoolMod2")

    def test_starts_with_digit_after_stripping(self):
        # A name that strips to a digit-starting result should get "Mod" prepended.
        result = to_class_name("2cool mod")
        self.assertTrue(result.startswith("Mod") or not result[0].isdigit(),
                        msg=f"Result '{result}' starts with a digit")

    def test_single_word(self):
        self.assertEqual(to_class_name("mymod"), "Mymod")

    def test_extra_whitespace(self):
        self.assertEqual(to_class_name("  Easy   Peasy  "), "EasyPeasy")

    def test_real_mod_name(self):
        result = to_class_name("Easy Peasy Gunpowder")
        self.assertEqual(result, "EasyPeasyGunpowder")


class TestSafeDeleteTree(unittest.TestCase):
    """Tests for safe_delete_tree."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_deletes_normal_directory(self):
        target = self.root / "normal_dir"
        target.mkdir()
        (target / "file.txt").write_text("hello", encoding="utf-8")
        (target / "subdir").mkdir()
        (target / "subdir" / "nested.txt").write_text("world", encoding="utf-8")

        safe_delete_tree(target)

        self.assertFalse(target.exists())

    def test_deletes_directory_with_readonly_files(self):
        """Mirrors the Windows [WinError 5] scenario: .git/objects are read-only."""
        target = self.root / "repo_with_readonly"
        git_obj_dir = target / ".git" / "objects" / "ab"
        git_obj_dir.mkdir(parents=True)
        readonly_file = git_obj_dir / "cd1234ef"
        readonly_file.write_bytes(b"packed object content")

        # Make the file read-only (simulates Git object files on Windows)
        readonly_file.chmod(stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)

        safe_delete_tree(target)

        self.assertFalse(target.exists())

    def test_does_nothing_when_path_missing(self):
        missing = self.root / "does_not_exist"
        # Must not raise
        safe_delete_tree(missing)

    def test_raises_clear_error_when_deletion_still_fails(self):
        """If rmtree leaves the path intact, safe_delete_tree raises OSError
        with an actionable message."""
        target = self.root / "stubborn_dir"
        target.mkdir()
        (target / "x.txt").write_text("x", encoding="utf-8")

        import sys
        if sys.version_info >= (3, 12):
            rmtree_kwarg = "onexc"
        else:
            rmtree_kwarg = "onerror"

        # Patch shutil.rmtree so it does nothing (simulating a locked handle)
        with patch("modsmith.utils.shutil.rmtree"):
            with self.assertRaises(OSError) as ctx:
                safe_delete_tree(target)

        msg = str(ctx.exception)
        # Message should guide the user
        self.assertIn("Could not fully delete", msg)
        self.assertIn("Gradle daemons", msg)

class TestRunProcess(unittest.TestCase):
    """Tests for run_process helper and hidden window flags."""

    def test_run_process_captures_stdout_stderr(self):
        import sys
        # Run a simple Python command that prints to stdout and stderr
        cmd = [sys.executable, "-c", "import sys; sys.stdout.write('hello'); sys.stderr.write('world')"]
        res = run_process(cmd, capture_output=True)
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout, "hello")
        self.assertEqual(res.stderr, "world")

    def test_run_process_exit_code_preserved(self):
        import sys
        cmd = [sys.executable, "-c", "import sys; sys.exit(42)"]
        res = run_process(cmd, capture_output=True)
        self.assertEqual(res.returncode, 42)

    def test_run_process_missing_executable_raises_error(self):
        with self.assertRaises(FileNotFoundError):
            run_process(["nonexistent_executable_12345"])

    def test_run_process_does_not_use_shell(self):
        # Verify subprocess.run or Popen is called without shell=True
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = unittest.mock.MagicMock()
            run_process(["dummy"])
            _, kwargs = mock_run.call_args
            self.assertFalse(kwargs.get("shell", False))

        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = unittest.mock.MagicMock()
            run_process(["dummy"], on_log_line=lambda l: None)
            _, kwargs = mock_popen.call_args
            self.assertFalse(kwargs.get("shell", False))

    def test_run_process_merges_and_streams_without_deadlock(self):
        import sys
        # Generate heavy stderr and stdout output to test deadlock prevention
        script = "import sys; sys.stdout.write('o' * 100000); sys.stderr.write('e' * 100000)"
        cmd = [sys.executable, "-c", script]
        
        lines = []
        def log_cb(line):
            lines.append(line)

        res = run_process(cmd, on_log_line=log_cb)
        self.assertEqual(res.returncode, 0)
        total_len = sum(len(l) for l in lines)
        self.assertGreater(total_len, 190000)
        self.assertEqual(res.stderr, "")

    def test_windows_hidden_process_flags_applied(self):
        import sys
        from modsmith.utils import run_process, set_hide_windows
        
        # Test A: hide_window=True
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = unittest.mock.MagicMock()
            run_process(["dummy"], hide_window=True)
            _, kwargs = mock_run.call_args
            if sys.platform == "win32":
                self.assertIn("creationflags", kwargs)
                self.assertEqual(kwargs["creationflags"], 0x08000000)
            else:
                self.assertNotIn("creationflags", kwargs)

        # Test B: hide_window=False (default visible)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = unittest.mock.MagicMock()
            run_process(["dummy"], hide_window=False)
            _, kwargs = mock_run.call_args
            self.assertNotIn("creationflags", kwargs)
            self.assertNotIn("startupinfo", kwargs)

        # Test C: set_hide_windows(True) globally
        try:
            set_hide_windows(True)
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = unittest.mock.MagicMock()
                run_process(["dummy"], hide_window=False)
                _, kwargs = mock_run.call_args
                if sys.platform == "win32":
                    self.assertIn("creationflags", kwargs)
                    self.assertEqual(kwargs["creationflags"], 0x08000000)
                else:
                    self.assertNotIn("creationflags", kwargs)
        finally:
            set_hide_windows(False)

    def test_gui_import_does_not_toggle_hidden_mode(self):
        from modsmith.utils import _hide_windows_globally
        self.assertFalse(_hide_windows_globally)
        
        import modsmith_gui.app
        import modsmith_gui.workers
        from modsmith.utils import _hide_windows_globally as val
        self.assertFalse(val)

    def test_run_app_startup_enables_hidden_mode(self):
        from modsmith.utils import _hide_windows_globally, set_hide_windows
        self.assertFalse(_hide_windows_globally)
        
        with patch("modsmith_gui.app.QApplication"), \
             patch("modsmith_gui.main_window.MainWindow"):
            try:
                from modsmith_gui.app import run_app
                run_app()
                from modsmith.utils import _hide_windows_globally as val
                self.assertTrue(val)
            finally:
                set_hide_windows(False)


if __name__ == "__main__":
    unittest.main()
