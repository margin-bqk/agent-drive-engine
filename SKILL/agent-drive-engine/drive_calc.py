#!/usr/bin/env python3
"""
Drive Engine - State Management Script

This script manages the Agent's internal motivation system state.
It supports multiple modes for different operations.

Usage:
    python3 drive_calc.py --mode=heartbeat
    python3 drive_calc.py --mode=reset-energy
    python3 drive_calc.py --mode=update-state --tasks "task1|30|10,task2|60|20" --energy-spent 30
    python3 drive_calc.py --mode=complete-task --task-id task_001

Task format: taskID|plannedMinutes|energyCost
Example: "task1|30|10,task2|60|20"
- task1: task ID
- 30: planned duration in minutes
- 10: energy cost

If plannedMinutes or energyCost not specified, defaults from config.json will be used.
"""

import json
import sys
import os
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Configuration paths
CONFIG_PATH = "./SKILL/agent-drive-engine/config.json"
STATE_PATH = "./SKILL/agent-drive-engine/state.json"


def load_json(file_path):
    """Load JSON file. Exit on error."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"error:{str(e)}")
        sys.exit(1)


def save_json(file_path, data):
    """Save JSON file. Exit on error."""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"error:{str(e)}")
        sys.exit(1)


def calculate_active_drive(config, state):
    """Calculate the active drive (highest score + priority tiebreaker)."""
    drive_scores = state["drive_scores"]
    sorted_drives = sorted(drive_scores.items(), key=lambda x: x[1], reverse=True)
    
    top_drive = sorted_drives[0][0]
    if len(sorted_drives) > 1 and sorted_drives[0][1] == sorted_drives[1][1]:
        priority = config["drives"]["priority"]
        top_drive = priority[0] if priority[0] in [d[0] for d in sorted_drives[:2]] else top_drive
    
    return top_drive


def calculate_available_tasks(config, state):
    """Calculate the number of available tasks based on energy and executing tasks limit."""
    energy = state["energy"]["remaining"]
    cost_per_task = config["energy"]["cost_per_task"]
    max_tasks = config["task"]["max_count"]
    max_executing = config["task"]["max_executing"]
    
    # Calculate based on energy
    energy_based_tasks = int(energy / cost_per_task)
    
    # Calculate based on executing tasks limit
    executing_tasks = state.get("executing_tasks", {})
    current_executing = len(executing_tasks)
    executing_based_tasks = max(0, max_executing - current_executing)
    
    # Use the smaller value
    available_tasks = min(energy_based_tasks, max_tasks, executing_based_tasks)
    return max(available_tasks, 0)


def parse_tasks_input(tasks_str, config):
    """
    Parse tasks input string.
    Format: taskID|plannedMinutes|energyCost,taskID2|plannedMinutes2|energyCost2
    Example: "task1|30|10,task2|60|20"
    """
    default_duration = config["task"].get("default_duration_minutes", 60)
    default_energy = config["task"].get("default_energy_cost", 10)
    
    tasks = []
    for task_part in tasks_str.split(','):
        task_part = task_part.strip()
        if not task_part:
            continue
        
        parts = task_part.split('|')
        task_id = parts[0].strip()
        
        if len(parts) >= 2:
            try:
                planned_minutes = int(parts[1])
            except ValueError:
                planned_minutes = default_duration
        else:
            planned_minutes = default_duration
        
        if len(parts) >= 3:
            try:
                energy_cost = int(parts[2])
            except ValueError:
                energy_cost = default_energy
        else:
            energy_cost = default_energy
        
        tasks.append({
            "id": task_id,
            "planned_minutes": planned_minutes,
            "energy_cost": energy_cost
        })
    
    return tasks


def get_task_status(state, config):
    """Get status of all executing tasks with duration info."""
    executing_tasks = state.get("executing_tasks", {})
    if not executing_tasks:
        return [], []
    
    now = datetime.now()
    stale_tasks = []
    task_details = []
    
    for task_id, task_info in executing_tasks.items():
        started_at_str = task_info.get("started_at", "")
        planned_minutes = task_info.get("planned_minutes", 60)
        
        try:
            started_at = datetime.strptime(started_at_str, "%Y-%m-%d %H:%M:%S")
            elapsed_minutes = (now - started_at).total_seconds() / 60
            elapsed_minutes = int(elapsed_minutes)
        except (ValueError, TypeError):
            elapsed_minutes = 0
            planned_minutes = 0
        
        exceeded = elapsed_minutes - planned_minutes if planned_minutes > 0 else 0
        
        if exceeded > 0:
            stale_tasks.append(task_id)
            status = f"WARNING: exceeded by {exceeded}min"
        else:
            remaining = planned_minutes - elapsed_minutes
            status = f"OK ({remaining}min remaining)"
        
        task_details.append({
            "id": task_id,
            "elapsed": elapsed_minutes,
            "planned": planned_minutes,
            "status": status,
            "exceeded": exceeded
        })
    
    return task_details, stale_tasks


def grow_drives(config, state):
    """
    Grow drive scores over time based on growth_factor.
    Each drive increases by growth_factor per heartbeat, up to max of 1.0.
    """
    growth_factor = config["drives"].get("growth_factor", 0.1)
    drive_scores = state.get("drive_scores", {})
    
    grown_drives = []
    for drive, score in drive_scores.items():
        new_score = min(score + growth_factor, 1.0)
        if new_score != score:
            grown_drives.append(f"{drive}: {score:.2f} -> {new_score:.2f}")
        state["drive_scores"][drive] = new_score
    
    return grown_drives


def mode_heartbeat(config, state):
    """Heartbeat mode: Calculate active drive and available tasks."""
    # Grow drive scores based on growth_factor
    grown_drives = grow_drives(config, state)
    
    # Save state after growing drives
    save_json(STATE_PATH, state)
    
    # Calculate active drive after growth
    active_drive = calculate_active_drive(config, state)
    remaining_energy = state["energy"]["remaining"]
    available_tasks = calculate_available_tasks(config, state)
    cost_per_task = config["energy"]["cost_per_task"]
    max_consumption = available_tasks * cost_per_task
    max_executing = config["task"]["max_executing"]
    growth_factor = config["drives"].get("growth_factor", 0.1)
    
    executing_tasks = state.get("executing_tasks", {})
    current_executing = len(executing_tasks)
    
    # Get task status and stale tasks
    task_details, stale_tasks = get_task_status(state, config)
    
    print(f"ACTION: heartbeat")
    print(f"DRIVE: {active_drive}")
    print(f"ENERGY_REMAINING: {remaining_energy}")
    print(f"TASK_COUNT: {available_tasks}")
    print(f"ENERGY_PER_TASK: {cost_per_task}")
    print(f"MAX_ENERGY_CONSUMPTION: {max_consumption}")
    print(f"EXECUTING_TASKS: {current_executing}/{max_executing}")
    print(f"GROWTH_FACTOR: {growth_factor}")
    
    # Print drive growth info if any
    if grown_drives:
        print(f"DRIVE_GROWTH: {grown_drives}")
    
    # Print task details if any
    if task_details:
        print("TASK_DETAILS:")
        for task in task_details:
            print(f"  - {task['id']}: {task['elapsed']}min / {task['planned']}min ({task['status']})")
    
    # Print stale tasks warning
    if stale_tasks:
        print(f"STALE_TASKS: {stale_tasks}")
    
    # Generate instructions
    if available_tasks > 0:
        print(f"INSTRUCTIONS: Based on {active_drive} drive, generate {available_tasks} small tasks. Each task costs {cost_per_task} energy, total consumption not exceeding {max_consumption}. Current executing: {current_executing}, max: {max_executing}. Format: --tasks \"taskID|plannedMinutes|energyCost,...\" Example: --tasks \"task1|30|10,task2|60|20\"")
    else:
        if current_executing >= max_executing:
            print(f"INSTRUCTIONS: No tasks can be generated. Executing tasks limit reached ({current_executing}/{max_executing}). Wait for a task to complete.")
        else:
            print(f"INSTRUCTIONS: No tasks can be generated due to insufficient energy. Energy required per task: {cost_per_task}")
    
    # Add warning about stale tasks
    if stale_tasks:
        print(f"ACTION_REQUIRED: {len(stale_tasks)} task(s) exceeded planned duration. Please verify status and call: python3 drive_calc.py --mode=complete-task --task-id=TASK_ID")


def mode_reset_energy(config, state):
    """Reset energy mode: Reset energy to maximum."""
    max_energy = config["energy"]["max_energy"]
    state["energy"]["remaining"] = max_energy
    state["energy"]["last_reset"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    save_json(STATE_PATH, state)
    
    print(f"ACTION: reset-energy")
    print(f"ENERGY_RESET_TO: {max_energy}")
    print(f"LAST_RESET: {state['energy']['last_reset']}")
    print(f"INSTRUCTIONS: Energy has been reset to {max_energy}. The last_reset timestamp has been updated.")


def mode_update_state(config, state, tasks_str, total_energy_spent):
    """Update state mode: Add tasks and deduct energy."""
    # Parse tasks input
    tasks = parse_tasks_input(tasks_str, config)
    
    if not tasks:
        print(f"ACTION: update-state")
        print(f"STATUS: error")
        print(f"ERROR: No valid tasks provided")
        sys.exit(1)
    
    # Validate energy
    if total_energy_spent > state["energy"]["remaining"]:
        print(f"ACTION: update-state")
        print(f"STATUS: error")
        print(f"ERROR: Insufficient energy. Remaining: {state['energy']['remaining']}, Requested: {total_energy_spent}")
        sys.exit(1)
    
    # Ensure executing_tasks dict exists
    if "executing_tasks" not in state:
        state["executing_tasks"] = {}
    
    # Check executing tasks limit
    max_executing = config["task"]["max_executing"]
    current_executing = len(state["executing_tasks"])
    
    if current_executing + len(tasks) > max_executing:
        print(f"ACTION: update-state")
        print(f"STATUS: error")
        print(f"ERROR: Executing tasks limit exceeded. Current: {current_executing}, Max: {max_executing}, Requested: {len(tasks)}")
        sys.exit(1)
    
    # Update energy
    state["energy"]["remaining"] -= total_energy_spent
    
    # Get current timestamp
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Add tasks to unfinished_tasks and executing_tasks
    task_ids = []
    for task in tasks:
        task_id = task["id"]
        task_ids.append(task_id)
        
        # Add to unfinished_tasks if not already there
        if task_id not in state["unfinished_tasks"]:
            state["unfinished_tasks"].append(task_id)
        
        # Add to executing_tasks with metadata
        state["executing_tasks"][task_id] = {
            "started_at": now_str,
            "planned_minutes": task["planned_minutes"],
            "energy_cost": task["energy_cost"]
        }
    
    # Update last_heartbeat
    state["last_heartbeat"] = now_str
    
    save_json(STATE_PATH, state)
    
    print(f"ACTION: update-state")
    print(f"STATUS: success")
    print(f"ENERGY_REMAINING: {state['energy']['remaining']}")
    print(f"TASKS_ADDED: {task_ids}")
    print(f"UNFINISHED_TASKS: {state['unfinished_tasks']}")
    print(f"EXECUTING_TASKS: {list(state['executing_tasks'].keys())}")
    print(f"INSTRUCTIONS: state.json updated. {len(tasks)} task(s) added. Each task has planned duration and energy cost tracked.")


def mode_complete_task(config, state, task_id):
    """Complete task mode: Mark task as complete and reset drive score."""
    # Ensure executing_tasks dict exists
    if "executing_tasks" not in state:
        state["executing_tasks"] = {}
    
    # Remove task from unfinished_tasks
    if task_id not in state["unfinished_tasks"]:
        print(f"ACTION: complete-task")
        print(f"STATUS: error")
        print(f"ERROR: Task {task_id} not found in unfinished_tasks")
        sys.exit(1)
    
    state["unfinished_tasks"].remove(task_id)
    
    # Remove task from executing_tasks if present
    if task_id in state["executing_tasks"]:
        del state["executing_tasks"][task_id]
    
    # Find the active drive and reset its score to 0
    active_drive = calculate_active_drive(config, state)
    state["drive_scores"][active_drive] = 0.0
    
    save_json(STATE_PATH, state)
    
    print(f"ACTION: complete-task")
    print(f"STATUS: success")
    print(f"TASK_COMPLETED: {task_id}")
    print(f"DRIVE_RESET: {active_drive}")
    print(f"EXECUTING_TASKS: {list(state['executing_tasks'].keys())}")
    print(f"INSTRUCTIONS: Task {task_id} completed. The {active_drive} drive score reset to 0. Task removed from executing_tasks.")


def main():
    parser = argparse.ArgumentParser(description="Drive Engine State Management Script")
    parser.add_argument("--mode", required=True, choices=["heartbeat", "reset-energy", "update-state", "complete-task"],
                        help="Operation mode")
    parser.add_argument("--tasks", help="Task info string: taskID|plannedMinutes|energyCost (comma-separated)")
    parser.add_argument("--energy-spent", type=int, help="Total energy spent (for update-state mode)")
    parser.add_argument("--task-id", help="Task ID to complete (for complete-task mode)")
    
    args = parser.parse_args()
    
    # Load config and state
    config = load_json(CONFIG_PATH)
    state = load_json(STATE_PATH)
    
    # Execute based on mode
    if args.mode == "heartbeat":
        mode_heartbeat(config, state)
    elif args.mode == "reset-energy":
        mode_reset_energy(config, state)
    elif args.mode == "update-state":
        if not args.tasks or args.energy_spent is None:
            print("ERROR: --tasks and --energy-spent are required for update-state mode")
            print("Example: --tasks \"task1|30|10,task2|60|20\" --energy-spent 30")
            sys.exit(1)
        mode_update_state(config, state, args.tasks, args.energy_spent)
    elif args.mode == "complete-task":
        if not args.task_id:
            print("ERROR: --task-id is required for complete-task mode")
            sys.exit(1)
        mode_complete_task(config, state, args.task_id)


if __name__ == "__main__":
    main()
