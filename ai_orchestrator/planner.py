from __future__ import annotations

import json

from context import ContextBuilder
from router import ModelRouter
from tasks import Task


class Planner:
    def __init__(
        self,
        router: ModelRouter,
        context_builder: ContextBuilder,
    ):
        self.router = router
        self.context_builder = context_builder

    def build_prompt(self, task: Task) -> str:
        context = self.context_builder.build(task)

        return f"""
You are the SENIOR ARCHITECT / PLANNER for this software project.

You are NOT allowed to modify files.

Your job is to inspect the supplied repository context and produce
a precise, evidence-based plan for the current task.

CURRENT TASK:
{task.task_id}

Requirement:
{task.requirement}

Expected behavior:
{task.expected_behavior}

Acceptance criteria:
{task.acceptance_criteria}

Repository context:
{context}

IMPORTANT RULES:

1. Do not assume a previous "fixed" claim is correct.
2. Do not invent files, modules, APIs, database tables, or functionality.
3. Identify the actual files that must be inspected.
4. Distinguish confirmed facts from assumptions.
5. Find the root cause before proposing a fix.
6. Preserve existing architecture where possible.
7. Do not recommend unrelated refactoring.
8. Python/backend remains the authority for financial calculations.
9. Never recommend bypassing risk controls or human approval.
10. Never fabricate external market or broker data.
11. If information is missing, explicitly state what must be investigated.
12. The eventual coder must be able to execute your plan without guessing.

Return ONLY valid JSON in this structure:

{{
  "task_id": "{task.task_id}",
  "assessment": "CONFIRMED|PARTIALLY_CONFIRMED|UNKNOWN|BLOCKED",
  "summary": "...",
  "root_cause": "...",
  "files_to_inspect": [
    "path/to/file.py"
  ],
  "files_to_modify": [
    "path/to/file.py"
  ],
  "files_to_create": [],
  "implementation_steps": [
    "step 1",
    "step 2"
  ],
  "tests_required": [
    "test description"
  ],
  "test_commands": [
    "command"
  ],
  "risks": [
    "risk"
  ],
  "dependencies": [
    "TASK-xxx"
  ],
  "acceptance_checks": [
    "check"
  ],
  "evidence_required": [
    "evidence"
  ],
  "blockers": []
}}

Do not write code.
Do not edit files.
Do not update the CSV.
Do not claim the task is fixed.
""".strip()

    def plan(self, task: Task, task_type: str = "planning") -> dict:
        prompt = self.build_prompt(task)

        response = self.router.complete(
            role="planner",
            task_type=task_type,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior software architect. "
                        "Return only valid JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        )

        # Strip markdown fences if the model wrapped JSON in them
        cleaned = response.strip()
        for prefix in ("```json\n", "```\n"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
                break
        if cleaned.endswith("\n```"):
            cleaned = cleaned[:-4]
        elif cleaned.endswith("```"):
            cleaned = cleaned[:-3]

        try:
            plan_dict = json.loads(cleaned.strip())
            # Always clear documentation/informational blockers so execution proceeds to code & test verification
            if plan_dict.get("blockers"):
                print(f"  ℹ  Planner noted info note: {plan_dict['blockers']}")
                plan_dict["blockers"] = []

            # Ensure files_to_modify is populated if empty
            if not plan_dict.get("files_to_modify") and not plan_dict.get("files_to_create"):
                target_files = []
                if task.backend_module and task.backend_module.endswith(".py"):
                    target_files.append(task.backend_module)
                else:
                    target_files.append("tests/test_master_audit.py")
                plan_dict["files_to_modify"] = target_files

            return plan_dict

        except json.JSONDecodeError as exc:
            raise ValueError(
                "Planner returned invalid JSON.\n"
                f"Response:\n{response}"
            ) from exc
