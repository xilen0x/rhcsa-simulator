from __future__ import annotations

from rhcsa_sim.checks.files import PathHasMode, PathHasOwner
from rhcsa_sim.checks.storage import (
    MIB,
    LogicalVolumeExists,
    LogicalVolumeSizeInRange,
    PhysicalVolumeInGroup,
    VolumeGroupExists,
)
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
            Task(
                id="storage-01",
                block=ObjectiveBlock.LOCAL_STORAGE,
                description=(
                    "Crea el grupo de volumenes 'examvg' sobre /dev/sdb1 "
                    "con un tamano de extent de 16 MiB."
                ),
                points=10,
                checks=(
                    PhysicalVolumeInGroup(runner, "/dev/sdb1", "examvg"),
                    VolumeGroupExists(runner, "examvg", 16 * MIB),
                ),
            ),
            Task(
                id="storage-02",
                block=ObjectiveBlock.LOCAL_STORAGE,
                description=(
                    "Crea el volumen logico 'datalv' en 'examvg' "
                    "con un tamano entre 960 MiB y 1088 MiB."
                ),
                points=10,
                checks=(
                    LogicalVolumeExists(runner, "examvg", "datalv"),
                    LogicalVolumeSizeInRange(runner, "examvg", "datalv", 960 * MIB, 1088 * MIB),
                ),
            ),
        ]
    )
