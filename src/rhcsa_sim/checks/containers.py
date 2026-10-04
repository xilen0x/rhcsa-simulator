from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from rhcsa_sim.checks._validation import (
    validate_absolute_path,
    validate_account_name,
    validate_port,
    validate_protocol,
    validate_unit_name,
)
from rhcsa_sim.models import CheckResult
from rhcsa_sim.runner import CommandResult, CommandRunner

# Solo lectura: nunca se descarga, arranca ni para nada. Podman rootless se ejecuta como
# el usuario del examen desde root (runuser), asi que estos checks necesitan sudo.
_ROOT_HINT = "run with sudo (rootless podman is queried as the user)"
_UNEXPECTED = "unexpected podman output"
_LINGER_DIR = "/var/lib/systemd/linger"
_PERMISSION_MARKERS = ("non-root", "Permission denied", "Access denied")
_CONTAINER_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_QUADLET_NAME_RE = re.compile(r"[A-Za-z0-9_@][A-Za-z0-9_.@-]{0,199}")


def _validate_image(image: str) -> str:
    if not image or image.startswith("-") or any(c.isspace() or c == "\x00" for c in image):
        raise ValueError(f"invalid image reference: {image!r}")
    return image


def _validate_container_name(name: str) -> str:
    if not _CONTAINER_NAME_RE.fullmatch(name):
        raise ValueError(f"invalid container name: {name!r}")
    return name


def _validate_quadlet_name(name: str) -> str:
    """Nombre base del .container: sin '/', sin '-' ni '.' iniciales."""
    if not _QUADLET_NAME_RE.fullmatch(name):
        raise ValueError(f"invalid quadlet unit name: {name!r}")
    return name


def _normalize_image(image: str) -> str:
    """Anade ':latest' si la referencia no lleva tag ni digest, para comparar
    'repo/img' con el 'repo/img:latest' que informa podman."""
    if "@" in image or ":" in image.rsplit("/", 1)[-1]:
        return image
    return f"{image}:latest"


def _first_line(text: str) -> str:
    lines = text.strip().splitlines()
    return lines[0] if lines else ""


def _denied(result: CommandResult) -> bool:
    return any(marker in result.stderr for marker in _PERMISSION_MARKERS)


def _failure(what: str, result: CommandResult) -> CheckResult:
    if _denied(result):
        return CheckResult(False, f"cannot {what}: {_ROOT_HINT}")
    detail = _first_line(result.stderr)
    suffix = f": {detail}" if detail else ""
    return CheckResult(False, f"cannot {what} (exit {result.returncode}){suffix}")


def _run_podman(
    runner: CommandRunner, user: str, args: list[str]
) -> CommandResult | CheckResult:
    """Ejecuta `podman <args>` como `user` con su XDG_RUNTIME_DIR. Devuelve el
    resultado del comando o un CheckResult fallido si no se resuelve el uid."""
    uid_result = runner.run(["id", "-u", "--", user])
    uid = uid_result.stdout.strip()
    if not uid_result.ok or not uid.isdigit():
        return CheckResult(False, f"cannot resolve uid of user '{user}'")
    # Sin /run/user/<uid> (sin linger ni sesion) un XDG_RUNTIME_DIR inexistente hace
    # fallar a podman; sin la variable usa su directorio alternativo y sigue viendo
    # las imagenes del usuario. Linger se evalua aparte (LingerEnabled).
    # `-C /`: runuser conserva el cwd del invocador y, si el usuario no puede
    # entrar en el, podman aborta ("cannot chdir", rc 125).
    if runner.run(["stat", "-c", "%F", "--", f"/run/user/{uid}"]).ok:
        env = ["env", "-C", "/", f"XDG_RUNTIME_DIR=/run/user/{uid}"]
    else:
        env = ["env", "-C", "/", "-u", "XDG_RUNTIME_DIR"]
    return runner.run(["runuser", "-u", user, "--", *env, "podman", *args])


def _load_json(text: str) -> object:
    try:
        return json.loads(text)
    except ValueError:
        return None


def _inspect(
    runner: CommandRunner, user: str, name: str, template: str
) -> object | CheckResult:
    """`podman inspect --format <template>` ya decodificado (JSON, `None` si es
    `null`); los callers estrechan el tipo. rc 125 = no existe."""
    result = _run_podman(runner, user, ["inspect", "--format", template, "--", name])
    if isinstance(result, CheckResult):
        return result
    if result.returncode == 125 and not _denied(result):
        return CheckResult(False, f"container not found: '{name}'")
    if not result.ok:
        return _failure(f"inspect container '{name}'", result)
    data = _load_json(result.stdout)
    if data is None and result.stdout.strip() != "null":
        return CheckResult(False, _UNEXPECTED)
    return data


@dataclass(frozen=True, slots=True)
class LingerEnabled:
    runner: CommandRunner
    user: str

    def __post_init__(self) -> None:
        validate_account_name(self.user)

    def describe(self) -> str:
        return f"linger is enabled for {self.user}"

    def run(self) -> CheckResult:
        result = self.runner.run(["stat", "-c", "%F", "--", f"{_LINGER_DIR}/{self.user}"])
        if not result.ok:
            return CheckResult(False, f"linger not enabled for {self.user}")
        return CheckResult(True, f"linger is enabled for {self.user}")


@dataclass(frozen=True, slots=True)
class ContainerImageExists:
    runner: CommandRunner
    user: str
    image: str

    def __post_init__(self) -> None:
        validate_account_name(self.user)
        _validate_image(self.image)

    def describe(self) -> str:
        return f"{self.user} has image {self.image}"

    def run(self) -> CheckResult:
        result = _run_podman(self.runner, self.user, ["image", "exists", "--", self.image])
        if isinstance(result, CheckResult):
            return result
        if result.ok:
            return CheckResult(True, f"image '{self.image}' is present")
        if result.returncode == 1 and not _denied(result):
            return CheckResult(False, f"image '{self.image}' is not present for {self.user}")
        return _failure(f"query image '{self.image}'", result)


def _parse_containers(stdout: str) -> list[dict[str, Any]] | None:
    data = _load_json(stdout)
    if not isinstance(data, list):
        return None
    for item in data:
        names = item.get("Names") if isinstance(item, dict) else None
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            return None
    return data


@dataclass(frozen=True, slots=True)
class ContainerRunning:
    """Contenedor con ese nombre exacto en estado running. Si se indica `image`
    se compara normalizando el tag ':latest' implicito."""

    runner: CommandRunner
    user: str
    name: str
    image: str | None = None

    def __post_init__(self) -> None:
        validate_account_name(self.user)
        _validate_container_name(self.name)
        if self.image is not None:
            _validate_image(self.image)

    def describe(self) -> str:
        suffix = f" from {self.image}" if self.image else ""
        return f"container {self.name}{suffix} is running for {self.user}"

    def run(self) -> CheckResult:
        # -a para distinguir "parado" de "inexistente"
        result = _run_podman(self.runner, self.user, ["ps", "-a", "--format", "json"])
        if isinstance(result, CheckResult):
            return result
        if not result.ok:
            return _failure("list containers", result)
        containers = _parse_containers(result.stdout)
        if containers is None:
            return CheckResult(False, _UNEXPECTED)
        found = next((c for c in containers if self.name in c["Names"]), None)
        if found is None:
            return CheckResult(False, f"container not found: '{self.name}'")
        state = found.get("State")
        if state != "running":
            return CheckResult(False, f"container '{self.name}' is {state}, expected running")
        actual = found.get("Image")
        if self.image is not None and (
            not isinstance(actual, str)
            or _normalize_image(actual) != _normalize_image(self.image)
        ):
            return CheckResult(False, f"container image is {actual}, expected {self.image}")
        return CheckResult(True, f"container '{self.name}' is running")


@dataclass(frozen=True, slots=True)
class ContainerPublishesPort:
    runner: CommandRunner
    user: str
    name: str
    host_port: int
    container_port: int
    protocol: str = "tcp"

    def __post_init__(self) -> None:
        validate_account_name(self.user)
        _validate_container_name(self.name)
        validate_port(self.host_port)
        validate_port(self.container_port)
        validate_protocol(self.protocol)

    def describe(self) -> str:
        return (
            f"container {self.name} publishes {self.host_port}->"
            f"{self.container_port}/{self.protocol}"
        )

    def run(self) -> CheckResult:
        data = _inspect(
            self.runner, self.user, self.name, "{{json .HostConfig.PortBindings}}"
        )
        if isinstance(data, CheckResult):
            return data
        if data is None or data == {}:
            return CheckResult(False, f"container '{self.name}' has no published ports")
        if not isinstance(data, dict):
            return CheckResult(False, _UNEXPECTED)
        key = f"{self.container_port}/{self.protocol}"
        hosts: list[str] = []
        for bindings in data.values():
            if not isinstance(bindings, list) or not all(isinstance(b, dict) for b in bindings):
                return CheckResult(False, _UNEXPECTED)
        for binding in data.get(key) or []:
            hosts.append(str(binding.get("HostPort", "")))
        if str(self.host_port) in hosts:
            return CheckResult(True, f"{self.host_port} -> {key} is published")
        if not hosts:
            return CheckResult(False, f"port {key} is not published")
        return CheckResult(
            False, f"port {key} is published on {', '.join(hosts)}, expected {self.host_port}"
        )


@dataclass(frozen=True, slots=True)
class ContainerHasBindMount:
    runner: CommandRunner
    user: str
    name: str
    source: str
    destination: str

    def __post_init__(self) -> None:
        validate_account_name(self.user)
        _validate_container_name(self.name)
        validate_absolute_path(self.source)
        validate_absolute_path(self.destination)

    def describe(self) -> str:
        return f"container {self.name} mounts {self.source} on {self.destination}"

    def run(self) -> CheckResult:
        data = _inspect(self.runner, self.user, self.name, "{{json .Mounts}}")
        if isinstance(data, CheckResult):
            return data
        mounts = [] if data is None else data
        if not isinstance(mounts, list) or not all(isinstance(m, dict) for m in mounts):
            return CheckResult(False, _UNEXPECTED)
        for mount in mounts:
            if (
                mount.get("Type") == "bind"
                and mount.get("Source") == self.source
                and mount.get("Destination") == self.destination
            ):
                return CheckResult(True, f"{self.source} is bind-mounted on {self.destination}")
        return CheckResult(
            False, f"no bind mount {self.source} -> {self.destination} in '{self.name}'"
        )


def _parse_ini(text: str) -> dict[str, list[tuple[str, str]]]:
    """INI minimo de systemd: secciones [X], pares K=V (con espacios), ignora
    comentarios (# y ;). Las claves repetidas se conservan en orden."""
    sections: dict[str, list[tuple[str, str]]] = {}
    current: list[tuple[str, str]] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("[") and line.endswith("]"):
            current = sections.setdefault(line[1:-1], [])
            continue
        key, sep, value = line.partition("=")
        if sep and current is not None:
            current.append((key.strip(), value.strip()))
    return sections


@dataclass(frozen=True, slots=True)
class QuadletUnitDefined:
    """`~user/.config/containers/systemd/<name>.container` con [Container]
    (con `Image=` y `ContainerName=` si se indican) y `[Install] WantedBy=`
    incluyendo `wanted_by`. Sin ContainerName= Quadlet nombra el contenedor
    `systemd-<name>`, no `<name>`."""

    runner: CommandRunner
    user: str
    name: str
    image: str | None = None
    wanted_by: str = "default.target"
    container_name: str | None = None

    def __post_init__(self) -> None:
        validate_account_name(self.user)
        _validate_quadlet_name(self.name)
        if self.image is not None:
            _validate_image(self.image)
        if self.container_name is not None:
            _validate_container_name(self.container_name)
        validate_unit_name(self.wanted_by)

    def describe(self) -> str:
        return f"{self.user} has quadlet {self.name}.container wanted by {self.wanted_by}"

    def _home(self) -> str | CheckResult:
        result = self.runner.run(["getent", "passwd", self.user])
        fields = result.stdout.strip().split(":")
        if not result.ok or len(fields) < 6:
            return CheckResult(False, f"cannot resolve home of user '{self.user}'")
        try:
            return validate_absolute_path(fields[5])
        except ValueError:
            return CheckResult(False, f"unexpected home directory for '{self.user}'")

    def run(self) -> CheckResult:
        home = self._home()
        if isinstance(home, CheckResult):
            return home
        path = f"{home}/.config/containers/systemd/{self.name}.container"
        result = self.runner.run(["cat", "--", path])
        if not result.ok:
            if _denied(result):
                return CheckResult(False, f"cannot read '{path}': {_ROOT_HINT}")
            return CheckResult(False, f"cannot read '{path}'")
        sections = _parse_ini(result.stdout)
        container = sections.get("Container")
        if container is None:
            return CheckResult(False, f"{path} has no [Container] section")
        if self.image is not None:
            images = [v for k, v in container if k == "Image"]
            if not any(_normalize_image(i) == _normalize_image(self.image) for i in images):
                shown = images[-1] if images else "(none)"
                return CheckResult(False, f"Image= is {shown}, expected {self.image}")
        if self.container_name is not None:
            names = [v for k, v in container if k == "ContainerName"]
            if not names or names[-1] != self.container_name:
                shown = names[-1] if names else "(none)"
                return CheckResult(
                    False, f"ContainerName= is {shown}, expected {self.container_name}"
                )
        wanted = [
            target
            for key, value in sections.get("Install", [])
            if key == "WantedBy"
            for target in value.split()
        ]
        if self.wanted_by not in wanted:
            return CheckResult(False, f"[Install] WantedBy= does not include {self.wanted_by}")
        return CheckResult(True, f"{self.name}.container is defined and wanted by {self.wanted_by}")


@dataclass(frozen=True, slots=True)
class UserServiceActive:
    """Unidad del gestor de usuario (`systemctl --user -M user@`) cargada y activa."""

    runner: CommandRunner
    user: str
    unit: str

    def __post_init__(self) -> None:
        validate_account_name(self.user)
        validate_unit_name(self.unit)

    def describe(self) -> str:
        return f"user service {self.unit} is active for {self.user}"

    def run(self) -> CheckResult:
        result = self.runner.run(
            [
                "systemctl", "--user", "-M", f"{self.user}@",
                "show", "-p", "LoadState,ActiveState", "--", self.unit,
            ]
        )  # fmt: skip
        hint = "the user manager must be running (enable linger)"
        if not result.ok:
            if _denied(result):
                return CheckResult(False, f"cannot query user unit: {_ROOT_HINT}")
            return CheckResult(
                False, f"cannot query user unit '{self.unit}' (exit {result.returncode}): {hint}"
            )
        props = dict(
            line.partition("=")[::2] for line in result.stdout.splitlines() if "=" in line
        )
        if "LoadState" not in props or "ActiveState" not in props:
            return CheckResult(False, f"unexpected systemctl output for '{self.unit}'")
        if props["LoadState"] != "loaded":
            return CheckResult(
                False, f"user unit '{self.unit}' is {props['LoadState']}; {hint}"
            )
        if props["ActiveState"] != "active":
            return CheckResult(
                False, f"user unit '{self.unit}' is {props['ActiveState']}, expected active"
            )
        return CheckResult(True, f"user unit '{self.unit}' is active")
