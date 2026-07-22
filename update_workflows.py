"""Update existing workflow instances to use OR logic for role-based assignments.

This script:
1. Finds all IN_PROGRESS workflow instances
2. For each step with multiple pending tasks (role assignment), applies OR logic
3. If at least one task is APPROVED, marks the rest as SUPERSEDED

Run this script once after deploying the OR logic changes to engine.py.
"""

import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.models import WorkflowInstance, WorkflowTask
from datetime import date


def update_existing_workflows():
    """Update existing workflow instances to use OR logic."""
    db = SessionLocal()
    try:
        # Find all IN_PROGRESS workflow instances
        instances = db.query(WorkflowInstance).filter(
            WorkflowInstance.status == "IN_PROGRESS"
        ).all()

        print(f"Found {len(instances)} IN_PROGRESS workflow instances")

        updated_count = 0
        for instance in instances:
            print(f"\nProcessing workflow instance {instance.id} for {instance.object_type} {instance.object_id}")

            # Group tasks by stage and step
            tasks_by_step = {}
            for task in instance.tasks:
                if task.status == "PENDING":
                    key = (task.stage_index, task.step_key)
                    if key not in tasks_by_step:
                        tasks_by_step[key] = []
                    tasks_by_step[key].append(task)

            # For each step with multiple pending tasks, apply OR logic
            for (stage_idx, step_key), tasks in tasks_by_step.items():
                if len(tasks) > 1:
                    print(f"  Step '{step_key}' at stage {stage_idx}: {len(tasks)} pending tasks")

                    # Check if any task is already approved
                    approved_tasks = [t for t in tasks if t.status == "APPROVED"]
                    pending_tasks = [t for t in tasks if t.status == "PENDING"]

                    if approved_tasks and pending_tasks:
                        # Mark pending tasks as SUPERSEDED
                        for task in pending_tasks:
                            task.status = "SUPERSEDED"
                            task.completed_at = date.today().isoformat()
                            task.comment = "Superseded: another user approved this step (migrated to OR logic)."
                            print(f"    Marked task {task.id} (user {task.assigned_to}) as SUPERSEDED")
                            updated_count += 1

        if updated_count > 0:
            db.commit()
            print(f"\n\nCommitted {updated_count} task updates")
        else:
            print("\n\nNo tasks needed updating")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Workflow Instance Update Script")
    print("=" * 60)
    print("\nThis script will update existing IN_PROGRESS workflow instances")
    print("to use OR logic for role-based assignments.")
    print("\nPress Enter to continue or Ctrl+C to cancel...")
    input()

    update_existing_workflows()
    print("\nDone!")
