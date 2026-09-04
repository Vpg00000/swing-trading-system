"""
Coder agent — takes a Planner JSON plan and applies file edits using
the local Ollama model (qwen2.5-coder:7b) as the primary engine, with
Gemini free as the escalation fallback.

Design principles:
  - One file at a time (fits in local model's context window)
  - Returns the COMPLETE corrected file (not a diff) — simpler to apply
  - Validates Python syntax with ast.parse() before writing
  - Strips markdown code fences if the model wraps output in them
  - Never modifies files outside files_to_modify / files_to_create
  - If syntax invalid after 1 retry → escalates to fallback model
  - Creates new files if files_to_create are listed in the plan
"""

from __future__ import annotations

import ast
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# Allow importing router from same package when running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from router import ModelRouter


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FileEdit:
    path: str           # relative path from repo root
    action: str         # "modified" | "created" | "skipped" | "error"
    model_used: str     # which model produced this edit
    attempts: int       # how many model calls were made
    error: str = ""     # non-empty if action == "error"


@dataclass
class CoderResult:
    success: bool
    edits: List[FileEdit] = field(default_factory=list)
    total_duration_sec: float = 0.0
    escalated: bool = False     # True if fallback model was used for any file

    @property
    def changed_files(self) -> List[str]:
        return [e.path for e in self.edits if e.action in ("modified", "created")]

    @property
    def error_files(self) -> List[str]:
        return [e.path for e in self.edits if e.action == "error"]


# ─────────────────────────────────────────────────────────────────────────────
# Prompt builders
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a senior Python developer making a precise, minimal fix to a file.
Output ONLY the complete corrected file content — no explanations, no markdown \
code fences, no commentary. The output must be valid, runnable Python.
Preserve all existing docstrings, comments, and formatting unless they are \
directly part of the fix. Do not add TODO, FIXME, mock, dummy, or placeholder \
values.\
"""

_NEW_FILE_SYSTEM_PROMPT = """\
You are a senior Python developer creating a new Python module.
Output ONLY the complete file content — no explanations, no markdown code \
fences, no commentary. The output must be valid, runnable Python.
Do not add TODO, FIXME, mock, dummy, or placeholder values.\
"""


def _build_modify_prompt(
    file_path: str,
    current_content: str,
    requirement: str,
    steps: List[str],
    task_id: str,
) -> str:
    steps_text = "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(steps))
    return (
        f"TASK: {task_id}\n\n"
        f"FILE TO MODIFY: {file_path}\n\n"
        f"REQUIREMENT:\n{requirement}\n\n"
        f"IMPLEMENTATION STEPS:\n{steps_text}\n\n"
        f"CURRENT FILE CONTENT:\n"
        f"{'─' * 60}\n"
        f"{current_content}\n"
        f"{'─' * 60}\n\n"
        f"Return the COMPLETE corrected file. Nothing else."
    )


def _build_create_prompt(
    file_path: str,
    requirement: str,
    steps: List[str],
    task_id: str,
    context_files: dict[str, str],
) -> str:
    steps_text = "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(steps))
    context_text = ""
    if context_files:
        context_text = "\n\nRELATED FILES FOR CONTEXT:\n"
        for path, content in context_files.items():
            context_text += f"\n--- {path} ---\n{content[:3000]}\n"
    return (
        f"TASK: {task_id}\n\n"
        f"NEW FILE TO CREATE: {file_path}\n\n"
        f"REQUIREMENT:\n{requirement}\n\n"
        f"IMPLEMENTATION STEPS:\n{steps_text}\n"
        f"{context_text}\n"
        f"Return the COMPLETE new file. Nothing else."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Output cleanup
# ─────────────────────────────────────────────────────────────────────────────

def _strip_code_fences(text: str) -> str:
    """
    Removes markdown code fences if the model wrapped its output.
    Handles: ```python ... ``` and ``` ... ```
    """
    text = text.strip()
    # Remove opening fence
    for prefix in ("```python\n", "```py\n", "```\n"):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    # Remove closing fence
    if text.endswith("\n```"):
        text = text[: -len("\n```")]
    elif text.endswith("```"):
        text = text[: -len("```")]
    return text.strip()


def _validate_python(content: str, file_path: str) -> Optional[str]:
    """
    Returns None if syntax is valid, or an error message string if not.
    Only validates .py files.
    """
    if not file_path.endswith(".py"):
        return None
    try:
        ast.parse(content)
        return None
    except SyntaxError as exc:
        return f"SyntaxError at line {exc.lineno}: {exc.msg}"


# ─────────────────────────────────────────────────────────────────────────────
# Coder
# ─────────────────────────────────────────────────────────────────────────────

class Coder:
    """
    Multi-model code writer.

    Primary model: 'coder' role → Ollama qwen2.5-coder:7b (local, free).
    Fallback:      'escalation' role → Gemini free (cloud, free).

    Usage:
        coder = Coder(router, repo_root=Path("."))
        result = coder.code(plan, task)
    """

    MAX_ATTEMPTS = 2  # per file: attempt 1 = primary, attempt 2 = fallback

    def __init__(self, router: ModelRouter, repo_root: Path):
        self.router = router
        self.root = repo_root.resolve()

    def _read_file(self, rel_path: str) -> str:
        target = self.root / rel_path
        if not target.exists():
            return ""
        return target.read_text(encoding="utf-8", errors="replace")

    def _write_file(self, rel_path: str, content: str) -> None:
        target = self.root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def _call_model(
        self,
        role: str,
        system_prompt: str,
        user_prompt: str,
        task_type: str = "coding",
    ) -> str:
        response = self.router.complete(
            role=role,
            task_type=task_type,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return _strip_code_fences(response)

    def _edit_one_file(
        self,
        rel_path: str,
        current_content: str,
        requirement: str,
        steps: List[str],
        task_id: str,
        action: str,  # "modify" or "create"
        context_files: dict[str, str] = {},
        task_type: str = "coding",
    ) -> FileEdit:
        attempts = 0
        escalated = False
        last_error = ""

        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            attempts = attempt
            # First attempt: primary 'coder' role (Ollama)
            # Second attempt: 'escalation' role (Gemini fallback)
            role = "coder" if attempt == 1 else "escalation"
            if attempt == 2:
                escalated = True

            try:
                if action == "create":
                    prompt = _build_create_prompt(
                        rel_path, requirement, steps, task_id, context_files
                    )
                    new_content = self._call_model(
                        role, _NEW_FILE_SYSTEM_PROMPT, prompt, task_type=task_type
                    )
                else:
                    prompt = _build_modify_prompt(
                        rel_path, current_content, requirement, steps, task_id
                    )
                    new_content = self._call_model(
                        role, _SYSTEM_PROMPT, prompt, task_type=task_type
                    )

                if not new_content.strip():
                    last_error = "Model returned empty response"
                    continue

                syntax_error = _validate_python(new_content, rel_path)
                if syntax_error:
                    last_error = syntax_error
                    print(
                        f"    ⚠  Syntax error on attempt {attempt}: {syntax_error}"
                    )
                    continue

                # Success — write the file
                self._write_file(rel_path, new_content)
                model_used = role  # approximate; router logs actual model name
                file_action = "created" if action == "create" else "modified"
                return FileEdit(
                    path=rel_path,
                    action=file_action,
                    model_used=model_used,
                    attempts=attempts,
                )

            except RuntimeError as exc:
                # Router couldn't find a healthy model for this role
                last_error = str(exc)
                print(f"    ✗  No model available for role={role}: {exc}")
                break
            except Exception as exc:
                last_error = str(exc)
                print(f"    ✗  Model call failed (attempt {attempt}): {exc}")

        return FileEdit(
            path=rel_path,
            action="error",
            model_used="none",
            attempts=attempts,
            error=last_error,
        )

    def code(
        self,
        plan: dict,
        task_id: str,
        requirement: str,
        task_type: str = "coding",
    ) -> CoderResult:
        """
        Apply all file edits specified in the plan.

        Args:
            plan: Structured JSON dict from Planner.plan()
            task_id: Human-readable task ID for prompt context
            requirement: The task requirement text for prompt context
            task_type: Task type hint for router (default: "coding")

        Returns:
            CoderResult with per-file edit results and success/failure
        """
        t_start = time.time()
        edits: List[FileEdit] = []
        escalated_any = False

        files_to_modify: List[str] = [
            f for f in plan.get("files_to_modify", [])
            if not f.endswith(".csv") and "Task_Tracker" not in f
        ]
        files_to_create: List[str] = [
            f for f in plan.get("files_to_create", [])
            if not f.endswith(".csv") and "Task_Tracker" not in f
        ]
        steps: List[str] = plan.get("implementation_steps", [])

        # Build context snippets for new file creation (files being modified)
        context_files: dict[str, str] = {}
        for rel_path in files_to_modify[:3]:  # limit to 3 to keep context small
            content = self._read_file(rel_path)
            if content:
                context_files[rel_path] = content

        # ── Modify existing files ──────────────────────────────────────────
        for rel_path in files_to_modify:
            target = self.root / rel_path
            if not target.exists():
                print(f"    ⚠  File not found (treating as create): {rel_path}")
                action = "create"
                current_content = ""
            else:
                action = "modify"
                current_content = self._read_file(rel_path)

            print(f"    → {'Editing' if action == 'modify' else 'Creating'} {rel_path} ...")
            edit = self._edit_one_file(
                rel_path=rel_path,
                current_content=current_content,
                requirement=requirement,
                steps=steps,
                task_id=task_id,
                action=action,
                context_files={},
                task_type=task_type,
            )
            edits.append(edit)
            if edit.action == "error":
                print(f"    ✗  {rel_path}: {edit.error}")
            else:
                print(f"    ✓  {rel_path} [{edit.action}] (attempts={edit.attempts})")

            if edit.attempts == self.MAX_ATTEMPTS and edit.action not in ("error",):
                escalated_any = True

        # ── Create new files ───────────────────────────────────────────────
        for rel_path in files_to_create:
            target = self.root / rel_path
            if target.exists():
                print(f"    ⚠  Skipping create (already exists): {rel_path}")
                edits.append(FileEdit(
                    path=rel_path,
                    action="skipped",
                    model_used="none",
                    attempts=0,
                    error="File already exists",
                ))
                continue

            print(f"    → Creating {rel_path} ...")
            edit = self._edit_one_file(
                rel_path=rel_path,
                current_content="",
                requirement=requirement,
                steps=steps,
                task_id=task_id,
                action="create",
                context_files=context_files,
                task_type=task_type,
            )
            edits.append(edit)
            if edit.action == "error":
                print(f"    ✗  {rel_path}: {edit.error}")
            else:
                print(f"    ✓  {rel_path} [{edit.action}] (attempts={edit.attempts})")

        duration = round(time.time() - t_start, 1)
        errors = [e for e in edits if e.action == "error"]
        success = len(errors) == 0 and len(edits) > 0

        return CoderResult(
            success=success,
            edits=edits,
            total_duration_sec=duration,
            escalated=escalated_any,
        )
