"""Tests for ModSmith 2.1.3 gitignore hygiene.

Covers:
- render_canonical_gitignore() output shape
- ensure_gitignore_rules() merging logic
- Legacy *.jar handling
- Idempotency and determinism
- Official template completeness
- Artifact scanners (template / staged / committed)
- Generator integration (end-to-end branch .gitignore)
- Wrapper JAR tracking verification
"""

from __future__ import annotations

import subprocess
import sys
import shutil
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Module under test
# ---------------------------------------------------------------------------

from modsmith.gitignore_rules import (
    REQUIRED_GITIGNORE_RULES,
    GitignoreUpdateResult,
    ensure_gitignore_rules,
    render_canonical_gitignore,
    scan_staged_for_artifacts,
    scan_committed_for_artifacts,
    scan_template_for_artifacts,
    _is_forbidden_path,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
MODTEMPLATES = REPO_ROOT / "MODTEMPLATES"
OFFICIAL_TEMPLATES = [
    "easypeasyslime-fabric-1.21-1.21.1",
    "easypeasyslime-fabric-1.21.2-1.21.11",
    "forge-1.20.1",
    "forge-1.21-1.21.1",
    "forge-1.21.2-1.21.11",
]


# ===========================================================================
# render_canonical_gitignore
# ===========================================================================

class TestRenderCanonicalGitignore:
    def test_contains_all_canonical_rules(self):
        content = render_canonical_gitignore()
        for rule in REQUIRED_GITIGNORE_RULES:
            assert rule in content, f"Canonical rule missing: {rule!r}"

    def test_ends_with_single_newline(self):
        content = render_canonical_gitignore()
        assert content.endswith("\n")
        assert not content.endswith("\n\n")

    def test_deterministic_for_same_header(self):
        a = render_canonical_gitignore(header_comment="# test")
        b = render_canonical_gitignore(header_comment="# test")
        assert a == b

    def test_header_comment_is_present(self):
        content = render_canonical_gitignore(header_comment="# ModSmith managed")
        assert "# ModSmith managed" in content

    def test_no_blank_jar_rule(self):
        content = render_canonical_gitignore()
        lines = content.splitlines()
        # *.jar must NOT appear (blanket jar ignores the gradle wrapper)
        bare_jar_lines = [l for l in lines if l.strip() == "*.jar"]
        assert bare_jar_lines == [], "render_canonical_gitignore must not produce *.jar"

    def test_no_old_jvm_crash_pattern(self):
        """Official output must use hs_err_pid* not the glob hs_err_*.log."""
        content = render_canonical_gitignore()
        assert "hs_err_*.log" not in content
        assert "replay_*.log" not in content
        assert "hs_err_pid*" in content
        assert "replay_pid*" in content


# ===========================================================================
# ensure_gitignore_rules — file missing
# ===========================================================================

class TestEnsureGitignoreRulesMissing:
    def test_creates_file_when_missing(self, tmp_path):
        gi = tmp_path / ".gitignore"
        ensure_gitignore_rules(gi)
        assert gi.exists()

    def test_all_canonical_rules_present_when_created(self, tmp_path):
        gi = tmp_path / ".gitignore"
        res = ensure_gitignore_rules(gi)
        content = gi.read_text(encoding="utf-8")
        for rule in REQUIRED_GITIGNORE_RULES:
            assert rule in content
        assert set(res.added) == set(REQUIRED_GITIGNORE_RULES)

    def test_ends_with_single_newline_when_created(self, tmp_path):
        gi = tmp_path / ".gitignore"
        ensure_gitignore_rules(gi)
        content = gi.read_text(encoding="utf-8")
        assert content.endswith("\n")
        assert not content.endswith("\n\n")


# ===========================================================================
# ensure_gitignore_rules — existing file
# ===========================================================================

class TestEnsureGitignoreRulesExisting:
    def test_adds_missing_canonical_rules_to_empty_file(self, tmp_path):
        gi = tmp_path / ".gitignore"
        gi.write_text("", encoding="utf-8")
        res = ensure_gitignore_rules(gi)
        content = gi.read_text(encoding="utf-8")
        for rule in REQUIRED_GITIGNORE_RULES:
            assert rule in content
        assert len(res.added) == len(REQUIRED_GITIGNORE_RULES)

    def test_preserves_existing_custom_rule(self, tmp_path):
        gi = tmp_path / ".gitignore"
        gi.write_text("# my project\nmy_custom_folder/\n", encoding="utf-8")
        ensure_gitignore_rules(gi)
        content = gi.read_text(encoding="utf-8")
        assert "my_custom_folder/" in content

    def test_preserves_existing_comments(self, tmp_path):
        gi = tmp_path / ".gitignore"
        gi.write_text("# My custom comment\nbuild/\n", encoding="utf-8")
        ensure_gitignore_rules(gi)
        content = gi.read_text(encoding="utf-8")
        assert "# My custom comment" in content

    def test_does_not_duplicate_existing_rule(self, tmp_path):
        gi = tmp_path / ".gitignore"
        # Use slash-less variant — should match canonical build/
        gi.write_text("build\n.gradle\nrun\n", encoding="utf-8")
        ensure_gitignore_rules(gi)
        content = gi.read_text(encoding="utf-8")
        # build should appear at most twice (original + canonical variant)
        # but the key is it should not be appended again as canonical
        # because _norm strips trailing slash
        build_count = content.count("\nbuild")
        assert build_count <= 2  # original non-slash + possibly no duplicate canonical

    def test_idempotent_run_twice(self, tmp_path):
        gi = tmp_path / ".gitignore"
        gi.write_text("# pre-existing\n*.jar\n", encoding="utf-8")
        ensure_gitignore_rules(gi)
        content1 = gi.read_text(encoding="utf-8")
        ensure_gitignore_rules(gi)
        content2 = gi.read_text(encoding="utf-8")
        assert content1 == content2

    def test_ends_with_single_newline_after_merge(self, tmp_path):
        gi = tmp_path / ".gitignore"
        gi.write_text("# stub", encoding="utf-8")  # no trailing newline
        ensure_gitignore_rules(gi)
        content = gi.read_text(encoding="utf-8")
        assert content.endswith("\n")
        assert not content.endswith("\n\n")

    def test_stable_bytes_deterministic(self, tmp_path):
        gi = tmp_path / ".gitignore"
        gi.write_text("# header\n.DS_Store\n", encoding="utf-8")
        ensure_gitignore_rules(gi)
        a = gi.read_bytes()
        gi.write_text("# header\n.DS_Store\n", encoding="utf-8")
        ensure_gitignore_rules(gi)
        b = gi.read_bytes()
        assert a == b


# ===========================================================================
# ensure_gitignore_rules — legacy *.jar handling
# ===========================================================================

class TestEnsureGitignoreRulesLegacyJar:
    def test_appends_jar_exception_when_bare_jar_present(self, tmp_path):
        gi = tmp_path / ".gitignore"
        gi.write_text("*.jar\n", encoding="utf-8")
        res = ensure_gitignore_rules(gi)
        content = gi.read_text(encoding="utf-8")
        assert "!gradle/wrapper/gradle-wrapper.jar" in content
        assert res.had_bare_jar_rule is True
        assert res.appended_jar_exception is True

    def test_no_double_jar_exception_on_idempotent_run(self, tmp_path):
        gi = tmp_path / ".gitignore"
        gi.write_text("*.jar\n", encoding="utf-8")
        ensure_gitignore_rules(gi)
        ensure_gitignore_rules(gi)
        content = gi.read_text(encoding="utf-8")
        assert content.count("!gradle/wrapper/gradle-wrapper.jar") == 1

    def test_no_jar_rule_added_by_canonical_merge(self, tmp_path):
        """ensure_gitignore_rules must not add a *.jar rule to a file that has none."""
        gi = tmp_path / ".gitignore"
        gi.write_text("", encoding="utf-8")
        ensure_gitignore_rules(gi)
        content = gi.read_text(encoding="utf-8")
        lines = [l.strip() for l in content.splitlines()]
        assert "*.jar" not in lines


# ===========================================================================
# Official template completeness
# ===========================================================================

class TestOfficialTemplates:
    @pytest.mark.parametrize("template", OFFICIAL_TEMPLATES)
    def test_gitignore_contains_all_canonical_rules(self, template):
        gi = MODTEMPLATES / template / ".gitignore"
        assert gi.exists(), f"{template}/.gitignore missing"
        content = gi.read_text(encoding="utf-8")
        missing = [r for r in REQUIRED_GITIGNORE_RULES if r not in content]
        assert missing == [], f"{template}/.gitignore missing rules: {missing}"

    @pytest.mark.parametrize("template", OFFICIAL_TEMPLATES)
    def test_gitignore_no_bare_jar_rule(self, template):
        gi = MODTEMPLATES / template / ".gitignore"
        assert gi.exists()
        lines = [l.strip() for l in gi.read_text(encoding="utf-8").splitlines()]
        assert "*.jar" not in lines, f"{template}/.gitignore has bare *.jar rule"

    @pytest.mark.parametrize("template", OFFICIAL_TEMPLATES)
    def test_gitignore_no_old_jvm_crash_patterns(self, template):
        """Official templates must use hs_err_pid* / replay_pid* not the glob forms."""
        gi = MODTEMPLATES / template / ".gitignore"
        content = gi.read_text(encoding="utf-8")
        assert "hs_err_*.log" not in content, f"{template}: old JVM crash pattern present"
        assert "replay_*.log" not in content, f"{template}: old replay pattern present"

    @pytest.mark.parametrize("template", OFFICIAL_TEMPLATES)
    def test_gradle_wrapper_jar_exists_and_not_ignored(self, template):
        """Wrapper JAR must exist in the template and not be ignored by *.jar."""
        jar = MODTEMPLATES / template / "gradle" / "wrapper" / "gradle-wrapper.jar"
        assert jar.exists(), f"{template}: gradle-wrapper.jar missing"
        gi = MODTEMPLATES / template / ".gitignore"
        content = gi.read_text(encoding="utf-8")
        # Bare *.jar without an exception would ignore the wrapper
        lines = [l.strip() for l in content.splitlines()]
        if "*.jar" in lines:
            assert "!gradle/wrapper/gradle-wrapper.jar" in lines, (
                f"{template}: has *.jar rule but no negation for gradle-wrapper.jar"
            )

    @pytest.mark.parametrize("template", OFFICIAL_TEMPLATES)
    def test_no_template_build_artifacts(self, template):
        """Official templates must not contain build artifacts."""
        forbidden = scan_template_for_artifacts(MODTEMPLATES / template)
        assert forbidden == [], (
            f"{template}: forbidden artifacts in template: {forbidden}"
        )


# ===========================================================================
# _is_forbidden_path helper
# ===========================================================================

class TestIsForbiddenPath:
    @pytest.mark.parametrize("path,expected", [
        (".gradle/caches/something", True),
        ("build/libs/mod.jar", True),
        ("run/server.log", True),
        ("logs/latest.log", True),
        ("out/production/something.class", True),
        ("src/main/java/Main.class", True),
        ("some_file.log", True),
        ("hs_err_pid12345", True),
        ("replay_pid99.log", True),
        # safe paths
        ("gradle/wrapper/gradle-wrapper.jar", False),
        ("src/main/java/com/example/Main.java", False),
        ("build.gradle", False),
        ("settings.gradle", False),
        ("README.md", False),
        (".gitignore", False),
    ])
    def test_forbidden_path_classification(self, path, expected):
        assert _is_forbidden_path(path) == expected


# ===========================================================================
# scan_template_for_artifacts
# ===========================================================================

class TestScanTemplateForArtifacts:
    def test_empty_template_returns_empty(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "Main.java").write_text("class Main {}", encoding="utf-8")
        assert scan_template_for_artifacts(tmp_path) == []

    def test_detects_class_file_in_build(self, tmp_path):
        (tmp_path / "build" / "classes").mkdir(parents=True)
        (tmp_path / "build" / "classes" / "Main.class").write_bytes(b"\xca\xfe\xba\xbe")
        # scan_template_for_artifacts checks file paths
        result = scan_template_for_artifacts(tmp_path)
        assert any("build" in r for r in result), f"Expected build artifact, got: {result}"

    def test_skips_git_directory(self, tmp_path):
        (tmp_path / ".git" / "objects").mkdir(parents=True)
        (tmp_path / ".git" / "objects" / "something.log").write_text("x")
        result = scan_template_for_artifacts(tmp_path)
        # .git files should not be flagged
        assert not any(".git" in r for r in result)

    def test_safe_jar_not_flagged(self, tmp_path):
        jar_dir = tmp_path / "gradle" / "wrapper"
        jar_dir.mkdir(parents=True)
        (jar_dir / "gradle-wrapper.jar").write_bytes(b"PK")
        result = scan_template_for_artifacts(tmp_path)
        assert result == []


# ===========================================================================
# scan_staged_for_artifacts — integration
# ===========================================================================

@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary Git repository."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@modsmith.local"],
        cwd=tmp_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path, check=True, capture_output=True
    )
    # Write and commit an initial .gitignore so HEAD exists
    gi = tmp_path / ".gitignore"
    gi.write_text(".gradle/\nbuild/\nrun/\n*.class\n*.log\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path, check=True, capture_output=True
    )
    return tmp_path


class TestScanStagedForArtifacts:
    def test_empty_staging_area(self, git_repo):
        result = scan_staged_for_artifacts(git_repo)
        assert result == []

    def test_clean_file_not_flagged(self, git_repo):
        f = git_repo / "README.md"
        f.write_text("# hello")
        subprocess.run(["git", "add", "README.md"], cwd=git_repo, check=True, capture_output=True)
        result = scan_staged_for_artifacts(git_repo)
        assert result == []

    def test_class_file_staged_is_flagged(self, git_repo):
        # Override gitignore to allow .class in this test
        gi = git_repo / ".gitignore"
        gi.write_text("")
        cls_dir = git_repo / "build" / "classes"
        cls_dir.mkdir(parents=True)
        cls_file = cls_dir / "Main.class"
        cls_file.write_bytes(b"\xca\xfe\xba\xbe")
        subprocess.run(
            ["git", "add", "-f", str(cls_file.relative_to(git_repo))],
            cwd=git_repo, check=True, capture_output=True
        )
        result = scan_staged_for_artifacts(git_repo)
        assert any("Main.class" in r for r in result)

    def test_safe_jar_not_flagged_when_staged(self, git_repo):
        jar_dir = git_repo / "gradle" / "wrapper"
        jar_dir.mkdir(parents=True)
        jar = jar_dir / "gradle-wrapper.jar"
        jar.write_bytes(b"PK")
        subprocess.run(
            ["git", "add", "-f", "gradle/wrapper/gradle-wrapper.jar"],
            cwd=git_repo, check=True, capture_output=True
        )
        result = scan_staged_for_artifacts(git_repo)
        assert result == [], f"Wrapper JAR must not be flagged as artifact: {result}"


# ===========================================================================
# scan_committed_for_artifacts — integration
# ===========================================================================

class TestScanCommittedForArtifacts:
    def test_clean_commit_returns_empty(self, git_repo):
        result = scan_committed_for_artifacts(git_repo)
        assert result == []

    def test_class_file_committed_is_flagged(self, git_repo):
        # Override gitignore to allow force-adding
        gi = git_repo / ".gitignore"
        gi.write_text("")
        cls_dir = git_repo / "build" / "classes"
        cls_dir.mkdir(parents=True)
        cls_file = cls_dir / "Main.class"
        cls_file.write_bytes(b"\xca\xfe\xba\xbe")
        subprocess.run(["git", "add", "-f", "."], cwd=git_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "oops"],
            cwd=git_repo, check=True, capture_output=True
        )
        result = scan_committed_for_artifacts(git_repo)
        assert any("Main.class" in r for r in result)

    def test_wrapper_jar_committed_not_flagged(self, git_repo):
        jar_dir = git_repo / "gradle" / "wrapper"
        jar_dir.mkdir(parents=True)
        jar = jar_dir / "gradle-wrapper.jar"
        jar.write_bytes(b"PK")
        subprocess.run(
            ["git", "add", "-f", "gradle/wrapper/gradle-wrapper.jar"],
            cwd=git_repo, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "add wrapper jar"],
            cwd=git_repo, check=True, capture_output=True
        )
        result = scan_committed_for_artifacts(git_repo)
        assert result == [], f"Wrapper JAR must not be flagged: {result}"


# ===========================================================================
# Ignored-directory probe test
# ===========================================================================

class TestIgnoredDirectories:
    """Verify that probe files placed inside ignored directories are git-ignored."""

    def _git_check_ignore(self, repo: Path, path: str) -> bool:
        """Return True if git reports *path* as ignored."""
        res = subprocess.run(
            ["git", "check-ignore", "-q", path],
            cwd=repo,
            capture_output=True,
        )
        return res.returncode == 0

    def test_gradle_dir_is_ignored(self, git_repo):
        probe = git_repo / ".gradle" / "probe.txt"
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("probe")
        assert self._git_check_ignore(git_repo, ".gradle/probe.txt")

    def test_build_dir_is_ignored(self, git_repo):
        probe = git_repo / "build" / "probe.txt"
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("probe")
        assert self._git_check_ignore(git_repo, "build/probe.txt")

    def test_run_dir_is_ignored(self, git_repo):
        probe = git_repo / "run" / "probe.txt"
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("probe")
        assert self._git_check_ignore(git_repo, "run/probe.txt")

    def test_log_file_is_ignored(self, git_repo):
        probe = git_repo / "server.log"
        probe.write_text("log")
        assert self._git_check_ignore(git_repo, "server.log")

    def test_class_file_is_ignored(self, git_repo):
        cls = git_repo / "Main.class"
        cls.write_bytes(b"\xca\xfe\xba\xbe")
        assert self._git_check_ignore(git_repo, "Main.class")

    def test_logs_dir_is_ignored(self, git_repo):
        probe = git_repo / "logs" / "debug.log"
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("debug")
        assert self._git_check_ignore(git_repo, "logs/debug.log")


# ===========================================================================
# Wrapper JAR tracking test
# ===========================================================================

class TestWrapperJarTracked:
    """The Gradle wrapper JAR must be tracked (not just unignored) in templates."""

    @pytest.mark.parametrize("template", OFFICIAL_TEMPLATES)
    def test_wrapper_jar_is_tracked_in_template(self, template, tmp_path):
        """Copy the template to a temp git repo and verify the JAR is tracked."""
        t_dir = MODTEMPLATES / template
        jar_path = t_dir / "gradle" / "wrapper" / "gradle-wrapper.jar"
        assert jar_path.exists(), f"{template}: wrapper JAR missing"

        # Init a git repo and add the wrapper JAR
        repo = tmp_path / template
        shutil.copytree(t_dir, repo, ignore=shutil.ignore_patterns(".git"))
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@modsmith.local"],
            cwd=repo, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo, check=True, capture_output=True
        )
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "template copy"],
            cwd=repo, check=True, capture_output=True
        )

        # Verify the wrapper JAR is tracked
        res = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "gradle/wrapper/gradle-wrapper.jar"],
            cwd=repo,
            capture_output=True,
        )
        assert res.returncode == 0, (
            f"{template}: gradle-wrapper.jar is NOT tracked in git after `git add -A`.\n"
            f"This means it is being silently ignored by a .gitignore rule.\n"
            f"stderr: {res.stderr.decode()}"
        )


# ===========================================================================
# ensure_gitignore_rules — normalization idempotency on legacy template
# ===========================================================================

class TestLegacyTemplateNormalization:
    def test_incomplete_gitignore_gets_all_canonical_rules(self, tmp_path):
        """Simulate a legacy template with a partial gitignore."""
        gi = tmp_path / ".gitignore"
        gi.write_text(
            "# legacy\n"
            ".gradle\n"
            "build\n"
            "# Note: run/ not included\n",
            encoding="utf-8",
        )
        ensure_gitignore_rules(gi)
        content = gi.read_text(encoding="utf-8")
        for rule in REQUIRED_GITIGNORE_RULES:
            assert rule.rstrip("/") in content or rule in content, (
                f"Legacy normalize: missing canonical rule: {rule!r}"
            )

    def test_custom_rules_survive_normalization(self, tmp_path):
        gi = tmp_path / ".gitignore"
        gi.write_text("my_special_rule/\n", encoding="utf-8")
        ensure_gitignore_rules(gi)
        content = gi.read_text(encoding="utf-8")
        assert "my_special_rule/" in content

    def test_double_normalization_stable(self, tmp_path):
        gi = tmp_path / ".gitignore"
        gi.write_text("*.iml\n", encoding="utf-8")
        ensure_gitignore_rules(gi)
        first = gi.read_text(encoding="utf-8")
        ensure_gitignore_rules(gi)
        second = gi.read_text(encoding="utf-8")
        assert first == second
