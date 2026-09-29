from __future__ import annotations

from rhcsa_sim.checks._units import MIB
from rhcsa_sim.checks.acl import PathHasAclEntry
from rhcsa_sim.checks.blockdev import PartitionExists, SwapActive, SwapInFstabByUuid
from rhcsa_sim.checks.files import PathHasMode, PathHasOwner
from rhcsa_sim.checks.firewall import FirewallPortAllowed, FirewallServiceAllowed
from rhcsa_sim.checks.filesystems import FstabMountByUuid, FstabUuidMatchesMount, MountedAt
from rhcsa_sim.checks.maintenance import (
    CronEntryExists,
    PackageInstalled,
    RepoNotEnabled,
    TunedProfileIs,
)
from rhcsa_sim.checks.network import (
    ConnectionAutoconnect,
    ConnectionHasDns,
    ConnectionStaticIpv4,
    HostnameIs,
)
from rhcsa_sim.checks.security import SshdOptionIs, SudoersValid, UserHasSudoRule
from rhcsa_sim.checks.selinux import (
    PathHasSelinuxType,
    SelinuxBooleanIs,
    SelinuxMode,
    SelinuxPortType,
)
from rhcsa_sim.checks.services import DefaultTarget, UnitActiveStateIs, UnitFileStateIs
from rhcsa_sim.checks.storage import (
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
                id="part-01",
                block=ObjectiveBlock.LOCAL_STORAGE,
                description="Crea en el disco /dev/sdb una particion /dev/sdb2 de 512 MiB.",
                points=10,
                checks=(PartitionExists(runner, "/dev/sdb2", 480 * MIB, 560 * MIB),),
            ),
            Task(
                id="swap-01",
                block=ObjectiveBlock.LOCAL_STORAGE,
                description=(
                    "Formatea /dev/sdb2 como swap, activala y hazla persistente "
                    "en /etc/fstab usando su UUID."
                ),
                points=10,
                checks=(
                    SwapActive(runner, "/dev/sdb2"),
                    SwapInFstabByUuid(runner, "/dev/sdb2"),
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
                id="net-01",
                block=ObjectiveBlock.NETWORKING,
                description=(
                    "Configura el perfil de conexion 'exam-static' con IPv4 estatica "
                    "192.168.122.50/24, gateway 192.168.122.1, DNS 192.168.122.1 "
                    "y activacion automatica al arranque."
                ),
                points=10,
                checks=(
                    ConnectionStaticIpv4(
                        runner, "exam-static", "192.168.122.50/24", "192.168.122.1"
                    ),
                    ConnectionHasDns(runner, "exam-static", ("192.168.122.1",)),
                    ConnectionAutoconnect(runner, "exam-static"),
                ),
            ),
            Task(
                id="net-02",
                block=ObjectiveBlock.NETWORKING,
                description="Configura de forma persistente el hostname servera.lab.example.com.",
                points=10,
                checks=(HostnameIs(runner, "servera.lab.example.com"),),
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
            Task(
                id="sec-01",
                block=ObjectiveBlock.SECURITY,
                description="Deshabilita el acceso SSH directo del usuario root (PermitRootLogin no).",
                points=10,
                checks=(SshdOptionIs(runner, "permitrootlogin", "no"),),
            ),
            Task(
                id="sec-02",
                block=ObjectiveBlock.SECURITY,
                description=(
                    "Permite al usuario alice ejecutar cualquier comando con sudo "
                    "sin contrasena mediante un archivo en /etc/sudoers.d."
                ),
                points=10,
                checks=(
                    SudoersValid(runner),
                    UserHasSudoRule(runner, "alice", "ALL", nopasswd=True),
                ),
            ),
            Task(
                id="dnf-01",
                block=ObjectiveBlock.DEPLOY_MAINTAIN,
                description=(
                    "Asegura que el repositorio defectuoso exam-internal no este habilitado "
                    "(deshabilitalo o eliminalo)."
                ),
                points=10,
                checks=(RepoNotEnabled(runner, "exam-internal"),),
            ),
            Task(
                id="pkg-01",
                block=ObjectiveBlock.DEPLOY_MAINTAIN,
                description=(
                    "Instala el paquete at y deja el servicio atd habilitado y en ejecucion."
                ),
                points=10,
                checks=(
                    PackageInstalled(runner, "at"),
                    UnitFileStateIs(runner, "atd.service", "enabled"),
                    UnitActiveStateIs(runner, "atd.service", "active"),
                ),
            ),
            Task(
                id="cron-01",
                block=ObjectiveBlock.DEPLOY_MAINTAIN,
                description=(
                    "Programa para el usuario alice la ejecucion diaria de /usr/bin/date "
                    "a las 14:30 con cron."
                ),
                points=10,
                checks=(CronEntryExists(runner, "alice", "30 14 * * *", "/usr/bin/date"),),
            ),
            Task(
                id="tuned-01",
                block=ObjectiveBlock.DEPLOY_MAINTAIN,
                description=(
                    "Aplica el perfil de tuned recomendado para esta VM (virtual-guest)."
                ),
                points=10,
                checks=(TunedProfileIs(runner, "virtual-guest"),),
            ),
        ]
    )
