from context import ContextBuilder
from planner import Planner
from router import ModelRouter
from tasks import TaskManager


CSV = "AI_Investment_Command_Center_Task_Tracker.csv"

manager = TaskManager(CSV)
task = manager.next_task()

if task is None:
    raise RuntimeError("No actionable task found")

router = ModelRouter()

builder = ContextBuilder(
    "AI_Investment_Command_Center_Master_Repair_Prompt.txt"
)

planner = Planner(
    router=router,
    context_builder=builder,
)

print(f"Planning {task.task_id}...")
print()

plan = planner.plan(task)

print("PLANNER WORKING")
print("=" * 70)

for key, value in plan.items():
    print(f"\n{key}:")
    print(value)
