from __future__ import annotations

import ipaddress
import re

_ACCOUNT_NAME_RE = re.compile(r"[a-z_][a-z0-9_-]{0,31}")
_LVM_NAME_RE = re.compile(r"[A-Za-z0-9+_.][A-Za-z0-9+_.-]{0,126}")
_BLOCK_DEVICE_RE = re.compile(r"/dev/[A-Za-z0-9_][A-Za-z0-9_./:-]*")
_FSTYPE_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,31}")
_UUID_RE = re.compile(
    r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
    r"|[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}"
)
_UNIT_NAME_RE = re.compile(
    r"[A-Za-z0-9:_@][A-Za-z0-9:_.@-]{0,249}"
    r"\.(?:service|socket|timer|target|mount|path|automount|swap)"
)
_ZONE_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,16}")
_FIREWALL_SERVICE_RE = re.compile(r"[a-z0-9][a-z0-9_.+-]{0,63}")
_SSHD_KEYWORD_RE = re.compile(r"[a-z][a-z0-9]{0,63}")
_SELINUX_NAME_RE = re.compile(r"[a-z][a-z0-9_]{0,127}")
_HOSTNAME_LABEL_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_REPO_ID_RE = re.compile(r"[A-Za-z0-9_.:][A-Za-z0-9_.:-]{0,99}")
_PACKAGE_NAME_RE = re.compile(r"[A-Za-z0-9_+.][A-Za-z0-9_+.-]{0,127}")
_TUNED_PROFILE_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
_LOGIN_DEFS_KEY_RE = re.compile(r"[A-Z_][A-Z0-9_]*")
_PROTOCOLS = frozenset({"tcp", "udp", "sctp", "dccp"})
_ACL_PERMS = r"[r-][w-][x-]"
_ACL_ENTRY_RE = re.compile(
    rf"(?:default:)?(?:(?:user|group):(?:[a-z_][a-z0-9_-]{{0,31}})?|(?:mask|other):):"
    rf"{_ACL_PERMS}"
)


def parse_octal_mode(text: str) -> int:
    """Convierte un modo octal ('640', '0640', '2770') a int. ValueError si es invalido."""
    if not text or len(text) > 4 or any(c not in "01234567" for c in text):
        raise ValueError(f"invalid octal mode: {text!r}")
    return int(text, 8)


def validate_account_name(name: str) -> str:
    if not _ACCOUNT_NAME_RE.fullmatch(name):
        raise ValueError(f"invalid user/group name: {name!r}")
    return name


def validate_absolute_path(path: str) -> str:
    if not path.startswith("/") or "\x00" in path or "\n" in path:
        raise ValueError(f"path must be absolute and free of control chars: {path!r}")
    return path


def validate_lvm_name(name: str) -> str:
    """Nombres de VG/LV: sin '-' inicial y distintos de '.' y '..'."""
    if not _LVM_NAME_RE.fullmatch(name) or name in {".", ".."}:
        raise ValueError(f"invalid LVM name: {name!r}")
    return name


def validate_block_device(path: str) -> str:
    if not _BLOCK_DEVICE_RE.fullmatch(path) or ".." in path.split("/"):
        raise ValueError(f"invalid block device path: {path!r}")
    return path


def validate_fstype(name: str) -> str:
    if not _FSTYPE_RE.fullmatch(name):
        raise ValueError(f"invalid filesystem type: {name!r}")
    return name


def validate_uuid(value: str) -> str:
    """UUID de sistema de archivos: forma larga o corta de vfat (XXXX-XXXX)."""
    if not _UUID_RE.fullmatch(value):
        raise ValueError(f"invalid filesystem UUID: {value!r}")
    return value


def validate_acl_entry(entry: str) -> str:
    """Entrada ACL en formato getfacl: [default:]user|group:<nombre>:rwx o mask|other::rwx."""
    if not _ACL_ENTRY_RE.fullmatch(entry):
        raise ValueError(f"invalid ACL entry: {entry!r}")
    return entry


def validate_unit_name(name: str) -> str:
    """Nombre de unidad systemd con sufijo conocido; sin '-' ni '.' inicial."""
    if not _UNIT_NAME_RE.fullmatch(name):
        raise ValueError(f"invalid systemd unit name: {name!r}")
    return name


def validate_zone(name: str) -> str:
    """Zona de firewalld: hasta 17 caracteres y sin '-' inicial."""
    if not _ZONE_RE.fullmatch(name):
        raise ValueError(f"invalid firewalld zone: {name!r}")
    return name


def validate_firewall_service(name: str) -> str:
    if not _FIREWALL_SERVICE_RE.fullmatch(name):
        raise ValueError(f"invalid firewalld service: {name!r}")
    return name


def validate_port(port: int) -> int:
    """Puerto 1-65535; un bool no cuenta como entero."""
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError(f"invalid port: {port!r}")
    return port


def validate_protocol(proto: str) -> str:
    if proto not in _PROTOCOLS:
        raise ValueError(f"invalid protocol: {proto!r}")
    return proto


def validate_selinux_type(name: str) -> str:
    """Tipo SELinux: minusculas, digitos y '_', y termina en '_t'."""
    if not _SELINUX_NAME_RE.fullmatch(name) or not name.endswith("_t"):
        raise ValueError(f"invalid SELinux type: {name!r}")
    return name


def validate_selinux_boolean(name: str) -> str:
    if not _SELINUX_NAME_RE.fullmatch(name):
        raise ValueError(f"invalid SELinux boolean: {name!r}")
    return name


def validate_connection_name(name: str) -> str:
    """Nombre de perfil NetworkManager: 1-64 caracteres imprimibles, sin '-' inicial
    ni espacios en los extremos."""
    if (
        not 1 <= len(name) <= 64
        or not name.isprintable()
        or name.startswith("-")
        or name != name.strip()
    ):
        raise ValueError(f"invalid connection name: {name!r}")
    return name


def validate_ipv4_interface(text: str) -> ipaddress.IPv4Interface:
    """Direccion IPv4 con prefijo obligatorio (a.b.c.d/n), normalizada."""
    if "/" not in text:
        raise ValueError(f"IPv4 address needs a /prefix: {text!r}")
    try:
        return ipaddress.IPv4Interface(text)
    except ValueError:
        raise ValueError(f"invalid IPv4 interface: {text!r}") from None


def validate_ipv4_address(text: str) -> ipaddress.IPv4Address:
    try:
        return ipaddress.IPv4Address(text)
    except ValueError:
        raise ValueError(f"invalid IPv4 address: {text!r}") from None


def validate_hostname(name: str) -> str:
    """Hostname tipo FQDN en minusculas: etiquetas de 1-63 caracteres, total <= 253."""
    if len(name) > 253 or not all(
        _HOSTNAME_LABEL_RE.fullmatch(label) for label in name.split(".")
    ):
        raise ValueError(f"invalid hostname: {name!r}")
    return name


def validate_sshd_keyword(name: str) -> str:
    """Keyword de sshd -T: minusculas y digitos, tal como las imprime sshd."""
    if not _SSHD_KEYWORD_RE.fullmatch(name):
        raise ValueError(f"invalid sshd keyword: {name!r}")
    return name


def validate_login_defs_key(name: str) -> str:
    """Clave de /etc/login.defs: mayusculas, digitos y '_'."""
    if not _LOGIN_DEFS_KEY_RE.fullmatch(name):
        raise ValueError(f"invalid login.defs key: {name!r}")
    return name


def validate_repo_id(name: str) -> str:
    """Id de repositorio dnf: sin '-' inicial."""
    if not _REPO_ID_RE.fullmatch(name):
        raise ValueError(f"invalid repository id: {name!r}")
    return name


def validate_package_name(name: str) -> str:
    """Nombre de paquete rpm: sin '-' inicial (se usa tras '--')."""
    if not _PACKAGE_NAME_RE.fullmatch(name):
        raise ValueError(f"invalid package name: {name!r}")
    return name


def validate_tuned_profile(name: str) -> str:
    if not _TUNED_PROFILE_RE.fullmatch(name):
        raise ValueError(f"invalid tuned profile: {name!r}")
    return name


def validate_kernel_arg(arg: str) -> str:
    """Argumento de kernel: sin espacios/NUL y sin '-' inicial (se pasa a grubby)."""
    if not arg or arg.startswith("-") or any(c.isspace() or c == "\0" for c in arg):
        raise ValueError(f"invalid kernel argument: {arg!r}")
    return arg
