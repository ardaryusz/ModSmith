"""Unit tests for modsmith.utils.

Covers:
- is_valid_mod_id
- is_valid_java_identifier
- is_valid_java_package
- to_class_name
"""

import unittest

from modsmith.utils import (
    is_valid_mod_id,
    is_valid_java_identifier,
    is_valid_java_package,
    to_class_name,
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


if __name__ == "__main__":
    unittest.main()
