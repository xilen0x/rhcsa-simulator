from __future__ import annotations

from rhcsa_sim.checks.files import PathHasMode, PathHasOwner
from rhcsa_sim.checks.users import (
    GroupExists,
    UserExists,
    UserHasShell,
    UserHasUid,
    UserInGroup,
)
from rhcsa_sim.models import ObjectiveBlock, Task
from rhcsa_sim.registry import TaskRegistry
from rhcsa_sim.runner import CommandRunner


def build_catalog(runner: CommandRunner) -> TaskRegistry:
    return TaskRegistry(
        [
            Task(
                id="users-01",
                block=ObjectiveBlock.USERS_GROUPS,
                description="Crea el grupo 'devs' con GID 5000.",
                points=10,
                checks=(GroupExists(runner, "devs", 5000),),
            ),
            Task(
                id="users-02",
                block=ObjectiveBlock.USERS_GROUPS,
                description=(
                    "Crea el usuario 'alice' con UID 1234, shell /bin/bash "
                    "y miembro del grupo 'devs'."
                ),
                points=10,
                checks=(
                    UserExists(runner, "alice"),
                    UserHasUid(runner, "alice", 1234),
                    UserHasShell(runner, "alice", "/bin/bash"),
                    UserInGroup(runner, "alice", "devs"),
                ),
            ),
            Task(
                id="files-01",
                block=ObjectiveBlock.FILE_SYSTEMS,
                description=(
                    "Crea el directorio /srv/shared con propietario root, "
                    "grupo devs y modo 2770 (setgid)."
                ),
                points=10,
                checks=(
                    PathHasOwner(runner, "/srv/shared", "root", "devs"),
                    PathHasMode(runner, "/srv/shared", "2770"),
                ),
            ),
        ]
    )
