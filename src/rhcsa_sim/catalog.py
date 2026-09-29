from __future__ import annotations

from rhcsa_sim.checks.acl import PathHasAclEntry
from rhcsa_sim.checks.files import PathHasMode, PathHasOwner
from rhcsa_sim.checks.firewall import FirewallPortAllowed, FirewallServiceAllowed
from rhcsa_sim.checks.filesystems import FstabMountByUuid, FstabUuidMatchesMount, MountedAt
from rhcsa_sim.checks.selinux import (
    PathHasSelinuxType,
    SelinuxBooleanIs,
    SelinuxMode,
    SelinuxPortType,
)
from rhcsa_sim.checks.services import DefaultTarget, UnitActiveStateIs, UnitFileStateIs
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
            Task(
                id="fs-01",
                block=ObjectiveBlock.FILE_SYSTEMS,
                description=(
                    "Monta de forma persistente el volumen logico examvg/datalv en /data "
                    "con sistema de archivos xfs, usando su UUID en /etc/fstab."
                ),
                points=10,
                checks=(
                    MountedAt(runner, "/data", "xfs", "/dev/mapper/examvg-datalv"),
                    FstabMountByUuid(runner, "/data", "xfs"),
                    FstabUuidMatchesMount(runner, "/data"),
                ),
            ),
            Task(
                id="fs-02",
                block=ObjectiveBlock.FILE_SYSTEMS,
                description=(
                    "Configura una ACL en /data que conceda al usuario 'alice' permisos rwx."
                ),
                points=10,
                checks=(PathHasAclEntry(runner, "/data", "user:alice:rwx"),),
            ),
            Task(
                id="svc-01",
                block=ObjectiveBlock.DEPLOY_MAINTAIN,
                description=(
                    "Asegura que el servicio httpd este habilitado al arranque y en ejecucion."
                ),
                points=10,
                checks=(
                    UnitFileStateIs(runner, "httpd.service", "enabled"),
                    UnitActiveStateIs(runner, "httpd.service", "active"),
                ),
            ),
            Task(
                id="svc-02",
                block=ObjectiveBlock.DEPLOY_MAINTAIN,
                description="Configura multi-user.target como target por defecto del sistema.",
                points=10,
                checks=(DefaultTarget(runner, "multi-user.target"),),
            ),
            Task(
                id="fw-01",
                block=ObjectiveBlock.NETWORKING,
                description=(
                    "Permite el servicio http en la zona public del firewall "
                    "de forma persistente y en ejecucion."
                ),
                points=10,
                checks=(FirewallServiceAllowed(runner, "public", "http"),),
            ),
            Task(
                id="fw-02",
                block=ObjectiveBlock.NETWORKING,
                description=(
                    "Abre el puerto 8080/tcp en la zona public del firewall "
                    "de forma persistente y en ejecucion."
                ),
                points=10,
                checks=(FirewallPortAllowed(runner, "public", 8080, "tcp"),),
            ),
            Task(
                id="se-01",
                block=ObjectiveBlock.SECURITY,
                description=(
                    "Configura SELinux en modo enforcing, en ejecucion y de forma persistente."
                ),
                points=10,
                checks=(SelinuxMode(runner, "enforcing"),),
            ),
            Task(
                id="se-02",
                block=ObjectiveBlock.SECURITY,
                description=(
                    "Crea el directorio /srv/web y asigna de forma persistente "
                    "el tipo SELinux httpd_sys_content_t a su contenido."
                ),
                points=10,
                checks=(PathHasSelinuxType(runner, "/srv/web", "httpd_sys_content_t"),),
            ),
            Task(
                id="se-03",
                block=ObjectiveBlock.SECURITY,
                description=(
                    "Activa de forma persistente el boolean SELinux httpd_can_network_connect."
                ),
                points=10,
                checks=(SelinuxBooleanIs(runner, "httpd_can_network_connect", True),),
            ),
            Task(
                id="se-04",
                block=ObjectiveBlock.SECURITY,
                description=(
                    "Permite que httpd escuche en el puerto 82/tcp etiquetandolo como http_port_t."
                ),
                points=10,
                checks=(SelinuxPortType(runner, 82, "tcp", "http_port_t"),),
            ),
        ]
    )
