from tasks import TaskManager
from context import ContextBuilder


CSV = "AI_Investment_Command_Center_Task_Tracker.csv"

manager = TaskManager(CSV)
task = manager.next_task()

if task is None:
    raise RuntimeError("No actionable task found")

builder = ContextBuilder(
    "AI_Investment_Command_Center_Master_Repair_Prompt.txt"
)

context = builder.build(task)

print("CONTEXT BUILDER WORKING")
print("=" * 70)
print(f"Task: {task.task_id}")
print(f"Context characters: {len(context)}")
print("=" * 70)
print(context[:3000])
