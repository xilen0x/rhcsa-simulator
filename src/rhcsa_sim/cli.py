from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from typing import TextIO

from rhcsa_sim.catalog import build_catalog
from rhcsa_sim.evaluator import evaluate_tasks
from rhcsa_sim.interactive import run_session
from rhcsa_sim.models import Task
from rhcsa_sim.registry import TaskRegistry
from rhcsa_sim.reporter import (
    format_summary,
    format_task_result,
    sanitize_text,
    should_use_color,
)
from rhcsa_sim.runner import CommandRunner, SubprocessRunner
from rhcsa_sim.ui import Ui, supports_unicode

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rhcsa-sim", description="RHCSA exam simulator: task checker."
    )
    sub = parser.add_subparsers(dest="command", required=False)
    sub.add_parser("list", help="list all tasks")
    show = sub.add_parser("show", help="show a task and its checks")
    show.add_argument("task_id")
    check = sub.add_parser("check", help="evaluate one task or all tasks")
    check.add_argument("task_id", nargs="?")
    check.add_argument("--all", action="store_true", dest="all_tasks")
    return parser


def _unknown_task(task_id: str, err: TextIO) -> int:
    err.write(f"error: unknown task '{sanitize_text(task_id)}'\n")
    return EXIT_USAGE


def _cmd_list(registry: TaskRegistry, out: TextIO) -> int:
    for task in registry.all():
        out.write(
            f"{task.id:<10} {task.block.value:<16} {task.points:>3} pts  "
            f"{task.description}\n"
        )
    return EXIT_OK


def _cmd_show(registry: TaskRegistry, task_id: str, out: TextIO, err: TextIO) -> int:
    task = registry.get(task_id)
    if task is None:
        return _unknown_task(task_id, err)
    out.write(f"{task.id} ({task.block.value}, {task.points} pts)\n")
    out.write(f"{task.description}\n")
    return EXIT_OK


def _cmd_check(
    registry: TaskRegistry,
    task_id: str | None,
    all_tasks: bool,
    out: TextIO,
    err: TextIO,
    color: bool,
) -> int:
    tasks: tuple[Task, ...]
    if all_tasks and task_id is None:
        tasks = registry.all()
    elif not all_tasks and task_id is not None:
        task = registry.get(task_id)
        if task is None:
            return _unknown_task(task_id, err)
        tasks = (task,)
    else:
        err.write("error: specify exactly one of <task_id> or --all\n")
        return EXIT_USAGE

    results = evaluate_tasks(tasks)
    for result in results:
        out.write(format_task_result(result, color=color) + "\n")
    if all_tasks:
        out.write(format_summary(results, color=color) + "\n")
    return EXIT_OK if all(r.passed for r in results) else EXIT_FAILED


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: CommandRunner | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    env: Mapping[str, str] | None = None,
    stdin: TextIO | None = None,
) -> int:
    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    environ: Mapping[str, str] = os.environ if env is None else env

    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else EXIT_USAGE

    registry = build_catalog(runner if runner is not None else SubprocessRunner())
    command: str | None = args.command
    if command is None:
        source = sys.stdin if stdin is None else stdin
        ui = Ui(
            unicode=supports_unicode(getattr(out, "encoding", None)),
            color=should_use_color(out.isatty(), environ),
        )

        def read() -> str:
            line = source.readline()
            if line == "":
                raise EOFError
            return line

        return run_session(registry, ui, read, out)
    if command == "list":
        return _cmd_list(registry, out)
    if command == "show":
        return _cmd_show(registry, args.task_id, out, err)
    return _cmd_check(
        registry,
        args.task_id,
        args.all_tasks,
        out,
        err,
        should_use_color(out.isatty(), environ),
    )
