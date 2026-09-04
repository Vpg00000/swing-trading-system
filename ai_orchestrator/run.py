"""
Multi-AI Code Fixer — Main Runner
===================================
Orchestrates the full Pick → Plan → Code → Verify → Review → Done loop
using Gemini (planner) + Ollama qwen2.5-coder (coder) + Python (verifier).

Usage:
    python ai_orchestrator/run.py               # fix next 1 actionable task
    python ai_orchestrator/run.py --loop        # fix all actionable tasks
    python ai_orchestrator/run.py --task P0-003 # fix a specific task by ID
    python ai_orchestrator/run.py --dry-run     # plan only, no file edits
    python ai_orchestrator/run.py --status      # show model health + task queue
    python ai_orchestrator/run.py --audit       # scan repo for placeholders only

Must be run from the project root:
    cd /path/to/swing-trading-system
    python ai_orchestrator/run.py
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

# ── Path setup — must happen before any local imports ────────────────────────
_HERE = Path(__file__).resolve().parent          # .../ai_orchestrator/
_ROOT = _HERE.parent                              # .../swing-trading-system/
sys.path.insert(0, str(_HERE))                   # allow `from router import ...`
sys.path.insert(0, str(_ROOT))                   # allow project imports if needed


from auditor import RepositoryAuditor
from coder import Coder
from context import ContextBuilder
from planner import Planner
from providers.ollama import OllamaProvider
from reviewer import Reviewer
from router import ModelRouter
from tasks import Task, TaskManager
from verifier import Verifier


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

TASK_CSV = str(_ROOT / "AI_Investment_Command_Center_Task_Tracker.csv")
MASTER_PROMPT = "AI_Investment_Command_Center_Master_Repair_Prompt.txt"
MODELS_YAML = str(_ROOT / "ai_orchestrator" / "models.yaml")
MAX_RETRIES_PER_TASK = 2   # how many full code→verify cycles before giving up


# ─────────────────────────────────────────────────────────────────────────────
# Terminal colors (no extra deps)
# ─────────────────────────────────────────────────────────────────────────────

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    BLUE   = "\033[94m"
    DIM    = "\033[2m"

def _c(color: str, text: str) -> str:
    return f"{color}{text}{C.RESET}"

def _banner(text: str) -> None:
    width = 64
    print()
    print(_c(C.CYAN, "═" * width))
    print(_c(C.BOLD + C.CYAN, f"  {text}"))
    print(_c(C.CYAN, "═" * width))

def _section(title: str) -> None:
    print()
    print(_c(C.BLUE + C.BOLD, f"[{title}]"))

def _ok(msg: str) -> None:
    print(_c(C.GREEN, f"  ✓  {msg}"))

def _warn(msg: str) -> None:
    print(_c(C.YELLOW, f"  ⚠  {msg}"))

def _fail(msg: str) -> None:
    print(_c(C.RED, f"  ✗  {msg}"))

def _info(msg: str) -> None:
    print(_c(C.DIM, f"     {msg}"))


# ─────────────────────────────────────────────────────────────────────────────
# Git helpers
# ─────────────────────────────────────────────────────────────────────────────

def _git(*args: str, cwd: Path = _ROOT) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0, result.stdout.strip()
    except Exception as exc:
        return False, str(exc)


def git_commit(task: Task, changed_files: list[str]) -> bool:
    """Stage changed files and commit with task ID in message."""
    for f in changed_files:
        _git("add", f)

    msg = f"fix: {task.task_id} — {task.component or task.requirement[:60]}"
    ok, out = _git("commit", "-m", msg)
    if ok:
        _ok(f"Git commit: {msg}")
    else:
        _warn(f"Git commit failed: {out}")
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# Startup checks
# ─────────────────────────────────────────────────────────────────────────────

def check_ollama() -> bool:
    provider = OllamaProvider()
    healthy, msg = provider.health_check()
    if healthy:
        models = provider.list_models()
        model_names = [m.name for m in models]
        _ok(f"Ollama: {msg}")
        _info(f"Installed models: {', '.join(model_names) or '(none)'}")
        if not any("qwen2.5-coder" in n for n in model_names):
            _warn("qwen2.5-coder:7b not found — run: ollama pull qwen2.5-coder:7b")
            return False
    else:
        _fail(f"Ollama: {msg}")
        _fail("Start Ollama first: open Ollama app or run 'ollama serve'")
        return False
    return True


def check_task_csv() -> bool:
    if Path(TASK_CSV).exists():
        _ok(f"Task CSV: {Path(TASK_CSV).name}")
        return True
    _fail(f"Task CSV not found: {TASK_CSV}")
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_status(router: ModelRouter, manager: TaskManager) -> None:
    """Show model health and pending task queue."""
    _banner("SYSTEM STATUS")

    _section("AI Models")
    for m in router.status():
        health_str = _c(C.GREEN, "HEALTHY") if m["healthy"] else _c(C.RED, f"COOLDOWN {m['cooldown_seconds']}s")
        local = " [local]" if m["local"] else ""
        free = " [free]" if m["free"] else ""
        private = " [🔒private]" if m["private"] else ""
        quota_str = f"quota={m['quota_score']:.0%}" if m["daily_limit"] != "unlimited" else "quota=∞"
        used = f" used={m['requests_today']}/{m['daily_limit']}" if m["daily_limit"] != "unlimited" else ""
        print(f"  {m['id']:<28} {health_str}  {quota_str}{used}  roles={','.join(m['roles'])}{local}{free}{private}")

    _section("Task Queue")
    actionable = manager.actionable_tasks()
    total = len(manager.tasks())
    verified = sum(1 for t in manager.tasks() if t.status == "VERIFIED")
    print(f"  Total tasks: {total}")
    print(f"  Verified:    {_c(C.GREEN, str(verified))}")
    print(f"  Actionable:  {_c(C.YELLOW, str(len(actionable)))}")
    print(f"  Remaining:   {total - verified}")

    if actionable:
        print()
        print("  Next tasks (by priority):")
        for t in actionable[:10]:
            print(f"    {t.task_id:<12} [{t.priority}] [{t.status:<25}] {t.component[:40]}")


def cmd_audit(repo_root: Path) -> None:
    """Scan repository for placeholder/mock/TODO patterns."""
    _banner("REPOSITORY AUDIT")
    auditor = RepositoryAuditor(repository_root=str(repo_root))
    report = auditor.generate_structured_audit_report()
    summary = report["summary"]

    _section("Architecture")
    arch = report["architecture_verification"]
    missing = [(p, s) for p, s in arch.items() if s == "MISSING"]
    empty = [(p, s) for p, s in arch.items() if s == "EMPTY"]
    exists = [(p, s) for p, s in arch.items() if s == "EXISTS"]
    _ok(f"Exists: {len(exists)} files")
    if empty:
        _warn(f"Empty:  {len(empty)} files")
        for p, _ in empty[:5]:
            _info(p)
    if missing:
        _fail(f"Missing: {len(missing)} files")
        for p, _ in missing[:10]:
            _info(p)

    _section("Placeholder Findings")
    findings = report["placeholder_findings"]
    high = [f for f in findings if f["severity"] == "HIGH"]
    medium = [f for f in findings if f["severity"] == "MEDIUM"]
    _info(f"Total findings: {len(findings)}")
    _ok(f"HIGH severity:   {len(high)}")
    _warn(f"MEDIUM severity: {len(medium)}")
    if high:
        print()
        print("  HIGH severity findings (production files with fake/mock data):")
        for f in high[:20]:
            print(f"    {f['file']}:{f['line_number']} [{f['category']}]")
            print(f"      {f['matched_text'][:90]}")

    _section("Import Check")
    imports = report["import_verification"]
    failed_imports = [(m, info) for m, info in imports.items() if info["status"] != "IMPORT_OK"]
    _ok(f"Checked: {len(imports)} modules")
    if failed_imports:
        _fail(f"Failed imports: {len(failed_imports)}")
        for mod, info in failed_imports[:10]:
            _info(f"{mod}: {info['error'][:100]}")


# ─────────────────────────────────────────────────────────────────────────────
# Single task fixer
# ─────────────────────────────────────────────────────────────────────────────

def fix_task(
    task: Task,
    router: ModelRouter,
    context_builder: ContextBuilder,
    planner: Planner,
    coder: Coder,
    verifier: Verifier,
    reviewer: Reviewer,
    manager: TaskManager,
    dry_run: bool = False,
    auto_commit: bool = True,
) -> str:
    """
    Run the full Plan → Code → Verify → Review → Done loop for one task.

    Returns the final status: "VERIFIED" | "CHANGES REQUESTED" | "BLOCKED" | "SKIPPED"
    """
    t_start = time.time()
    original_status = task.status  # saved so transient errors can restore it

    print()
    print(_c(C.BOLD, f"  Task:      {task.task_id}"))
    print(_c(C.DIM,  f"  Component: {task.component or '—'}"))
    print(_c(C.DIM,  f"  Priority:  {task.priority}  Status: {task.status}"))
    print(_c(C.DIM,  f"  Requirement: {task.requirement[:80]}"))

    # ── Step 1: Plan ─────────────────────────────────────────────────────────
    _section("PLAN  (Gemini)")
    manager.update_status(task.task_id, "INVESTIGATING")

    try:
        plan = planner.plan(task, task_type="planning")
    except Exception as exc:
        err_str = str(exc)
        # Detect transient / recoverable errors — do NOT mark BLOCKED
        transient_keywords = (
            "503", "502", "unavailable", "high demand",
            "429", "rate limit", "quota", "timeout",
        )
        is_transient = any(kw in err_str.lower() for kw in transient_keywords)
        if is_transient:
            _warn(f"Planner hit a transient error (will auto-retry next run):")
            _warn(f"  {err_str[:200]}")
            _warn("Restoring task to original status — run again in ~30 seconds.")
            manager.update_status(task.task_id, original_status)
            return "SKIPPED"
        _fail(f"Planner failed (non-transient): {err_str[:200]}")
        manager.update_status(task.task_id, "BLOCKED")
        return "BLOCKED"

    files_to_modify = plan.get("files_to_modify", [])
    files_to_create = plan.get("files_to_create", [])
    steps = plan.get("implementation_steps", [])
    blockers = plan.get("blockers", [])

    if blockers:
        _warn("Planner identified blockers:")
        for b in blockers:
            _warn(f"  - {b}")
        manager.update_status(task.task_id, "BLOCKED")
        manager.update_fields(task.task_id, **{"Next Action": "; ".join(blockers)[:500]})
        return "BLOCKED"

    _ok(f"Assessment: {plan.get('assessment', '?')}")
    _info(f"Root cause: {plan.get('root_cause', '?')[:100]}")
    _info(f"Files to modify: {', '.join(files_to_modify) or '(none)'}")
    _info(f"Files to create: {', '.join(files_to_create) or '(none)'}")
    _info(f"Steps: {len(steps)}")
    for s in steps[:5]:
        _info(f"  • {s[:90]}")

    if not files_to_modify and not files_to_create:
        _warn("Planner did not identify any files to change — skipping")
        manager.update_status(task.task_id, "BLOCKED")
        return "BLOCKED"

    if dry_run:
        print()
        print(_c(C.YELLOW, "  DRY RUN — plan shown, no files written."))
        manager.update_status(task.task_id, task.status)  # restore original status
        return "SKIPPED"

    # ── Step 2: Code (with retry) ─────────────────────────────────────────
    changed_files: list[str] = []
    verify_passed = False

    for attempt in range(1, MAX_RETRIES_PER_TASK + 1):
        attempt_label = f"attempt {attempt}/{MAX_RETRIES_PER_TASK}"
        _section(f"CODE  (Ollama → Gemini fallback) — {attempt_label}")
        manager.update_status(task.task_id, "PARTIALLY IMPLEMENTED")

        coder_result = coder.code(
            plan=plan,
            task_id=task.task_id,
            requirement=task.requirement,
            task_type="coding",
        )

        if coder_result.escalated:
            _warn("Some files used Gemini fallback (Ollama failed)")

        if not coder_result.success:
            _fail(f"Coder failed on: {', '.join(coder_result.error_files)}")
            if attempt == MAX_RETRIES_PER_TASK:
                manager.update_status(task.task_id, "BLOCKED")
                return "BLOCKED"
            _warn(f"Retrying task ({attempt_label} failed) ...")
            continue

        changed_files = coder_result.changed_files
        _ok(f"Code applied: {', '.join(changed_files)}")

        # ── Step 3: Verify ────────────────────────────────────────────────
        _section("VERIFY  (Python)")
        verify_result = verifier.verify(
            task=task,
            changed_files=changed_files,
        )

        if verify_result.passed:
            verify_passed = True
            _ok(f"Verification PASSED ({verify_result.total_duration_sec}s)")
            break
        else:
            _fail(f"Verification FAILED: {verify_result.fail_reason[:150]}")
            manager.update_status(task.task_id, "TEST FAILED")
            if attempt < MAX_RETRIES_PER_TASK:
                _warn(f"Will retry code generation (attempt {attempt + 1}) ...")

    if not verify_passed:
        _fail("All verification attempts exhausted — marking BLOCKED")
        manager.update_status(task.task_id, "BLOCKED")
        return "BLOCKED"

    # ── Step 4: Review ────────────────────────────────────────────────────
    _section("REVIEW  (Quality Gate)")
    review_result = reviewer.review(changed_files=changed_files)
    print(f"  {review_result.summary()}")

    if not review_result.approved:
        _fail("Review FAILED — HIGH severity placeholder/mock patterns found")
        _fail("Task NOT marked VERIFIED — fix the flagged lines manually")
        manager.update_status(task.task_id, "CHANGES REQUESTED")
        return "CHANGES REQUESTED"

    if review_result.medium_severity:
        _warn(f"{len(review_result.medium_severity)} MEDIUM severity findings (not blocking)")

    # ── Step 5: Mark done ─────────────────────────────────────────────────
    manager.update_status(task.task_id, "VERIFIED")
    duration = round(time.time() - t_start, 1)
    _ok(f"Task {task.task_id} → VERIFIED  ({duration}s total)")

    if auto_commit and changed_files:
        git_commit(task, changed_files)

    return "VERIFIED"


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multi-AI Code Fixer — Gemini plans, Ollama codes, Python verifies.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--loop",       action="store_true", help="Fix all actionable tasks (not just one)")
    parser.add_argument("--task",       metavar="ID",        help="Fix a specific task by ID (e.g. P0-003)")
    parser.add_argument("--dry-run",    action="store_true", help="Plan only — no file edits")
    parser.add_argument("--status",     action="store_true", help="Show model health and task queue, then exit")
    parser.add_argument("--audit",      action="store_true", help="Scan repo for placeholders/TODOs, then exit")
    parser.add_argument("--no-commit",  action="store_true", help="Skip git commit after verified fix")
    args = parser.parse_args()

    _banner("MULTI-AI CODE FIXER — Swing Trading System")
    print(f"  Root:   {_ROOT}")
    print(f"  Models: {MODELS_YAML}")
    print(f"  Tasks:  {TASK_CSV}")

    # ── Startup checks ────────────────────────────────────────────────────
    _section("STARTUP CHECKS")
    ollama_ok = check_ollama()
    csv_ok = check_task_csv()

    if not csv_ok:
        sys.exit(1)

    if not ollama_ok:
        _warn("Ollama unavailable — coder will rely entirely on Gemini fallback")
        _warn("(All tasks will be handled by Gemini free tier)")

    # ── Init components ────────────────────────────────────────────────────
    router = ModelRouter(config_path=MODELS_YAML)
    manager = TaskManager(TASK_CSV)
    context_builder = ContextBuilder(
        master_prompt_path=MASTER_PROMPT,
        repository_root=str(_ROOT),
    )
    planner = Planner(router=router, context_builder=context_builder)
    coder = Coder(router=router, repo_root=_ROOT)
    verifier = Verifier(repo_root=_ROOT)
    reviewer = Reviewer(repo_root=_ROOT)

    # ── Sub-commands ───────────────────────────────────────────────────────
    if args.status:
        cmd_status(router, manager)
        return

    if args.audit:
        cmd_audit(_ROOT)
        return

    # ── Determine tasks to run ─────────────────────────────────────────────
    if args.task:
        task_map = manager.task_map()
        task = task_map.get(args.task)
        if task is None:
            _fail(f"Task '{args.task}' not found in CSV")
            sys.exit(1)
        tasks_to_run = [task]
    elif args.loop:
        tasks_to_run = manager.actionable_tasks()
        if not tasks_to_run:
            _ok("No actionable tasks — all done!")
            return
        _info(f"Loop mode: {len(tasks_to_run)} actionable task(s) queued")
    else:
        # Default: one task
        task = manager.next_task()
        if task is None:
            _ok("No actionable tasks — all done!")
            return
        tasks_to_run = [task]

    # ── Run ────────────────────────────────────────────────────────────────
    results: dict[str, str] = {}
    session_start = time.time()

    for task in tasks_to_run:
        _banner(f"TASK  {task.task_id}")
        status = fix_task(
            task=task,
            router=router,
            context_builder=context_builder,
            planner=planner,
            coder=coder,
            verifier=verifier,
            reviewer=reviewer,
            manager=manager,
            dry_run=args.dry_run,
            auto_commit=not args.no_commit,
        )
        results[task.task_id] = status

        if args.loop and status == "BLOCKED":
            _warn("Task BLOCKED — continuing to next task")

    # ── Session summary ────────────────────────────────────────────────────
    _banner("SESSION SUMMARY")
    total_sec = round(time.time() - session_start, 1)
    verified = sum(1 for s in results.values() if s == "VERIFIED")
    blocked = sum(1 for s in results.values() if s == "BLOCKED")
    changed = sum(1 for s in results.values() if s == "CHANGES REQUESTED")
    skipped = sum(1 for s in results.values() if s == "SKIPPED")

    print(f"  Tasks processed: {len(results)}")
    print(f"  {_c(C.GREEN, 'Verified')}:         {verified}")
    print(f"  {_c(C.YELLOW, 'Changes needed')}:  {changed}")
    print(f"  {_c(C.RED, 'Blocked')}:          {blocked}")
    print(f"  {_c(C.DIM, 'Skipped')}:          {skipped}")
    print(f"  Total time:      {total_sec}s")

    # Show remaining actionable count
    remaining = manager.actionable_tasks()
    if remaining:
        print()
        _info(f"{len(remaining)} task(s) still actionable. Run again to continue.")

    if results:
        print()
        for task_id, status in results.items():
            color = C.GREEN if status == "VERIFIED" else (C.RED if status == "BLOCKED" else C.YELLOW)
            print(f"  {task_id:<15} {_c(color, status)}")


if __name__ == "__main__":
    main()
