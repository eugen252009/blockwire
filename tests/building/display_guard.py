"""Read-only POSIX benchmark isolation proof. Not a runtime/gameplay capability.

Launcher environment is not proof of a child's display: singleton IPC can forward
an instance launch to an unrelated GUI. Check the actual game process BEFORE any
native connection or measurement. Never kill processes or fall back to :0 here.
"""
from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class ProcessProof:
    pid: int
    uid: int
    start_time: str
    cwd: Path
    display: str | None
    argv: tuple[str, ...]


def inspect_process(pid: int, *, proc_root=Path('/proc')) -> ProcessProof:
    if type(pid) is not int or pid <= 0:
        raise ValueError('Explicit positive process ID required')
    process = Path(proc_root) / str(pid)
    try:
        before = (process / 'stat').read_text().rsplit(')', 1)[1].split()[19]
        uid = process.stat().st_uid
        cwd = (process / 'cwd').resolve(strict=True)
        argv = tuple(part.decode() for part in (process / 'cmdline').read_bytes().split(b'\0') if part)
        environment = (process / 'environ').read_bytes().split(b'\0')
        displays = [part[len(b'DISPLAY='):].decode() for part in environment if part.startswith(b'DISPLAY=')]
        after = (process / 'stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, UnicodeError, IndexError) as error:
        raise RuntimeError('Cannot prove benchmark process identity') from error
    if before != after or len(displays) != 1:
        raise RuntimeError('Unstable process or unproven display')
    return ProcessProof(pid, uid, before, cwd, displays[0], argv)


def require_hidden_game(proof: ProcessProof, game_directory: Path, *, display=':99', uid=None):
    if display == ':0' or not display.startswith(':'):
        raise ValueError('Explicit isolated display required; no visible fallback')
    uid = os.getuid() if uid is None else uid
    if (proof.uid != uid or proof.cwd != Path(game_directory).resolve()
            or proof.display != display or 'org.prismlauncher.EntryPoint' not in proof.argv):
        raise RuntimeError('Native benchmark process is not isolated on the selected display')
    return proof


def require_no_foreign_launcher(proofs, launcher_directory: Path, *, display=':99', uid=None):
    """Prelaunch guard for the selected launcher's shared singleton/IPC home."""
    uid = os.getuid() if uid is None else uid
    directory = Path(launcher_directory).resolve()
    for proof in proofs:
        launcher = any(Path(arg).name.lower() in {'prismlauncher', 'prismlauncher-bin', 'prismrun'} for arg in proof.argv)
        if proof.uid == uid and proof.cwd == directory and launcher and proof.display != display:
            raise RuntimeError('Foreign-display launcher owns the shared IPC home; do not launch or terminate it')
