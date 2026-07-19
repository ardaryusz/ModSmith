"""Background worker threads for long-running ModSmith operations.

Each worker is a QThread subclass that:
 - Accepts the required parameters in its constructor (no GUI coupling).
 - Emits ``log_line(str)`` for individual log messages (INFO/WARN/ERROR prefixed).
 - Emits ``finished(bool, str)`` when done: (success, summary_message).
 - Never touches any widget directly — all UI updates go via signals.

Usage::

    worker = DoctorWorker(workspace_dir, templates_dir, mods_dir)
    worker.log_line.connect(log_panel.append_line)
    worker.finished.connect(self._on_doctor_finished)
    worker.start()
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal


class DoctorWorker(QThread):
    """Runs ``diagnose_environment`` in a background thread.

    Emits each INFO/WARN/ERROR message individually so the log panel
    fills in real-time rather than all at once on completion.
    """

    #: Emitted for every individual log line produced by the doctor.
    log_line: Signal = Signal(str)

    #: Emitted when the check is complete.
    #: Arguments: (success: bool, summary: str)
    finished: Signal = Signal(bool, str)

    def __init__(
        self,
        workspace_dir: Path,
        templates_dir: Path,
        mods_dir: Path,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._workspace_dir = workspace_dir
        self._templates_dir = templates_dir
        self._mods_dir = mods_dir

    # ------------------------------------------------------------------
    # QThread interface
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Execute doctor checks and emit results.  Runs on the worker thread."""
        from modsmith.doctor import diagnose_environment  # lazy import

        try:
            result = diagnose_environment(
                workspace_dir=self._workspace_dir,
                templates_dir=self._templates_dir,
                mods_dir=self._mods_dir,
            )
        except Exception as exc:  # pragma: no cover — safety net
            self.log_line.emit(f"[ERROR] Unexpected exception in doctor: {exc}")
            self.finished.emit(False, f"Doctor failed unexpectedly: {exc}")
            return

        # Emit each message in order: infos first, then warnings, then errors
        for info in result.infos:
            self.log_line.emit(f"[INFO]  {info}")
        for warn in result.warnings:
            self.log_line.emit(f"[WARN]  {warn}")
        for err in result.errors:
            self.log_line.emit(f"[ERROR] {err}")

        # Summary line
        if result.ok:
            summary = (
                f"Doctor OK — {len(result.warnings)} warning(s), "
                f"0 error(s)"
            )
        else:
            summary = (
                f"Doctor found {len(result.errors)} error(s), "
                f"{len(result.warnings)} warning(s)"
            )

        self.finished.emit(result.ok, summary)


# ---------------------------------------------------------------------------
# ValidateWorker
# ---------------------------------------------------------------------------


class ValidateWorker(QThread):
    """Runs ``validate_workspace`` in a background thread.

    Emits each validation error/warning individually and a summary on finish.
    """

    log_line: Signal = Signal(str)
    finished: Signal = Signal(bool, str)

    def __init__(
        self,
        workspace_dir: Path,
        templates_dir: Path,
        mods_dir: Path,
        *,
        force: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._workspace_dir = workspace_dir
        self._templates_dir = templates_dir
        self._mods_dir = mods_dir
        self._force = force

    def run(self) -> None:
        """Execute validation and emit results.  Runs on the worker thread."""
        from modsmith.validator import validate_workspace  # lazy import

        self.log_line.emit("[INFO]  Running workspace validation…")
        try:
            result = validate_workspace(
                workspace_dir=self._workspace_dir,
                templates_dir=self._templates_dir,
                mods_dir=self._mods_dir,
                force=self._force,
            )
        except Exception as exc:
            self.log_line.emit(f"[ERROR] Unexpected exception in validator: {exc}")
            self.finished.emit(False, f"Validation failed unexpectedly: {exc}")
            return

        for warn in result.warnings:
            self.log_line.emit(f"[WARN]  {warn}")
        for err in result.errors:
            self.log_line.emit(f"[ERROR] {err}")

        if result.ok:
            summary = (
                f"Validation passed — {len(result.warnings)} warning(s), "
                f"0 error(s)"
            )
        else:
            summary = (
                f"Validation failed — {len(result.errors)} error(s), "
                f"{len(result.warnings)} warning(s)"
            )
        self.finished.emit(result.ok, summary)


# ---------------------------------------------------------------------------
# GenerateWorker
# ---------------------------------------------------------------------------


class GenerateWorker(QThread):
    """Runs ``generator.generate`` in a background thread.

    The generator writes to the file system and may take a while; it does not
    have a streaming progress API so we emit a single start log line and then
    the result/error on completion.
    """

    log_line: Signal = Signal(str)
    finished: Signal = Signal(bool, str)

    def __init__(
        self,
        workspace_dir: Path,
        templates_dir: Path,
        mods_dir: Path,
        *,
        force: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._workspace_dir = workspace_dir
        self._templates_dir = templates_dir
        self._mods_dir = mods_dir
        self._force = force

    def run(self) -> None:
        """Execute generate and emit results.  Runs on the worker thread."""
        from modsmith.generator import generate, GenerateError  # lazy import

        mode = "force" if self._force else "normal"
        self.log_line.emit(f"[INFO]  Generating mod repository ({mode} mode)…")
        try:
            result = generate(
                workspace_dir=self._workspace_dir,
                templates_dir=self._templates_dir,
                mods_dir=self._mods_dir,
                force=self._force,
            )
        except GenerateError as exc:
            self.log_line.emit(f"[ERROR] {exc}")
            self.finished.emit(False, f"Generate failed: {exc}")
            return
        except Exception as exc:
            self.log_line.emit(f"[ERROR] Unexpected error during generate: {exc}")
            self.finished.emit(False, f"Generate failed unexpectedly: {exc}")
            return

        for warn in result.warnings:
            self.log_line.emit(f"[WARN]  {warn}")

        branch_list = ", ".join(result.generated_branches) or "(none)"
        self.log_line.emit(
            f"[INFO]  Generated branches: {branch_list}"
        )
        self.log_line.emit(f"[INFO]  Output repo: {result.repo_dir}")
        summary = (
            f"Generate complete — {len(result.generated_branches)} branch(es) generated"
        )
        self.finished.emit(True, summary)


# ---------------------------------------------------------------------------
# BuildWorker
# ---------------------------------------------------------------------------


class BuildWorker(QThread):
    """Runs ``builder.build`` in a background thread.

    The Gradle build can be very long-running; we emit start/finish lines and
    surface any BuildError messages to the log.
    """

    log_line: Signal = Signal(str)
    finished: Signal = Signal(bool, str)

    def __init__(
        self,
        workspace_dir: Path,
        mods_dir: Path,
        *,
        branch: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._workspace_dir = workspace_dir
        self._mods_dir = mods_dir
        self._branch = branch

    def run(self) -> None:
        """Execute build and emit results.  Runs on the worker thread."""
        from modsmith.builder import build, BuildError  # lazy import

        target = f"branch '{self._branch}'" if self._branch else "all branches"
        self.log_line.emit(f"[INFO]  Building {target} with Gradle…")
        self.log_line.emit("[INFO]  (This may take several minutes.)")
        try:
            def log_callback(line: str) -> None:
                self.log_line.emit(line)

            result = build(
                workspace_dir=self._workspace_dir,
                mods_dir=self._mods_dir,
                branch=self._branch,
                on_log_line=log_callback,
            )
        except BuildError as exc:
            self.log_line.emit(f"[ERROR] {exc}")
            self.finished.emit(False, f"Build failed: {exc}")
            return
        except Exception as exc:
            self.log_line.emit(f"[ERROR] Unexpected error during build: {exc}")
            self.finished.emit(False, f"Build failed unexpectedly: {exc}")
            return

        for warn in result.warnings:
            self.log_line.emit(f"[WARN]  {warn}")

        built = ", ".join(result.built_branches) or "(none)"
        self.log_line.emit(f"[INFO]  Built branches: {built}")
        if result.jar_map:
            self.log_line.emit("[INFO]  JARs collected:")
            for br, jar_path in result.jar_map.items():
                self.log_line.emit(f"[INFO]  - {br} -> {jar_path.name}")
        elif result.copied_jars:
            self.log_line.emit("[INFO]  JARs collected:")
            for jar_path in result.copied_jars:
                self.log_line.emit(f"[INFO]  - {jar_path.name}")
        summary = (
            f"Build complete — {len(result.built_branches)} branch(es), "
            f"{len(result.copied_jars)} JAR(s)"
        )
        self.finished.emit(True, summary)


# ---------------------------------------------------------------------------
# CleanWorker
# ---------------------------------------------------------------------------


class CleanWorker(QThread):
    """Runs ``cleaner.clean`` in a background thread.

    The GUI always calls with ``force=True`` — confirmation is handled by the
    screen *before* the worker is started (via QMessageBox.question).
    """

    log_line: Signal = Signal(str)
    finished: Signal = Signal(bool, str)

    def __init__(
        self,
        workspace_dir: Path,
        mods_dir: Path,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._workspace_dir = workspace_dir
        self._mods_dir = mods_dir

    def run(self) -> None:
        """Execute clean and emit results.  Runs on the worker thread."""
        from modsmith.cleaner import clean, CleanError  # lazy import

        self.log_line.emit("[INFO]  Cleaning generated output repository…")
        try:
            result = clean(
                workspace_dir=self._workspace_dir,
                mods_dir=self._mods_dir,
                force=True,  # GUI confirms before starting the worker
            )
        except CleanError as exc:
            self.log_line.emit(f"[ERROR] {exc}")
            self.finished.emit(False, f"Clean failed: {exc}")
            return
        except Exception as exc:
            self.log_line.emit(f"[ERROR] Unexpected error during clean: {exc}")
            self.finished.emit(False, f"Clean failed unexpectedly: {exc}")
            return

        self.log_line.emit(f"[INFO]  {result.message}")
        self.finished.emit(True, result.message)
