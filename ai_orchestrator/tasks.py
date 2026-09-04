from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


ACTIONABLE_STATUSES = {
    "NOT IMPLEMENTED",
    "INVESTIGATING",
    "CONFIRMED BROKEN",
    "PARTIALLY IMPLEMENTED",
    "IMPLEMENTED BUT UNTESTED",
    "TEST FAILED",
    "CHANGES REQUESTED",
    "BLOCKED",
}

TERMINAL_STATUSES = {
    "VERIFIED",
}

BLOCKED_STATUSES = {
    "BLOCKED",
}


PRIORITY_ORDER = {
    "P0": 0,
    "P1": 1,
    "P2": 2,
    "P3": 3,
    "P4": 4,
}


@dataclass
class Task:
    row_number: int
    data: dict[str, str]

    @property
    def task_id(self) -> str:
        return self.data.get("Task ID", "").strip()

    @property
    def domain(self) -> str:
        return self.data.get("Domain", "").strip()

    @property
    def component(self) -> str:
        return self.data.get("Component", "").strip()

    @property
    def requirement(self) -> str:
        return self.data.get("Requirement", "").strip()

    @property
    def expected_behavior(self) -> str:
        return self.data.get("Expected Behavior", "").strip()

    @property
    def status(self) -> str:
        return self.data.get("Status", "").strip().upper()

    @property
    def priority(self) -> str:
        return self.data.get("Priority", "").strip().upper()

    @property
    def priority_rank(self) -> int:
        return PRIORITY_ORDER.get(self.priority, 99)

    @property
    def dependencies(self) -> list[str]:
        raw = self.data.get("Dependencies", "").strip()

        if not raw or raw.lower() in {"none", "n/a", "-"}:
            return []

        return [
            item.strip()
            for item in raw.replace(",", ";").split(";")
            if item.strip()
        ]

    @property
    def backend_module(self) -> str:
        return self.data.get("Backend Module", "").strip()

    @property
    def ui_module(self) -> str:
        return self.data.get("UI Module", "").strip()

    @property
    def api_endpoint(self) -> str:
        return self.data.get("API Endpoint", "").strip()

    @property
    def implementation_plan(self) -> str:
        return self.data.get("Implementation Plan", "").strip()

    @property
    def test_plan(self) -> str:
        return self.data.get("Test Plan", "").strip()

    @property
    def test_command(self) -> str:
        return self.data.get("Test Command", "").strip()

    @property
    def acceptance_criteria(self) -> str:
        return self.data.get("Acceptance Criteria", "").strip()

    @property
    def next_action(self) -> str:
        return self.data.get("Next Action", "").strip()


class TaskManager:

    def __init__(self, csv_path: str):
        self.csv_path = Path(csv_path)

        if not self.csv_path.exists():
            raise FileNotFoundError(
                f"Task CSV not found: {self.csv_path}"
            )

        with self.csv_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as fh:
            reader = csv.DictReader(fh)

            if not reader.fieldnames:
                raise ValueError(
                    "Task CSV has no header"
                )

            self.fieldnames = list(reader.fieldnames)
            self.rows = list(reader)

    def tasks(self) -> list[Task]:
        return [
            Task(
                row_number=index + 2,
                data=row,
            )
            for index, row in enumerate(self.rows)
        ]

    def task_map(self) -> dict[str, Task]:
        return {
            task.task_id: task
            for task in self.tasks()
            if task.task_id
        }

    def dependencies_verified(
        self,
        task: Task,
    ) -> bool:
        task_map = self.task_map()

        for dependency_id in task.dependencies:
            dependency = task_map.get(dependency_id)

            if dependency is None:
                return False

            if dependency.status != "VERIFIED":
                return False

        return True

    def actionable_tasks(self) -> list[Task]:
        candidates = []

        for task in self.tasks():

            if task.status not in ACTIONABLE_STATUSES:
                continue

            if not self.dependencies_verified(task):
                continue

            candidates.append(task)

        return candidates

    def next_task(self) -> Task | None:
        candidates = self.actionable_tasks()

        if not candidates:
            return None

        candidates.sort(
            key=lambda task: (
                task.priority_rank,
                task.row_number,
            )
        )

        return candidates[0]

    def update_status(
        self,
        task_id: str,
        status: str,
        blocker: str | None = None,
    ) -> None:

        status = status.strip().upper()

        valid_statuses = (
            ACTIONABLE_STATUSES
            | TERMINAL_STATUSES
            | BLOCKED_STATUSES
        )

        if status not in valid_statuses:
            raise ValueError(
                f"Invalid task status: {status}"
            )

        found = False

        for row in self.rows:
            if row.get("Task ID", "").strip() == task_id:
                row["Status"] = status
                if blocker is not None:
                    row["Blocker"] = blocker
                found = True
                break

        if not found:
            raise KeyError(
                f"Task not found: {task_id}"
            )

        self._write()

    def update_fields(
        self,
        task_id: str,
        **fields: str,
    ) -> None:

        allowed = set(self.fieldnames)

        unknown = set(fields) - allowed

        if unknown:
            raise ValueError(
                f"Unknown CSV columns: {sorted(unknown)}"
            )

        found = False

        for row in self.rows:
            if row.get("Task ID", "").strip() == task_id:

                for key, value in fields.items():
                    row[key] = value

                found = True
                break

        if not found:
            raise KeyError(
                f"Task not found: {task_id}"
            )

        self._write()

    def _write(self) -> None:

        temp_path = self.csv_path.with_suffix(
            ".csv.tmp"
        )

        with temp_path.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as fh:

            writer = csv.DictWriter(
                fh,
                fieldnames=self.fieldnames,
                extrasaction="ignore",
            )

            writer.writeheader()
            writer.writerows(self.rows)

        temp_path.replace(self.csv_path)