from __future__ import annotations

from rhcsa_sim.checks._units import MIB
from rhcsa_sim.checks.acl import PathHasAclEntry
from rhcsa_sim.checks.autofs import AutofsMapEntry, AutofsMasterEntry
from rhcsa_sim.checks.blockdev import PartitionExists, SwapActive, SwapInFstabByUuid
from rhcsa_sim.checks.boot import KernelArgPresent
from rhcsa_sim.checks.essentials import (
    ArchiveContains,
    GrepOutputSaved,
    HardLinkTo,
    SymlinkTo,
)
from rhcsa_sim.checks.files import FilesIdentical, PathHasMode, PathHasOwner, UmaskConfigured
from rhcsa_sim.checks.firewall import FirewallPortAllowed, FirewallServiceAllowed
from rhcsa_sim.checks.filesystems import (
    FstabMountByUuid,
    FstabNfsEntry,
    FstabUuidMatchesMount,
    MountedAt,
    NfsMountedAt,
)
from rhcsa_sim.checks.logs import JournalPersistent
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
    ConnectionStaticIpv6,
    HostnameIs,
)
from rhcsa_sim.checks.processes import ProcessRunning
from rhcsa_sim.checks.scripts import (
    FileContainsLine,
    FileIsExecutable,
    ScriptHasShebang,
    ScriptSyntaxValid,
)
from rhcsa_sim.checks.security import (
    AuthorizedKeyPresent,
    SshdOptionIs,
    SudoersValid,
    UserHasSudoRule,
)
from rhcsa_sim.checks.selinux import (
    PathHasSelinuxType,
    SelinuxBooleanIs,
    SelinuxMode,
    SelinuxPortType,
)
from rhcsa_sim.checks.services import (
    DefaultTarget,
    TimerOnCalendar,
    UnitActiveStateIs,
    UnitFileStateIs,
)
from rhcsa_sim.checks.timesync import ChronySource
from rhcsa_sim.checks.storage import (
    LogicalVolumeExists,
    LogicalVolumeSizeInRange,
    PhysicalVolumeInGroup,
    VolumeGroupExists,
)
from rhcsa_sim.checks.users import (
    GroupExists,
    LoginDefsValue,
    PasswordAging,
    UserExists,
    UserHasShell,
    UserHasUid,
    UserInGroup,
)
from rhcsa_sim.models import ObjectiveBlock, Task
from rhcsa_sim.registry import TaskRegistry
from rhcsa_sim.runner import CommandRunner


# Hostname compartido por net-02 y scr-01.
LAB_HOSTNAME = "servera.lab.example.com"


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
                id="users-03",
                block=ObjectiveBlock.USERS_GROUPS,
                description=(
                    "Crea el usuario 'bob' con shell /usr/sbin/nologin "
                    "(sin acceso interactivo)."
                ),
                points=10,
                checks=(
                    UserExists(runner, "bob"),
                    UserHasShell(runner, "bob", "/usr/sbin/nologin"),
                ),
            ),
            Task(
                id="users-04",
                block=ObjectiveBlock.USERS_GROUPS,
                description=(
                    "Configura la contrasena de 'alice' para que caduque cada 90 dias "
                    "como maximo, con aviso 7 dias antes."
                ),
                points=10,
                checks=(PasswordAging(runner, "alice", max_days=90, warn_days=7),),
            ),
            Task(
                id="users-05",
                block=ObjectiveBlock.USERS_GROUPS,
                description=(
                    "Configura que los usuarios nuevos tengan por defecto una caducidad "
                    "maxima de contrasena de 60 dias (PASS_MAX_DAYS en /etc/login.defs)."
                ),
                points=10,
                checks=(LoginDefsValue(runner, "PASS_MAX_DAYS", "60"),),
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
                id="fs-03",
                block=ObjectiveBlock.FILE_SYSTEMS,
                description=(
                    "Crea la particion /dev/sdb3 de 256 MiB, formateala como VFAT y "
                    "montala de forma persistente en /mnt/vfat usando su UUID en /etc/fstab."
                ),
                points=10,
                checks=(
                    PartitionExists(runner, "/dev/sdb3", 240 * MIB, 300 * MIB),
                    MountedAt(runner, "/mnt/vfat", "vfat", "/dev/sdb3"),
                    FstabMountByUuid(runner, "/mnt/vfat", "vfat"),
                    FstabUuidMatchesMount(runner, "/mnt/vfat"),
                ),
            ),
            Task(
                id="fs-04",
                block=ObjectiveBlock.FILE_SYSTEMS,
                description=(
                    "Monta de forma persistente el recurso NFS localhost:/srv/nfsexport "
                    "en /mnt/nfs (nfs4) mediante /etc/fstab. Si practicas solo, puedes "
                    "exportar /srv/nfsexport desde tu propia maquina."
                ),
                points=10,
                checks=(
                    NfsMountedAt(runner, "/mnt/nfs", "localhost:/srv/nfsexport"),
                    FstabNfsEntry(runner, "/mnt/nfs", "localhost:/srv/nfsexport"),
                ),
            ),
            Task(
                id="fs-05",
                block=ObjectiveBlock.FILE_SYSTEMS,
                description=(
                    "Configura autofs con un montaje indirecto en /remote y el mapa "
                    "/etc/auto.remote, donde la clave 'data' monte localhost:/srv/nfsexport "
                    "con -fstype=nfs4,rw. Deja autofs habilitado y en ejecucion."
                ),
                points=10,
                checks=(
                    AutofsMasterEntry(runner, "/remote", "/etc/auto.remote"),
                    AutofsMapEntry(
                        runner, "/etc/auto.remote", "data", "localhost:/srv/nfsexport", "nfs4"
                    ),
                    UnitFileStateIs(runner, "autofs.service", "enabled"),
                    UnitActiveStateIs(runner, "autofs.service", "active"),
                ),
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
                description=f"Configura de forma persistente el hostname {LAB_HOSTNAME}.",
                points=10,
                checks=(HostnameIs(runner, LAB_HOSTNAME),),
            ),
            Task(
                id="net-03",
                block=ObjectiveBlock.NETWORKING,
                description=(
                    "Anade al perfil de conexion 'exam-static' una direccion IPv6 estatica "
                    "2001:db8:10::50/64 con gateway 2001:db8:10::1."
                ),
                points=10,
                checks=(
                    ConnectionStaticIpv6(
                        runner, "exam-static", "2001:db8:10::50/64", "2001:db8:10::1"
                    ),
                ),
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
                id="sec-03",
                block=ObjectiveBlock.SECURITY,
                description=(
                    "Configura que el usuario alice tenga por defecto umask 0027 "
                    "en sus sesiones de shell (/home/alice/.bashrc)."
                ),
                points=10,
                checks=(UmaskConfigured(runner, "/home/alice/.bashrc", "0027"),),
            ),
            Task(
                id="sec-04",
                block=ObjectiveBlock.SECURITY,
                description=(
                    "Como root, genera un par de claves ed25519 sin contrasena en "
                    "/root/.ssh/id_ed25519 y autorizalo para entrar como alice por SSH "
                    "(~/.ssh con modo 700 y authorized_keys con modo 600, ambos de alice)."
                ),
                points=10,
                checks=(
                    AuthorizedKeyPresent(
                        runner, "/home/alice/.ssh/authorized_keys", "/root/.ssh/id_ed25519.pub"
                    ),
                    PathHasOwner(runner, "/home/alice/.ssh", "alice"),
                    PathHasMode(runner, "/home/alice/.ssh", "700"),
                    PathHasOwner(runner, "/home/alice/.ssh/authorized_keys", "alice"),
                    PathHasMode(runner, "/home/alice/.ssh/authorized_keys", "600"),
                ),
            ),
            Task(
                id="dnf-01",
                block=ObjectiveBlock.MANAGE_SOFTWARE,
                description=(
                    "Asegura que el repositorio defectuoso exam-internal no este habilitado "
                    "(deshabilitalo o eliminalo)."
                ),
                points=10,
                checks=(RepoNotEnabled(runner, "exam-internal"),),
            ),
            Task(
                id="pkg-01",
                block=ObjectiveBlock.MANAGE_SOFTWARE,
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
                block=ObjectiveBlock.RUNNING_SYSTEMS,
                description=(
                    "Aplica el perfil de tuned recomendado para esta VM (virtual-guest)."
                ),
                points=10,
                checks=(TunedProfileIs(runner, "virtual-guest"),),
            ),
            Task(
                id="scr-01",
                block=ObjectiveBlock.SHELL_SCRIPTS,
                description=(
                    "Crea el script ejecutable /usr/local/bin/sysinfo.sh (bash) que escriba el "
                    "hostname del sistema en /root/sysinfo.txt (en una linea propia), y ejecutalo "
                    f"una vez (el hostname configurado en net-02: {LAB_HOSTNAME})."
                ),
                points=10,
                checks=(
                    FileIsExecutable(runner, "/usr/local/bin/sysinfo.sh"),
                    ScriptHasShebang(runner, "/usr/local/bin/sysinfo.sh", "/bin/bash"),
                    ScriptSyntaxValid(runner, "/usr/local/bin/sysinfo.sh"),
                    FileContainsLine(runner, "/root/sysinfo.txt", LAB_HOSTNAME),
                ),
            ),
            Task(
                id="scr-02",
                block=ObjectiveBlock.SHELL_SCRIPTS,
                description=(
                    "Crea el script ejecutable /usr/local/bin/etc-backup.sh (bash) que genere "
                    "el archivo comprimido con gzip /root/backups/etc.tar.gz con el contenido "
                    "de /etc, y ejecutalo una vez: se evalua el archivo resultante, no la "
                    "ejecucion del script."
                ),
                points=10,
                checks=(
                    FileIsExecutable(runner, "/usr/local/bin/etc-backup.sh"),
                    ScriptHasShebang(runner, "/usr/local/bin/etc-backup.sh", "/bin/bash"),
                    ScriptSyntaxValid(runner, "/usr/local/bin/etc-backup.sh"),
                    ArchiveContains(
                        runner, "/root/backups/etc.tar.gz", "gzip", ("etc/hosts", "etc/fstab")
                    ),
                ),
            ),
            Task(
                id="prc-01",
                block=ObjectiveBlock.RUNNING_SYSTEMS,
                description=(
                    "Baja la prioridad del demonio crond (que ya esta en ejecucion) a un "
                    "valor nice de 10 sin reiniciarlo; debe seguir ejecutandose como root."
                ),
                points=10,
                checks=(ProcessRunning(runner, "crond", nice=10, user="root"),),
            ),
            Task(
                id="log-01",
                block=ObjectiveBlock.RUNNING_SYSTEMS,
                description=(
                    "Haz que el registro de systemd-journald sea persistente tras los "
                    "reinicios: crea /var/log/journal y configura Storage=persistent."
                ),
                points=10,
                checks=(JournalPersistent(runner),),
            ),
            Task(
                id="run-01",
                block=ObjectiveBlock.RUNNING_SYSTEMS,
                description=(
                    "Copia de forma segura con scp desde localhost el fichero /etc/services "
                    "a /root/services.bak."
                ),
                points=10,
                checks=(FilesIdentical(runner, "/etc/services", "/root/services.bak"),),
            ),
            Task(
                id="ess-01",
                block=ObjectiveBlock.ESSENTIAL_TOOLS,
                description=(
                    "Crea una copia de seguridad de /etc como archivo tar comprimido con "
                    "gzip en /root/etc-backup.tar.gz."
                ),
                points=10,
                checks=(
                    ArchiveContains(
                        runner, "/root/etc-backup.tar.gz", "gzip", ("etc/fstab", "etc/hosts")
                    ),
                ),
            ),
            Task(
                id="ess-02",
                block=ObjectiveBlock.ESSENTIAL_TOOLS,
                description=(
                    "Crea el enlace simbolico /root/hosts-link que apunte a /etc/hosts; "
                    "crea ademas el fichero /root/notes.txt (con cualquier contenido) y un "
                    "enlace duro a el llamado /root/notes.hard."
                ),
                points=10,
                checks=(
                    SymlinkTo(runner, "/root/hosts-link", "/etc/hosts"),
                    HardLinkTo(runner, "/root/notes.hard", "/root/notes.txt"),
                ),
            ),
            Task(
                id="ess-03",
                block=ObjectiveBlock.ESSENTIAL_TOOLS,
                description=(
                    "Guarda en /root/nologin.txt, en el mismo orden, las lineas de "
                    "/etc/passwd que contengan la cadena nologin."
                ),
                points=10,
                checks=(GrepOutputSaved(runner, "/etc/passwd", "nologin", "/root/nologin.txt"),),
            ),
            Task(
                id="dep-01",
                block=ObjectiveBlock.DEPLOY_MAINTAIN,
                description=(
                    "Crea en /etc/systemd/system la unidad backup.service y el temporizador "
                    "backup.timer con OnCalendar=daily; deja backup.timer habilitado y activo."
                ),
                points=10,
                checks=(
                    TimerOnCalendar(runner, "backup.timer", "*-*-* 00:00:00"),
                    UnitFileStateIs(runner, "backup.timer", "enabled"),
                    UnitActiveStateIs(runner, "backup.timer", "active"),
                ),
            ),
            Task(
                id="dep-02",
                block=ObjectiveBlock.DEPLOY_MAINTAIN,
                description=(
                    "Configura chrony como cliente NTP con el servidor classroom.example.com; "
                    "deja chronyd habilitado y en ejecucion."
                ),
                points=10,
                checks=(
                    ChronySource(runner, "classroom.example.com"),
                    UnitFileStateIs(runner, "chronyd.service", "enabled"),
                    UnitActiveStateIs(runner, "chronyd.service", "active"),
                ),
            ),
            Task(
                id="dep-03",
                block=ObjectiveBlock.DEPLOY_MAINTAIN,
                description=(
                    "Modifica el gestor de arranque para que todos los kernels arranquen con "
                    "el argumento systemd.show_status=1 (grubby)."
                ),
                points=10,
                checks=(KernelArgPresent(runner, "systemd.show_status=1"),),
            ),
        ]
    )
