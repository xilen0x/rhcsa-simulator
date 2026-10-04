from __future__ import annotations

import textwrap
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TextIO

from rhcsa_sim.evaluator import evaluate_tasks
from rhcsa_sim.models import Task, TaskResult
from rhcsa_sim.registry import TaskRegistry
from rhcsa_sim.reporter import (
    PASS_THRESHOLD_PERCENT,
    calculate_score,
    sanitize_text,
)
from rhcsa_sim.ui import Ui

BOX_WIDTH = 76
EXAM_NAME = "RHCSA EX200 · RHEL 10"
PROMPT = "> "

_COMMAND_BAR = "[Enter] next [p] prev [N|id] jump [c] check [a] all [l] list [h] help [q] quit"

_HELP = (
    ("Enter / n", "next task"),
    ("p", "previous task"),
    ("<number> / <id>", "jump to a task (1-based number or exact id)"),
    ("c", "grade the current task"),
    ("a", "grade all tasks and show the score"),
    ("l", "list all tasks with status and progress"),
    ("s", "show the current task again"),
    ("h / ?", "this help"),
    ("q", "quit"),
)


@dataclass(slots=True)
class SessionState:
    """Estado puro de la sesion: posicion actual y resultados recordados."""

    tasks: tuple[Task, ...]
    index: int = 0
    results: dict[str, TaskResult] = field(default_factory=dict)

    @property
    def current(self) -> Task:
        return self.tasks[self.index]

    def move(self, delta: int) -> bool:
        """Mueve la posicion sin dar la vuelta; devuelve False si esta en un extremo."""
        target = self.index + delta
        if not 0 <= target < len(self.tasks):
            return False
        self.index = target
        return True

    def jump(self, token: str) -> bool:
        """Salta por numero (1-based) o por id exacto; False si no existe."""
        if token.isdecimal():
            number = int(token)
            if 1 <= number <= len(self.tasks):
                self.index = number - 1
                return True
            return False
        for position, task in enumerate(self.tasks):
            if task.id.lower() == token:
                self.index = position
                return True
        return False

    def status(self, task: Task) -> str:
        result = self.results.get(task.id)
        if result is None:
            return "pending"
        return "passed" if result.passed else "failed"

    def remember(self, results: Sequence[TaskResult]) -> None:
        for result in results:
            self.results[result.task.id] = result

    def graded_score(self) -> tuple[int, int]:
        """Puntos ganados sobre el total de las tareas ya calificadas."""
        return calculate_score(tuple(self.results.values()))


@dataclass(frozen=True, slots=True)
class Reply:
    text: str
    quit: bool = False


def _badge(ui: Ui, status: str) -> str:
    return f"{ui.painted_symbol(status)} {status}"


def _exam_name(ui: Ui) -> str:
    sep = "\u00b7" if ui.unicode else "-"
    return f"RHCSA EX200 {sep} RHEL 10"


def render_banner(state: SessionState, ui: Ui) -> str:
    total = sum(task.points for task in state.tasks)
    lines = [
        ui.bold(ui.cyan("rhcsa-sim")) + "  " + _exam_name(ui),
        f"{len(state.tasks)} tasks, {total} points. Type h for help.",
    ]
    return ui.box(lines, BOX_WIDTH)


def render_task(state: SessionState, ui: Ui) -> str:
    task = state.current
    title = f"Task {state.index + 1}/{len(state.tasks)}"
    header = (
        ui.bold(sanitize_text(task.id))
        + "  "
        + ui.cyan(task.block.value)
        + f"  {task.points} pts  "
        + _badge(ui, state.status(task))
    )
    body = textwrap.wrap(sanitize_text(task.description), BOX_WIDTH - 4) or [""]
    return ui.box([header, "", *body], BOX_WIDTH, title)


def render_command_bar(ui: Ui) -> str:
    return ui.dim(_COMMAND_BAR)


def render_screen(state: SessionState, ui: Ui) -> str:
    return render_task(state, ui) + "\n" + render_command_bar(ui)


def render_result(result: TaskResult, ui: Ui) -> str:
    task = result.task
    lines = [
        f"{ui.painted_symbol('passed' if result.passed else 'failed')} "
        f"{ui.bold(sanitize_text(task.id))}  "
        f"({result.earned_points}/{task.points} pts)"
    ]
    for check, check_result in zip(task.checks, result.check_results, strict=True):
        mark = ui.painted_symbol("passed" if check_result.passed else "failed")
        lines.append(
            f"   {mark} {sanitize_text(check.describe())}: "
            f"{sanitize_text(check_result.detail)}"
        )
    return "\n".join(lines)


def render_compact_result(result: TaskResult, ui: Ui) -> str:
    mark = ui.painted_symbol("passed" if result.passed else "failed")
    return (
        f"{mark} {sanitize_text(result.task.id):<12} "
        f"{result.earned_points:>3}/{result.task.points}"
    )


def render_score(results: Sequence[TaskResult], ui: Ui) -> str:
    earned, total = calculate_score(results)
    if total == 0:
        return "No tasks evaluated."
    percent = earned * 100 // total
    ok = percent >= PASS_THRESHOLD_PERCENT
    verdict = ui.green("PASS") if ok else ui.red("FAIL")
    return (
        f"Score: {earned}/{total} ({percent}%) [{verdict}] "
        f"pass threshold: {PASS_THRESHOLD_PERCENT}%"
    )


def render_list(state: SessionState, ui: Ui) -> str:
    rows = []
    for position, task in enumerate(state.tasks, start=1):
        marker = ">" if position - 1 == state.index else " "
        rows.append(
            f"{marker}{position:>3} {ui.painted_symbol(state.status(task)):<2} "
            f"{sanitize_text(task.id):<12} {task.block.value:<16} {task.points:>3} pts"
        )
    earned, _ = state.graded_score()
    total = sum(task.points for task in state.tasks)
    graded = len(state.results)
    bar = ui.progress_bar(graded, len(state.tasks))
    rows.append(
        f"{bar} graded {graded}/{len(state.tasks)}, score so far {earned}/{total}"
    )
    return "\n".join(rows)


def render_help(ui: Ui) -> str:
    return "\n".join(f"  {ui.bold(f'{key:<16}')}{text}" for key, text in _HELP)


def dispatch(state: SessionState, ui: Ui, line: str) -> Reply:
    """Interpreta una linea del usuario, actualiza el estado y devuelve el texto."""
    command = line.strip().lower()
    if command in ("", "n"):
        if state.move(1):
            return Reply(render_screen(state, ui))
        return Reply(ui.yellow("This is the last task."))
    if command == "p":
        if state.move(-1):
            return Reply(render_screen(state, ui))
        return Reply(ui.yellow("This is the first task."))
    if command == "s":
        return Reply(render_screen(state, ui))
    if command in ("h", "?"):
        return Reply(render_help(ui))
    if command == "l":
        return Reply(render_list(state, ui))
    if command == "c":
        results = evaluate_tasks((state.current,))
        state.remember(results)
        return Reply(render_result(results[0], ui))
    if command == "a":
        results = evaluate_tasks(state.tasks)
        state.remember(results)
        parts = [render_compact_result(r, ui) for r in results]
        parts.append(render_score(results, ui))
        return Reply("\n".join(parts))
    if command == "q":
        earned, total = state.graded_score()
        return Reply(
            f"Bye! Session score: {earned}/{total} "
            f"(graded {len(state.results)}/{len(state.tasks)}).",
            quit=True,
        )
    if state.jump(command):
        return Reply(render_screen(state, ui))
    if command.isdecimal():
        return Reply(ui.red(f"No such task. Use a number from 1-{len(state.tasks)}."))
    return Reply(
        ui.red(f"Unknown command '{sanitize_text(command)}'. Type h for help.")
    )


def run_session(
    registry: TaskRegistry,
    ui: Ui,
    read: Callable[[], str],
    out: TextIO,
) -> int:
    """Bucle de lectura: EOF y Ctrl+C terminan limpiamente con codigo 0."""
    state = SessionState(registry.all())
    if not state.tasks:
        out.write("No tasks available.\n")
        return 0
    out.write(render_banner(state, ui) + "\n")
    out.write(render_screen(state, ui) + "\n")
    try:
        while True:
            out.write(PROMPT)
            out.flush()
            reply = dispatch(state, ui, read())
            out.write(reply.text + "\n")
            if reply.quit:
                break
    except (EOFError, KeyboardInterrupt):
        out.write("\n")
    return 0
