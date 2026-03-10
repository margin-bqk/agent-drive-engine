# Agent Drive Engine Skill

## Overview

This skill provides the Agent with an internal motivation system. It generates self-driven task proposals based on "Drives" (internal motivation dimensions).

## Triggers

- **Heartbeat**: Every 30 minutes (handled by heartbeat system)
- **Energy Reset**: Daily at 02:00 (handled by cronjob)

## Deployment Guide

### Initial Setup

1. **Ensure drive_engine skill directory structure**:
   ```
   drive_engine/
   ├── config.json      # Static configuration
   ├── state.json       # Dynamic state
   ├── drives.md        # Drive definitions
   └── skill.md        # This file
   ```

2. **Configure cronjob for energy reset (daily at 02:00)**:
   - Configure a cronjob to trigger the Agent daily at 02:00
   - The cronjob should trigger the Agent to execute: `python3 drive_calc.py --mode=reset-energy`
   - Example cron configuration: `0 2 * * * cd /path/to/agent && python3 drive_calc.py --mode=reset-energy`

3. **Configure heartbeat for deicated intervals**:
   - The heartbeat system triggers every given minutes set by agent config
   - Add a task to agent's HEARTBEAT.md. When triggered, agent should execute: `python3 drive_calc.py --mode=heartbeat`

## Execution Modes

### Mode 1: Heartbeat (triggered every 30 minutes)

**User Intervention:**
If `user_intervention.enabled` is set to `true` in state.json, the Agent must obtain user confirmation before generating tasks. The instructions will include a notice: `[USER INTERVENTION REQUIRED] Please confirm with user before adding tasks.`

**Step 1: Execute calculation script**
```bash
python3 drive_calc.py --mode=heartbeat
```

**Step 2: Parse output**
Read the script output and parse the following fields:
- `ACTION`: Action type
- `DRIVE`: Current active drive
- `ENERGY_REMAINING`: Remaining energy
- `TASK_COUNT`: Number of tasks that can be generated
- `ENERGY_PER_TASK`: Energy cost per task
- `MAX_ENERGY_CONSUMPTION`: Maximum energy consumption
- `EXECUTING_TASKS`: Current executing tasks count (e.g., "2/2")
- `TASK_DETAILS`: List of executing tasks with their elapsed/planned time
- `STALE_TASKS`: Tasks that exceeded planned duration
- `INSTRUCTIONS`: Specific execution instructions

**Step 3: Execute tasks**
Follow the instructions in the `INSTRUCTIONS` field:
1. Generate the specified number of small, executable tasks
2. Execute update-state mode after generating tasks

**Step 4: Update state**
```bash
python3 drive_calc.py --mode=update-state --tasks "task1|30|10,task2|60|20" --energy-spent 30
```

Format: `taskID|plannedMinutes|energyCost` (comma-separated for multiple tasks)
- Example: `task1|30|10` = task1, 30 minutes planned, 10 energy
- If plannedMinutes or energyCost not specified, defaults from config.json will be used

### Mode 2: Energy Reset (triggered at 02:00 daily by cronjob)

**Step 1: Execute reset script**
```bash
python3 drive_calc.py --mode=reset-energy
```

**Step 2: Parse output**
Confirm energy has been reset to 100

### Mode 3: Complete Task (triggered when task is finished)

**Step 1: Execute complete-task script**
```bash
python3 drive_calc.py --mode=complete-task --task-id=task_001
```

**Step 2: Parse output**
Confirm the drive score has been reset to 0

## File Operation Rules

- **Read only**: config.json, drives.md
- **Managed by Python**: state.json (do not modify directly)
- **After task completion**: Reset corresponding drive score to 0

## Prohibited Actions

- Do not modify state.json directly
- Do not manually calculate energy/drive scores
- Do not generate tasks exceeding energy limits
- All state operations must go through Python script

## Output Format Example

```
ACTION: heartbeat
DRIVE: completion
ENERGY_REMAINING: 70
TASK_COUNT: 2
ENERGY_PER_TASK: 10
MAX_ENERGY_CONSUMPTION: 20
EXECUTING_TASKS: 2/2
TASK_DETAILS:
  - task_001: 25min / 30min (OK)
  - task_002: 65min / 60min (WARNING: exceeded by 5min)
STALE_TASKS: [task_002]
INSTRUCTIONS: Based on completion drive, generate 2 small tasks. Format: --tasks "taskID|plannedMinutes|energyCost,..."
ACTION_REQUIRED: 1 task(s) exceeded planned duration. Please verify status and call: python3 drive_calc.py --mode=complete-task --task-id=TASK_ID
```

## Executing Tasks Limit and Timeout

The system limits the number of concurrent executing tasks (default: 2, configurable in config.json).
- When `EXECUTING_TASKS` reaches the limit (e.g., "2/2"), no new tasks will be generated
- Each task has a planned duration (planned_minutes) set when generating the task
- When a task exceeds its planned duration, it becomes a STALE_TASK
- The Agent must verify and complete stale tasks before generating new tasks

### Task Format
When generating tasks, specify planned duration and energy cost:
```bash
python3 drive_calc.py --mode=update-state --tasks "task1|30|10,task2|60|20" --energy-spent 30
```
Format: `taskID|plannedMinutes|energyCost`
- If not specified, defaults from config.json are used (default_duration_minutes: 60, default_energy_cost: 10)
