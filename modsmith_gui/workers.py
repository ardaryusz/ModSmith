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
