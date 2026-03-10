#!/usr/bin/env python3
"""
Standalone CLI for TickTick task management.
Uses the same TickTickClient as the MCP server.

Usage:
    ticktick-cli projects
    ticktick-cli tasks [--project NAME_OR_ID] [--all]
    ticktick-cli create "Title" --project NAME_OR_ID [--due DATE] [--priority N] [--tags t1,t2]
    ticktick-cli update TASK_ID --project PID [--title T] [--due DATE] [--priority N] [--tags t1,t2]
    ticktick-cli complete TASK_ID --project PID
    ticktick-cli delete TASK_ID --project PID
    ticktick-cli search "query"

Environment:
    TICKTICK_ACCESS_TOKEN   Required. OAuth access token.
    TICKTICK_CLIENT_ID      Optional. For token refresh.
    TICKTICK_CLIENT_SECRET  Optional. For token refresh.
    TICKTICK_PROJECTS       Optional. JSON map of name->id overrides.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta

from .src.ticktick_client import TickTickClient

# Default project aliases (personal config — override via TICKTICK_PROJECTS env)
DEFAULT_PROJECTS = {
    "work": "693d58d98f08a47127417e87",
    "health": "693d58dc8f08a7f5090da2b1",
    "finance": "693d58de8f084de1795503cf",
    "family": "693d58e08f08a7f5090da302",
    "career": "693d58e28f08a47127417f3d",
    "home": "693d58e48f084de179550520",
    "craft": "6957aa3d8f087c3909232a4a",
    "general": "6957abeb8f0880378e3ec05b",
}


def get_project_map():
    """Load project name->id mapping from env or defaults."""
    env_map = os.getenv("TICKTICK_PROJECTS")
    if env_map:
        try:
            return {k.lower(): v for k, v in json.loads(env_map).items()}
        except json.JSONDecodeError:
            pass
    return DEFAULT_PROJECTS


def resolve_project(name_or_id):
    """Resolve a project name alias to ID, or pass through raw ID."""
    projects = get_project_map()
    resolved = projects.get(name_or_id.lower())
    if resolved:
        return resolved
    # Looks like a raw ID already (24-char hex)
    if len(name_or_id) >= 20:
        return name_or_id
    print(f"Unknown project: {name_or_id}", file=sys.stderr)
    print(f"Available: {', '.join(sorted(projects.keys()))}", file=sys.stderr)
    sys.exit(1)


def fmt_task(task, compact=False):
    """Format a single task for display."""
    prio_map = {0: "⚪", 1: "🟢", 3: "🟡", 5: "🔴"}
    prio = prio_map.get(task.get("priority", 0), "⚪")
    status = "✅" if task.get("status") == 2 else "⬜"
    due = ""
    if task.get("dueDate"):
        due = f" · {task['dueDate'][:10]}"
    tags = ""
    if task.get("tags"):
        tags = f" [{','.join(task['tags'])}]"
    tid = task.get("id", "?")

    if compact:
        return f"  {status} {prio} {task.get('title', '?')}{due}{tags}  ({tid[:8]})"

    lines = [f"{prio} {task.get('title', '?')}"]
    lines.append(f"  id: {tid}  project: {task.get('projectId', '?')}")
    if task.get("dueDate"):
        lines.append(f"  due: {task['dueDate'][:10]}")
    if task.get("startDate"):
        lines.append(f"  start: {task['startDate'][:10]}")
    if task.get("tags"):
        lines.append(f"  tags: {', '.join(task['tags'])}")
    if task.get("content"):
        lines.append(f"  content: {task['content'][:100]}")
    if task.get("items"):
        for item in task["items"]:
            s = "✓" if item.get("status") == 1 else "□"
            lines.append(f"    [{s}] {item.get('title', '?')}")
    return "\n".join(lines)


def cmd_projects(client, args):
    projects = client.get_projects()
    if isinstance(projects, dict) and "error" in projects:
        print(f"Error: {projects['error']}", file=sys.stderr)
        return 1
    aliases = get_project_map()
    alias_by_id = {v: k for k, v in aliases.items()}
    for p in projects:
        alias = alias_by_id.get(p["id"], "")
        suffix = f" ({alias})" if alias else ""
        print(f"  {p.get('name', '?')}: {p['id']}{suffix}")
    return 0


def cmd_tasks(client, args):
    projects = get_project_map()
    if args.project:
        project_ids = [(args.project, resolve_project(args.project))]
    elif args.all:
        project_ids = [(name, pid) for name, pid in sorted(projects.items())]
    else:
        # Default: show all projects
        project_ids = [(name, pid) for name, pid in sorted(projects.items())]

    for name, pid in project_ids:
        data = client.get_project_with_data(pid)
        if isinstance(data, dict) and "error" in data:
            print(f"  {name}: Error — {data['error']}", file=sys.stderr)
            continue
        tasks = [t for t in data.get("tasks", []) if t.get("status") != 2]
        if not tasks and not args.all:
            continue
        proj_name = data.get("project", {}).get("name", name)
        print(f"\n=== {proj_name} ({len(tasks)} active) ===")
        for task in tasks:
            print(fmt_task(task, compact=True))
    return 0


def cmd_create(client, args):
    pid = resolve_project(args.project)
    tags = args.tags.split(",") if args.tags else None
    result = client.create_task(
        title=args.title,
        project_id=pid,
        content=args.content,
        due_date=args.due,
        start_date=args.start,
        priority=args.priority,
        is_all_day=not args.timed,
        tags=tags,
    )
    if isinstance(result, dict) and "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        return 1
    print(f"Created: {result.get('id', '?')} — {result.get('title', '?')}")
    if args.json:
        print(json.dumps(result, indent=2))
    return 0


def cmd_update(client, args):
    pid = resolve_project(args.project)
    tags = args.tags.split(",") if args.tags else None
    result = client.update_task(
        task_id=args.task_id,
        project_id=pid,
        title=args.title,
        content=args.content,
        due_date=args.due,
        start_date=args.start,
        priority=args.priority,
        is_all_day=args.all_day,
        tags=tags,
    )
    if isinstance(result, dict) and "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        return 1
    print(f"Updated: {result.get('id', '?')} — {result.get('title', '?')}")
    return 0


def cmd_complete(client, args):
    pid = resolve_project(args.project)
    result = client.complete_task(pid, args.task_id)
    if isinstance(result, dict) and "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        return 1
    print(f"Completed: {args.task_id}")
    return 0


def cmd_delete(client, args):
    pid = resolve_project(args.project)
    result = client.delete_task(pid, args.task_id)
    if isinstance(result, dict) and "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        return 1
    print(f"Deleted: {args.task_id}")
    return 0


def cmd_search(client, args):
    projects_list = client.get_projects()
    if isinstance(projects_list, dict) and "error" in projects_list:
        print(f"Error: {projects_list['error']}", file=sys.stderr)
        return 1
    query = args.query.lower()
    found = 0
    for proj in projects_list:
        if proj.get("closed"):
            continue
        data = client.get_project_with_data(proj["id"])
        tasks = data.get("tasks", [])
        matches = [
            t for t in tasks
            if query in t.get("title", "").lower()
            or query in t.get("content", "").lower()
        ]
        if matches:
            print(f"\n=== {proj.get('name', '?')} ===")
            for task in matches:
                print(fmt_task(task, compact=True))
                found += 1
    if not found:
        print(f"No tasks matching '{args.query}'")
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="ticktick-cli",
        description="TickTick CLI — same client as MCP server, standalone interface",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # projects
    sub.add_parser("projects", help="List all projects")

    # tasks
    p_tasks = sub.add_parser("tasks", help="List tasks")
    p_tasks.add_argument("--project", "-p", help="Project name or ID")
    p_tasks.add_argument("--all", "-a", action="store_true", help="Include empty projects")

    # create
    p_create = sub.add_parser("create", help="Create a task")
    p_create.add_argument("title", help="Task title")
    p_create.add_argument("--project", "-p", required=True, help="Project name or ID")
    p_create.add_argument("--due", "-d", help="Due date (YYYY-MM-DD)")
    p_create.add_argument("--start", help="Start date (YYYY-MM-DD)")
    p_create.add_argument("--priority", type=int, default=0, choices=[0, 1, 3, 5],
                          help="Priority: 0=none, 1=low, 3=medium, 5=high")
    p_create.add_argument("--tags", "-t", help="Comma-separated tags")
    p_create.add_argument("--content", "-c", help="Task description")
    p_create.add_argument("--timed", action="store_true", help="Not all-day (has specific time)")
    p_create.add_argument("--json", action="store_true", help="Output full JSON response")

    # update
    p_update = sub.add_parser("update", help="Update a task")
    p_update.add_argument("task_id", help="Task ID")
    p_update.add_argument("--project", "-p", required=True, help="Project ID")
    p_update.add_argument("--title", help="New title")
    p_update.add_argument("--due", "-d", help="New due date (YYYY-MM-DD)")
    p_update.add_argument("--start", help="New start date")
    p_update.add_argument("--priority", type=int, choices=[0, 1, 3, 5], help="New priority")
    p_update.add_argument("--tags", "-t", help="Comma-separated tags (empty string to clear)")
    p_update.add_argument("--content", "-c", help="New description")
    p_update.add_argument("--all-day", type=bool, help="Set all-day flag")

    # complete
    p_complete = sub.add_parser("complete", help="Complete a task")
    p_complete.add_argument("task_id", help="Task ID")
    p_complete.add_argument("--project", "-p", required=True, help="Project name or ID")

    # delete
    p_delete = sub.add_parser("delete", help="Delete a task")
    p_delete.add_argument("task_id", help="Task ID")
    p_delete.add_argument("--project", "-p", required=True, help="Project name or ID")

    # search
    p_search = sub.add_parser("search", help="Search tasks by text")
    p_search.add_argument("query", help="Search query")

    args = parser.parse_args()

    # Initialize client
    try:
        client = TickTickClient()
    except ValueError as e:
        print(f"Auth error: {e}", file=sys.stderr)
        print("Run 'ticktick-auth' to set up credentials.", file=sys.stderr)
        sys.exit(1)

    handlers = {
        "projects": cmd_projects,
        "tasks": cmd_tasks,
        "create": cmd_create,
        "update": cmd_update,
        "complete": cmd_complete,
        "delete": cmd_delete,
        "search": cmd_search,
    }
    handler = handlers.get(args.command)
    sys.exit(handler(client, args))


if __name__ == "__main__":
    main()
