from __future__ import annotations

import subprocess
from pathlib import Path

from tasks import Task


class ContextBuilder:
    def __init__(
        self,
        master_prompt_path: str,
        repository_root: str = ".",
    ):
        self.root = Path(repository_root)
        self.master_prompt_path = self.root / master_prompt_path

    def _read(self, path: Path) -> str:
        if not path.exists():
            return f"[FILE NOT FOUND: {path}]"

        return path.read_text(
            encoding="utf-8",
            errors="replace",
        )

    def _git(self, *args: str) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            return result.stdout.strip()

        except Exception as exc:
            return f"[GIT ERROR: {exc}]"

    def build(self, task: Task) -> str:
        master_prompt = self._read(
            self.master_prompt_path
        )

        sections = []

        sections.append(
            "# MASTER OPERATING INSTRUCTIONS\n\n"
            + master_prompt
        )

        sections.append(
            "# CURRENT TASK\n\n"
            f"Task ID: {task.task_id}\n"
            f"Domain: {task.domain}\n"
            f"Component: {task.component}\n"
            f"Priority: {task.priority}\n"
            f"Status: {task.status}\n"
            f"Dependencies: "
            f"{', '.join(task.dependencies) or 'None'}\n\n"
            f"Requirement:\n{task.requirement}\n\n"
            f"Expected Behavior:\n"
            f"{task.expected_behavior}\n\n"
            f"Implementation Plan:\n"
            f"{task.implementation_plan}\n\n"
            f"Test Plan:\n{task.test_plan}\n\n"
            f"Test Command:\n{task.test_command}\n\n"
            f"Acceptance Criteria:\n"
            f"{task.acceptance_criteria}\n\n"
            f"Next Action:\n{task.next_action}"
        )

        sections.append(
            "# REPOSITORY TARGETS\n\n"
            f"Backend Module: {task.backend_module}\n"
            f"UI Module: {task.ui_module}\n"
            f"API Endpoint: {task.api_endpoint}"
        )

        # Include Task Tracker overview so planner can see all 40 tasks & claims
        tracker_path = self.root / "AI_Investment_Command_Center_Task_Tracker.csv"
        if tracker_path.exists():
            tracker_content = tracker_path.read_text(encoding="utf-8", errors="replace")
            sections.append(
                "# TASK TRACKER CSV CONTENT\n\n"
                + tracker_content
            )

        # Include key python repository structure
        py_files = [
            str(p.relative_to(self.root))
            for p in self.root.rglob("*.py")
            if not any(part.startswith((".", "venv", "__pycache__")) for part in p.parts)
        ]
        sections.append(
            "# EXISTING REPOSITORY PYTHON FILES (" + str(len(py_files)) + " files)\n\n"
            + "\n".join(sorted(py_files))
        )

        sections.append(
            "# GIT STATUS\n\n"
            + self._git("status", "--short")
        )

        sections.append(
            "# RECENT COMMITS\n\n"
            + self._git(
                "log",
                "--oneline",
                "-10",
            )
        )

        return "\n\n---\n\n".join(sections)
