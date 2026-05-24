"""Unit tests for Git operations in modsmith/git_ops.py."""

import unittest
import tempfile
import shutil
from pathlib import Path

from modsmith.git_ops import (
    git_init,
    git_create_orphan_branch,
    git_clear_working_tree,
    git_add_all,
    git_commit,
    git_checkout,
    git_current_branch,
    git_list_branches,
    write_gitignore,
)


class TestGitOps(unittest.TestCase):
    """Verify that all wrap Git subprocess commands function correctly on local disk."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name) / "test_repo"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_git_init_and_gitignore(self):
        git_init(self.repo_dir)
        self.assertTrue((self.repo_dir / ".git").exists())

        write_gitignore(self.repo_dir)
        gitignore_file = self.repo_dir / ".gitignore"
        self.assertTrue(gitignore_file.exists())
        content = gitignore_file.read_text(encoding="utf-8")
        self.assertIn(".gradle/", content)
        self.assertIn("build/", content)

    def test_git_branch_lifecycle_and_commits(self):
        git_init(self.repo_dir)

        # Write dummy file to commit
        dummy_file = self.repo_dir / "test.txt"
        dummy_file.write_text("Hello Git", encoding="utf-8")

        # Create orphan branch
        branch_name = "test-branch"
        git_create_orphan_branch(self.repo_dir, branch_name)

        current = git_current_branch(self.repo_dir)
        self.assertEqual(current, branch_name)

        # Add and commit
        git_add_all(self.repo_dir)
        git_commit(self.repo_dir, "Initial dummy commit")

        branches = git_list_branches(self.repo_dir)
        self.assertIn(branch_name, branches)

        # Create a second branch
        second_branch = "second-branch"
        # Since git 2.23+ allows orphan branch creation, let's create a second one
        git_create_orphan_branch(self.repo_dir, second_branch)
        dummy_file_2 = self.repo_dir / "second.txt"
        dummy_file_2.write_text("Hello second branch", encoding="utf-8")
        git_add_all(self.repo_dir)
        git_commit(self.repo_dir, "Second dummy commit")

        branches = git_list_branches(self.repo_dir)
        self.assertIn(second_branch, branches)

        # Checkout first branch
        git_checkout(self.repo_dir, branch_name)
        current = git_current_branch(self.repo_dir)
        self.assertEqual(current, branch_name)

    def test_git_clear_working_tree(self):
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        # Setup files inside and a .git dir
        (self.repo_dir / ".git").mkdir()
        (self.repo_dir / ".git" / "config").write_text("dummy config", encoding="utf-8")
        (self.repo_dir / "src").mkdir()
        (self.repo_dir / "src" / "Main.java").write_text("class Main {}", encoding="utf-8")
        (self.repo_dir / "README.md").write_text("Read me", encoding="utf-8")

        # Clear it
        git_clear_working_tree(self.repo_dir)

        # .git should be spared
        self.assertTrue((self.repo_dir / ".git").exists())
        self.assertTrue((self.repo_dir / ".git" / "config").exists())

        # Everything else should be deleted
        self.assertFalse((self.repo_dir / "src").exists())
        self.assertFalse((self.repo_dir / "README.md").exists())


if __name__ == "__main__":
    unittest.main()
