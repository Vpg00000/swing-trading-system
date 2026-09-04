from tasks import TaskManager


CSV = "AI_Investment_Command_Center_Task_Tracker.csv"

manager = TaskManager(CSV)

print(f"Total tasks: {len(manager.tasks())}")

task = manager.next_task()

if task is None:
    print("No actionable tasks found.")
else:
    print("Next task:")
    print(f"  ID: {task.task_id}")
    print(f"  Priority: {task.priority}")
    print(f"  Status: {task.status}")
    print(f"  Requirement: {task.requirement}")
