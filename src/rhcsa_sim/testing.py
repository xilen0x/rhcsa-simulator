from __future__ import annotations

from collections.abc import Mapping, Sequence

from rhcsa_sim.runner import CommandResult


def make_result(
    args: Sequence[str],
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> CommandResult:
    return CommandResult(tuple(args), returncode, stdout, stderr)


class FakeCommandRunner:
    """Responde con salidas predefinidas. Un comando no esperado falla el test."""

    def __init__(self, responses: Mapping[tuple[str, ...], CommandResult]) -> None:
        self._responses = dict(responses)
        self.calls: list[tuple[str, ...]] = []

    def run(
        self, args: Sequence[str], *, timeout: float | None = None
    ) -> CommandResult:
        key = tuple(args)
        self.calls.append(key)
        if key not in self._responses:
            raise AssertionError(f"unexpected command: {key}")
        return self._responses[key]
