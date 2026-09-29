from __future__ import annotations

from collections.abc import Mapping, Sequence

from rhcsa_sim.models import TaskResult

# Ajustar si Red Hat cambia el umbral oficial (hoy: 210 de 300 puntos).
PASS_THRESHOLD_PERCENT = 70

_RESET = "\x1b[0m"
_GREEN = "\x1b[32m"
_RED = "\x1b[31m"


def sanitize_text(text: str) -> str:
    """Elimina caracteres de control para evitar inyeccion de secuencias de escape
    en la terminal (los detalles pueden incluir texto que viene del sistema)."""
    return "".join(ch if ch.isprintable() else "?" for ch in text)


def should_use_color(is_tty: bool, env: Mapping[str, str]) -> bool:
    if env.get("NO_COLOR", "") or env.get("TERM") == "dumb":
        return False
    return is_tty


def _paint(text: str, code: str, enabled: bool) -> str:
    return f"{code}{text}{_RESET}" if enabled else text


def format_status(passed: bool, *, color: bool) -> str:
    if passed:
        return _paint("OK", _GREEN, color)
    return _paint("KO", _RED, color)


def format_task_result(result: TaskResult, *, color: bool) -> str:
    task = result.task
    header = (
        f"[{format_status(result.passed, color=color)}] {task.id}  "
        f"{sanitize_text(task.description)}  ({result.earned_points}/{task.points})"
    )
    lines = [header]
    for check, check_result in zip(task.checks, result.check_results, strict=True):
        status = format_status(check_result.passed, color=color)
        lines.append(
            f"     [{status}] {sanitize_text(check.describe())}: "
            f"{sanitize_text(check_result.detail)}"
        )
    return "\n".join(lines)


def calculate_score(results: Sequence[TaskResult]) -> tuple[int, int]:
    earned = sum(r.earned_points for r in results)
    total = sum(r.task.points for r in results)
    return earned, total


def format_summary(results: Sequence[TaskResult], *, color: bool) -> str:
    earned, total = calculate_score(results)
    if total == 0:
        return "No tasks evaluated."
    percent = earned * 100 // total
    passed = percent >= PASS_THRESHOLD_PERCENT
    verdict = _paint("PASS", _GREEN, color) if passed else _paint("FAIL", _RED, color)
    return (
        f"Score: {earned}/{total} ({percent}%) [{verdict}] "
        f"pass threshold: {PASS_THRESHOLD_PERCENT}%"
    )
