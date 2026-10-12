"""Theme-only installer; Python >= 3.11, standard library only."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import platform
import re
import tomllib
import shutil
import subprocess


def _validate_lua(content: bytes, env: dict, label: str) -> None:
    executable = shutil.which('nvim', path=env.get('PATH', ''))
    if not executable:
        raise InstallerError('Neovim requires nvim on PATH for safe loadfile validation; no files changed')
    scratch = Path(os.environ.get('TMPDIR') or tempfile.gettempdir())
    if not scratch.is_dir():
        raise InstallerError('Set TMPDIR to an existing scratch directory for Lua validation')
    with tempfile.TemporaryDirectory(prefix='terminal-theme-lua-', dir=scratch) as directory:
        root = Path(directory)
        source = root / 'proposed.lua'
        source.write_bytes(content)
        isolated = dict(env)
        isolated.update(HOME=str(root), XDG_CONFIG_HOME=str(root / 'config'),
                        XDG_STATE_HOME=str(root / 'state'), XDG_DATA_HOME=str(root / 'data'),
                        XDG_CACHE_HOME=str(root / 'cache'), NVIM_APPNAME='theme-validator',
                        TERMINAL_THEME_LUA=str(source))
        command = 'lua local f = loadfile(vim.env.TERMINAL_THEME_LUA); if not f then vim.cmd("cquit 1") end'
        try:
            result = subprocess.run([executable, '--headless', '-u', 'NONE', '-i', 'NONE', '-n',
                                     '--cmd', command, '+qa!'], env=isolated,
                                    capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise InstallerError(f'Could not validate {label} with headless Neovim') from exc
        if result.returncode != 0:
            raise InstallerError(f'Invalid Lua in proposed {label}; integrate manually (top-level return may prevent appending)')
import hashlib
import json
import stat
import tempfile
import uuid
from datetime import datetime, timezone


@dataclass(frozen=True)
class Change:
    requested: Path
    path: Path
    before: bytes | None
    mode: int | None
    after: bytes | None


@dataclass(frozen=True)
class Result:
    backup: Path | None
    changed: tuple[Path, ...]
    warnings: tuple[str, ...] = ()


def _digest(data: bytes | None) -> str | None:
    return None if data is None else hashlib.sha256(data).hexdigest()


def _snapshot(path: Path) -> tuple[bytes | None, int | None]:
    if path.is_symlink():
        raise InstallerError(f'Unexpected symlink at resolved target: {path}')
    if not path.exists():
        return None, None
    if not path.is_file():
        raise InstallerError(f'Target is not a regular file: {path}')
    if path.stat().st_nlink != 1:
        raise InstallerError(f'Hardlinked targets are unsupported (atomic writes would break the link): {path}')
    return path.read_bytes(), stat.S_IMODE(path.stat().st_mode)


def _change(requested: Path, after: bytes | None) -> Change:
    requested = _absolute(requested, Path.home())
    if requested.is_symlink() and not requested.exists():
        raise InstallerError(f'Dangling symlink is unsupported: {requested}')
    path = requested.resolve()
    _absolute(path, Path.home())
    before, mode = _snapshot(path)
    return Change(requested, path, before, mode, after)


def _check_overlap(changes: list[Change]) -> None:
    targets = [change.path for change in changes]
    for i, path in enumerate(targets):
        for other in targets[i + 1:]:
            if path == other or path in other.parents or other in path.parents:
                raise InstallerError(f'Overlapping target files: {path} and {other}')


def _ensure_dirs(directory: Path, created: list[Path]) -> None:
    missing = []
    while not directory.exists():
        missing.append(directory)
        directory = directory.parent
    if not directory.is_dir():
        raise InstallerError(f'Parent is not a directory: {directory}')
    for path in reversed(missing):
        path.mkdir(mode=0o700)
        created.append(path)


def _atomic_write(path: Path, content: bytes | None, mode: int | None, created=None) -> None:
    created = [] if created is None else created
    if path.is_symlink():
        raise InstallerError(f'Refusing to replace symlink: {path}')
    if content is None:
        if path.exists():
            if not path.is_file():
                raise InstallerError(f'Refusing to remove non-file: {path}')
            path.unlink()
        return
    _ensure_dirs(path.parent, created)
    fd, temporary = tempfile.mkstemp(prefix='.terminal-theme-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), mode if mode is not None else 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if _snapshot(path) != (content, mode if mode is not None else 0o600):
            raise InstallerError(f'Write verification failed: {path}')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _clean_dirs(created: list[Path]) -> None:
    for path in reversed(created):
        try:
            path.rmdir()
        except OSError:
            pass  # Do not remove user data or directories that are no longer empty.


def _manifest_write(backup: Path, manifest: dict) -> None:
    data = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
    _atomic_write(backup / 'manifest.json', data, 0o600)


def _validate_backup_location(repo: Path, backup: Path, changes: list[Change]) -> None:
    backup = backup.resolve()
    if backup == repo.resolve() or repo.resolve() in backup.parents:
        raise InstallerError('Backups must be outside the repository')
    if backup.exists():
        raise InstallerError(f'Backup directory already exists: {backup}')
    for change in changes:
        if backup == change.path or backup in change.path.parents or change.path in backup.parents:
            raise InstallerError('Backup directory overlaps a target file')


def _make_backup(repo: Path, backup: Path, changes: list[Change], metadata=None) -> dict:
    _validate_backup_location(repo, backup, changes)
    _ensure_dirs(backup.parent, [])
    backup.mkdir(mode=0o700)
    (backup / 'files').mkdir(mode=0o700)
    records = []
    for i, change in enumerate(changes):
        payload = f'files/{i}' if change.before is not None else None
        if payload:
            _atomic_write(backup / payload, change.before, 0o600)
        records.append({'requested': str(change.requested), 'path': str(change.path),
                        'original': payload, 'before_sha256': _digest(change.before),
                        'before_mode': change.mode, 'after_sha256': _digest(change.after),
                        'after_mode': change.mode if change.mode is not None else 0o600})
    manifest = {'version': 1, 'status': 'pending', 'files': records,
                'created_dirs': [], 'metadata': metadata or {}}
    _manifest_write(backup, manifest)
    return manifest


def _assert_unchanged(change: Change) -> None:
    if change.requested.resolve() != change.path or _snapshot(change.path) != (change.before, change.mode):
        raise InstallerError(f'Target changed after preflight: {change.requested}')


def _reload_herdr(config: Path, env: dict) -> tuple[str, ...]:
    if not shutil.which('herdr', path=env.get('PATH', '')):
        return ('Herdr CLI unavailable; files saved, reload manually when the server is running.',)
    try:
        result = subprocess.run(['herdr', 'server', 'reload-config'],
                                env=dict(env, HERDR_CONFIG_PATH=str(config)),
                                capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        return ('Herdr CLI unavailable; files saved without reloading.',)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallerError('Herdr reload could not be verified') from exc
    if result.returncode:
        diagnostic = (result.stderr + result.stdout).lower()
        if any(token in diagnostic for token in ('not running', 'connection refused', 'failed to connect',
                                                  'no such file', 'not connected', 'could not connect')):
            return ('Herdr server not running; files saved, reload manually after starting it.',)
        raise InstallerError('Herdr reload failed; diagnostics suppressed for privacy')
    try:
        reply = json.loads(result.stdout)
        status = reply.get('result', reply)
        if not isinstance(status, dict) or status.get('status') != 'applied' or status.get('diagnostics'):
            raise ValueError('Reload was not cleanly applied')
    except (ValueError, AttributeError, TypeError) as exc:
        raise InstallerError('Herdr reload did not confirm status: applied with no diagnostics') from exc
    return ()


def _hermes(arguments: list[str], home: Path, env: dict) -> str:
    bound = dict(env, HERMES_HOME=str(home))
    try:
        result = subprocess.run(['hermes', *arguments], env=bound, capture_output=True,
                                text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallerError('Hermes configuration command unavailable or timed out') from exc
    if result.returncode != 0:
        # Never echo CLI diagnostics: user config can contain private values.
        raise InstallerError('Hermes configuration command failed (diagnostics suppressed for privacy)')
    return result.stdout.strip()


def _get_skin(home: Path, env: dict) -> str:
    skin = _hermes(['config', 'get', 'display.skin'], home, env)
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', skin):
        raise InstallerError('Unexpected Hermes display.skin readback; refusing to guess')
    return skin


def _validate_ghostty(content: bytes) -> None:
    allowed = {'background', 'foreground', 'cursor-color', 'cursor-text',
               'selection-background', 'selection-foreground'}
    seen = set()
    for line in content.decode('utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        match = re.fullmatch(r'\s*([a-z-]+)\s*=\s*(.*?)\s*', line)
        if not match or match[1] not in allowed | {'palette'}:
            raise InstallerError('Ghostty asset must contain color settings only')
        key, color = match[1], match[2]
        if key == 'palette':
            palette = re.fullmatch(r'([0-9]+)\s*=\s*(#[0-9a-fA-F]{6})', color)
            if not palette or not 0 <= int(palette[1]) <= 255:
                raise InstallerError('Invalid Ghostty palette assignment')
            key, color = f'palette-{int(palette[1])}', palette[2]
        if key in seen or not re.fullmatch('#[0-9a-fA-F]{6}', color):
            raise InstallerError('Invalid or duplicate Ghostty color assignment')
        seen.add(key)
    if not {'background', 'foreground'} <= seen:
        raise InstallerError('Ghostty asset must define background and foreground')


def _validate_skin(content: bytes) -> None:
    """Validate this repository's deliberately small string-mapping YAML subset.

    This is not a general YAML parser. Reject advanced YAML rather than installing
    unchecked input; no PyYAML dependency or execution of the target's config.
    """
    values = {}
    section = None
    for line in content.decode('utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        match = re.fullmatch(r'( *)([A-Za-z_][A-Za-z0-9_-]*):(?: +(.*))?', line)
        if not match or len(match[1]) not in (0, 2):
            raise InstallerError('Unsupported Hermes skin YAML; only string mappings are accepted')
        indent, key, raw = len(match[1]), match[2], match[3]
        if indent == 0:
            section = None
        if raw is None:
            if indent or key not in ('colors', 'branding') or key in values:
                raise InstallerError('Unsupported Hermes skin mapping')
            values[key] = {}
            section = key
            continue
        if raw.startswith('"'):
            try:
                value = json.loads(raw)
            except ValueError as exc:
                raise InstallerError('Invalid quoted Hermes skin string') from exc
            if not isinstance(value, str):
                raise InstallerError('Hermes skin scalars must be strings')
        elif raw.startswith("'"):
            if len(raw) < 2 or not raw.endswith("'") or not re.fullmatch(r"'(?:[^']|'')*'", raw):
                raise InstallerError('Invalid single-quoted Hermes skin string')
            value = raw[1:-1].replace("''", "'")
        else:
            if not raw or re.search(r'[\[\]{}&*!|>#?:]', raw) or raw.lower() in ('null', 'true', 'false'):
                raise InstallerError('Unsupported Hermes skin scalar')
            value = raw
        target = values if indent == 0 else values.get(section)
        if not isinstance(target, dict) or key in target:
            raise InstallerError('Duplicate or misplaced Hermes skin key')
        target[key] = value
    if values.get('name') != 'github-light' or not isinstance(values.get('colors'), dict):
        raise InstallerError('Hermes asset must be named github-light and define colors')
    if set(values) - {'name', 'description', 'colors', 'branding', 'tool_prefix'}:
        raise InstallerError('Unsupported Hermes skin root key')
    if 'background' not in values['colors'] or not all(re.fullmatch('#[0-9a-fA-F]{6}', v) for v in values['colors'].values()):
        raise InstallerError('Hermes skin colors must be explicit six-digit hex strings')


def _validate_zsh(content: bytes, env: dict) -> None:
    executable = shutil.which('zsh', path=env.get('PATH', ''))
    if not executable:
        raise InstallerError('Powerlevel10k requires zsh on PATH for syntax validation; no files changed')
    try:
        result = subprocess.run([executable, '-dfn'], input=content, env=env,
                                capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallerError('Could not validate Powerlevel10k configuration; no files changed') from exc
    if result.returncode != 0:
        raise InstallerError('Invalid Powerlevel10k configuration; no files changed')


def _p10k_target(requested: Path, env: dict) -> Path:
    home = _absolute(env.get('HOME', str(Path.home())), Path.home())
    requested = _absolute(requested, home)
    startup_names = {'.zshenv', '.zprofile', '.zshrc', '.zlogin', '.zlogout'}
    resolved = requested.resolve()
    shell_dirs = {home, _absolute(env.get('ZDOTDIR') or home, home)}
    if (requested.name.casefold() in startup_names or resolved.name.casefold() in startup_names
            or any(resolved == (directory / name).resolve()
                   or (resolved.exists() and (directory / name).exists()
                       and resolved.samefile(directory / name))
                   for directory in shell_dirs for name in startup_names)):
        raise InstallerError('Powerlevel10k must not replace zsh startup files or their aliases '
                             '(including hardlinks); no files changed')
    return requested


def install(repo: Path, paths: Paths, *, only=('ghostty', 'neovim', 'herdr', 'hermes'),
            dry_run=False, backup_dir=None, no_reload=False, env=None) -> Result:
    """Validate the complete plan before any target or backup is created."""
    repo = Path(repo).resolve()
    runtime_env = dict(os.environ if env is None else env)
    only = tuple(only)
    if not only or set(only) - {'ghostty', 'neovim', 'herdr', 'hermes', 'powerlevel10k'}:
        raise InstallerError('Select at least one supported application')
    changes = []
    if 'powerlevel10k' in only:
        target = _p10k_target(paths.p10k_config, runtime_env)
        asset = (repo / 'zsh/p10k.zsh').read_bytes()
        _validate_zsh(asset, runtime_env)
        changes.append(_change(target, asset))
    if 'ghostty' in only:
        asset = (repo / 'ghostty/github-light.conf').read_bytes()
        _validate_ghostty(asset)
        changes.append(_change(paths.ghostty_theme, asset))
        body = f'theme = {paths.ghostty_theme}\n' + asset.decode('utf-8').rstrip('\n')
        for config in paths.ghostty_configs:
            initial = _change(config, None)
            content = (initial.before or b'').decode('utf-8')
            updated = managed_block(content, body, '#').encode()
            changes.append(Change(initial.requested, initial.path, initial.before, initial.mode, updated))
    if 'herdr' in only:
        initial = _change(paths.herdr_config, None)
        content = (initial.before or b'').decode('utf-8')
        fragment = (repo / 'herdr/theme.toml').read_text(encoding='utf-8')
        updated = replace_toml_theme(content, fragment).encode()
        changes.append(Change(initial.requested, initial.path, initial.before, initial.mode, updated))
    if 'neovim' in only:
        runtime_env = dict(os.environ if env is None else env)
        init = paths.neovim_dir / 'init.lua'
        if not init.exists() and (paths.neovim_dir / 'init.vim').exists():
            raise InstallerError("init.vim-only configuration is unsupported; manually add lua require('github_light').setup() after installing the module")
        module = (repo / 'neovim/github_light.lua').read_bytes()
        initial = _change(init, None)
        updated = managed_block((initial.before or b'').decode('utf-8'), "require('github_light').setup()", '--').encode()
        _validate_lua(module, runtime_env, 'github_light.lua')
        _validate_lua(updated, runtime_env, 'init.lua')
        changes.append(_change(paths.neovim_dir / 'lua/github_light.lua', module))
        changes.append(Change(initial.requested, initial.path, initial.before, initial.mode, updated))
    runtime_env = dict(os.environ if env is None else env)
    metadata = {}
    external_config = None
    external_skin = None
    activate = False
    if 'hermes' in only:
        if not shutil.which('hermes', path=runtime_env.get('PATH', '')):
            raise InstallerError('Hermes selected but hermes CLI is missing from PATH; no files changed')
        config = paths.hermes_home / 'config.yaml'
        if config.is_symlink():
            raise InstallerError('Hermes config.yaml symlink is unsupported by the external writer; no files changed')
        external_config = _change(config, None)
        asset = (repo / 'hermes/github-light.yaml').read_bytes()
        _validate_skin(asset)
        external_skin = _change(paths.hermes_home / 'skins/github-light.yaml', asset)
        changes.append(external_skin)
        prior = None if dry_run else _get_skin(paths.hermes_home, runtime_env)
        _assert_unchanged(external_config)
        activate = dry_run or prior != 'github-light'
        if activate:
            external_config = Change(external_config.requested, external_config.path,
                                     external_config.before, external_config.mode, external_config.before)
            changes.append(external_config)
        metadata['hermes'] = {'home': str(paths.hermes_home), 'prior_skin': prior}
    _check_overlap(changes)
    for change in changes:
        if change.path == repo or repo in change.path.parents:
            raise InstallerError('Configuration targets must be outside this repository')
    changes = [change for change in changes if change.before != change.after
               or (activate and (change is external_config or change is external_skin))]
    home = _absolute(runtime_env.get('HOME', str(Path.home())), Path.home())
    backup = _absolute(backup_dir, home).resolve() if backup_dir is not None else paths.state_dir / (
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:12])
    backup = backup.resolve()
    _validate_backup_location(repo, backup, changes)
    if dry_run or not changes:
        return Result(None, tuple(change.requested for change in changes))
    if any(change.requested == paths.herdr_config for change in changes):
        metadata['herdr_config'] = str(paths.herdr_config)
    warnings = ()

    for change in changes:
        _assert_unchanged(change)
    manifest = _make_backup(repo, backup, changes, metadata)
    created = []
    touched = []
    try:
        for change in changes:
            _assert_unchanged(change)
            if change is external_config:
                continue  # Only Hermes' official config writer may activate the skin.
            touched.append(change)
            _atomic_write(change.path, change.after, change.mode, created)
        if activate:
            assert external_config is not None
            _assert_unchanged(external_config)
            _ensure_dirs(external_config.path.parent, created)
            touched.append(external_config)
            _hermes(['config', 'set', 'display.skin', 'github-light'], paths.hermes_home, runtime_env)
            if _get_skin(paths.hermes_home, runtime_env) != 'github-light':
                raise InstallerError('Hermes activation did not match readback')
            content, mode = _snapshot(external_config.path)
            if content is None:
                raise InstallerError('Hermes activation did not produce target config.yaml')
            wanted_mode = external_config.mode if external_config.mode is not None else 0o600
            if mode != wanted_mode:
                external_config.path.chmod(wanted_mode)
            record = manifest['files'][changes.index(external_config)]
            record['after_sha256'] = _digest(content)
            record['after_mode'] = wanted_mode
        if 'herdr_config' in metadata and not no_reload:
            warnings = _reload_herdr(paths.herdr_config, runtime_env)
        manifest['created_dirs'] = [str(p) for p in created]
        manifest['status'] = 'applied'
        _manifest_write(backup, manifest)
    except BaseException as exc:
        errors = []
        for change in reversed(touched):
            try:
                _atomic_write(change.path, change.before, change.mode)
            except Exception as recovery:
                errors.append(str(recovery))
        _clean_dirs(created)
        manifest['status'] = 'rollback-failed' if errors else 'rolled-back'
        try:
            _manifest_write(backup, manifest)
        except Exception:
            errors.append('Could not update recovery manifest')
        raise InstallerError(f'Apply failed; {"rollback incomplete" if errors else "original files restored"}. '
                             f'Recovery backup: {backup}') from exc
    return Result(backup, tuple(change.requested for change in changes), warnings)


def _load_backup(backup: Path) -> tuple[dict, list[Change]]:
    """Treat recovery metadata as untrusted; payloads stay inside this backup."""
    backup = backup.resolve()
    manifest_path = backup / 'manifest.json'
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise InstallerError('Missing or unsafe backup manifest')
    try:
        manifest = json.loads(manifest_path.read_bytes())
        if manifest['version'] != 1 or manifest['status'] not in ('applied', 'restored', 'rolled-back', 'rollback-failed', 'pending'):
            raise ValueError('Unknown backup version or status')
        records = manifest['files']
        if not isinstance(records, list) or not records:
            raise ValueError('Empty or invalid file list')
        changes = []
        for i, record in enumerate(records):
            path = _absolute(record['path'], Path.home())
            requested = _absolute(record['requested'], Path.home())
            if '..' in path.parts or '..' in requested.parts:
                raise ValueError('Parent traversal is unsupported')
            if path == backup or backup in path.parents or path in backup.parents:
                raise ValueError('Backup overlaps target')
            if requested.resolve() != path or path.resolve() != path:
                raise ValueError('Target symlink changed since apply')
            payload = record['original']
            if payload is None:
                original = None
                if record['before_mode'] is not None or record['before_sha256'] is not None:
                    raise ValueError('Invalid missing-file metadata')
            else:
                if payload != f'files/{i}':
                    raise ValueError('Backup-data path traversal or invalid payload path')
                source = backup / payload
                if source.is_symlink() or source.resolve() != source or not source.is_file():
                    raise ValueError('Unsafe backup payload')
                original = source.read_bytes()
                if _digest(original) != record['before_sha256']:
                    raise ValueError('Backup integrity check failed')
                mode = record['before_mode']
                if type(mode) is not int or not 0 <= mode <= 0o7777:
                    raise ValueError('Invalid original file mode')
            for name in ('before_sha256', 'after_sha256'):
                digest = record[name]
                if digest is not None and (not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)):
                    raise ValueError('Invalid checksum')
            if type(record['after_mode']) is not int or not 0 <= record['after_mode'] <= 0o7777:
                raise ValueError('Invalid applied mode')
            current, mode = _snapshot(path)
            changes.append(Change(requested, path, current, mode, original))
        _check_overlap(changes)
        if not isinstance(manifest['created_dirs'], list):
            raise ValueError('Invalid created directory list')
        for directory in manifest['created_dirs']:
            path = _absolute(directory, Path.home())
            if '..' in path.parts or path.resolve() != path or not any(path in c.path.parents for c in changes):
                raise ValueError('Unsafe created directory metadata')
        metadata = manifest.get('metadata', {})
        if not isinstance(metadata, dict):
            raise ValueError('Invalid metadata')
        if 'herdr_config' in metadata and not any(str(c.requested) == metadata['herdr_config'] for c in changes):
            raise ValueError('Herdr reload metadata is not a restored target')
        return manifest, changes
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise InstallerError(f'Invalid backup: {exc}') from exc


def restore(backup: Path, *, dry_run=False, force=False, no_reload=False, env=None) -> Result:
    backup = _absolute(backup, Path.home()).resolve()
    manifest, changes = _load_backup(backup)
    for change, record in zip(changes, manifest['files']):
        already_original = (change.before, change.mode) == (change.after, record['before_mode'])
        if already_original and manifest['status'] in ('restored', 'rolled-back'):
            continue
        expected = (record['after_sha256'], record['after_mode'] if record['after_sha256'] is not None else None)
        if not force and (_digest(change.before), change.mode) != expected:
            raise InstallerError(f'File changed since apply; use --force to overwrite: {change.requested}')
    work = [(change, record['before_mode']) for change, record in zip(changes, manifest['files'])
            if (change.before, change.mode) != (change.after, record['before_mode'])]
    if dry_run or not work:
        return Result(None, tuple(change.requested for change, _ in work))
    touched = []
    warnings = ()
    try:
        for change, mode in work:
            _assert_unchanged(change)
            touched.append(change)
            _atomic_write(change.path, change.after, mode)
        config = manifest['metadata'].get('herdr_config')
        if config and not no_reload:
            warnings = _reload_herdr(Path(config), dict(os.environ if env is None else env))
        manifest['status'] = 'restored'
        _manifest_write(backup, manifest)
    except BaseException as exc:
        errors = []
        for change in reversed(touched):
            try:
                _atomic_write(change.path, change.before, change.mode)
            except Exception as recovery:
                errors.append(str(recovery))
        raise InstallerError(f'Restore failed; {"rollback incomplete" if errors else "pre-restore files restored"}. '
                             f'Backup retained: {backup}') from exc
    _clean_dirs([Path(p) for p in manifest['created_dirs']])
    return Result(backup, tuple(change.requested for change, _ in work), warnings)


def replace_toml_theme(original: str, fragment: str) -> str:
    """Preserve non-theme source verbatim, then prove parsed equivalence.

    Fail closed for multiline TOML strings and root inline/dotted theme keys.
    A header-looking string must never be mistaken for a real table header.
    """
    try:
        before = tomllib.loads(original)
        desired = tomllib.loads(fragment)
        if set(desired) != {'theme'} or not isinstance(desired['theme'], dict):
            raise InstallerError('Herdr asset must contain only the theme subtree')
        if before.get('theme') == desired['theme']:
            return original  # Avoid accumulating the fragment's leading comments on reapply.
        if '\"\"\"' in original or "'''" in original:
            raise InstallerError('Herdr multiline strings are unsupported; integrate theme manually')
        keep = []
        in_theme = False
        for line in original.splitlines(keepends=True):
            header = re.match(r'^\s*(\[.*\])\s*(?:#.*)?$', line.rstrip('\r\n'))
            if header:
                probe = tomllib.loads(header[1] + '\n__probe__ = true\n')
                in_theme = set(probe) == {'theme'}
            if not in_theme:
                keep.append(line)
        base = ''.join(keep)
        updated = base + ('\n' if base and not base.endswith('\n') else '') + fragment.rstrip('\n') + '\n'
        after = tomllib.loads(updated)
        if {k: v for k, v in before.items() if k != 'theme'} != {k: v for k, v in after.items() if k != 'theme'}:
            raise InstallerError('Herdr non-theme values changed; refusing to write')
        if after.get('theme') != desired['theme']:
            raise InstallerError('Herdr theme did not match the asset; refusing to write')
        return updated
    except tomllib.TOMLDecodeError as exc:
        raise InstallerError('Invalid or unsupported Herdr TOML; no files changed') from exc


def managed_block(original: str, body: str, comment: str) -> str:
    begin = f'{comment} BEGIN terminal-theme github-light'
    end = f'{comment} END terminal-theme github-light'
    lines = original.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.strip() == begin]
    stops = [i for i, line in enumerate(lines) if line.strip() == end]
    block = begin + '\n' + body + '\n' + end + '\n'
    if not starts and not stops:
        return original + ('\n' if original and not original.endswith('\n') else '') + block
    if len(starts) != 1 or len(stops) != 1 or starts[0] >= stops[0]:
        raise InstallerError('Malformed or duplicate managed theme markers; repair manually')
    # The managed block must be last so a subsequent user setting cannot win.
    remaining = ''.join(lines[:starts[0]] + lines[stops[0] + 1:])
    return remaining + ('\n' if remaining and not remaining.endswith('\n') else '') + block


class InstallerError(Exception):
    """A safe, user-facing installation failure."""


@dataclass(frozen=True)
class Paths:
    ghostty_configs: tuple[Path, ...]
    ghostty_theme: Path
    neovim_dir: Path
    herdr_config: Path
    hermes_home: Path
    state_dir: Path
    p10k_config: Path


def _absolute(value: str | Path, home: Path) -> Path:
    text = str(value)
    if '\n' in text or '\r' in text or '\0' in text:
        raise InstallerError('Paths must not contain newlines or NUL characters')
    if text == '~' or text.startswith('~/'):
        text = str(home) + text[1:]
    path = Path(text)
    if not path.is_absolute():
        raise InstallerError(f'An absolute path is required: {path}')
    if '..' in path.parts:
        raise InstallerError(f'Parent traversal is unsupported: {value}')
    return path


def discover_paths(*, system: str | None = None, env=None, overrides=None) -> Paths:
    env = dict(os.environ if env is None else env)
    overrides = overrides or {}
    home = _absolute(env.get('HOME', str(Path.home())), Path.home())
    xdg = _absolute(env.get('XDG_CONFIG_HOME') or home / '.config', home)
    state = _absolute(env.get('XDG_STATE_HOME') or home / '.local/state', home)
    system = system or platform.system()
    if system not in ('Linux', 'Darwin'):
        raise InstallerError('Only Linux and macOS are supported')
    ghostty_dirs = [xdg / 'ghostty']
    if system == 'Darwin':
        ghostty_dirs.append(home / 'Library/Application Support/com.mitchellh.ghostty')
    if overrides.get('ghostty_config'):
        ghostty = (_absolute(overrides['ghostty_config'], home),)
    else:
        ghostty = tuple(directory / name for directory in ghostty_dirs
                        for name in ('config', 'config.ghostty')
                        if (directory / name).exists() or (directory / name).is_symlink())
        if not ghostty:
            ghostty = (ghostty_dirs[-1] / 'config.ghostty',)
    appname = env.get('NVIM_APPNAME') or 'nvim'
    nvim_dir = _absolute(overrides.get('neovim_config') or xdg / appname, home)
    return Paths(ghostty, xdg / 'ghostty/themes/github-light.conf', nvim_dir,
                 _absolute(overrides.get('herdr_config') or env.get('HERDR_CONFIG_PATH')
                           or xdg / 'herdr/config.toml', home),
                 _absolute(overrides.get('hermes_home') or env.get('HERMES_HOME')
                           or home / '.hermes', home),
                 state / 'terminal-theme/backups',
                 # Optional prompt paths stay lexical until Powerlevel10k is selected.
                 Path(overrides.get('p10k_config') or
                      Path(env.get('ZDOTDIR') or home) / '.p10k.zsh'))


def _report(result: Result, dry_run: bool, action: str) -> None:
    if not result.changed:
        print('No changes needed.')
    for path in result.changed:
        print(f'{"Would update" if dry_run else action}: {path}')
    if result.backup:
        print(f'Backup: {result.backup}')
    for warning in result.warnings:
        print(f'Warning: {warning}')


def apply_main(argv=None) -> int:
    import argparse
    import sys
    parser = argparse.ArgumentParser(
        description='Apply local theme-only assets (Python >= 3.11).',
        epilog='Neovim requires nvim for syntax validation and github-nvim-theme at runtime. '
               'The module can bootstrap the theme via vim.pack; the installer never downloads. '
               'Existing plugin setup and mappings are not changed. init.vim-only configs and '
               'Herdr multiline TOML strings require manual integration.')
    parser.add_argument('--dry-run', action='store_true', help='validate and show the plan without target writes')
    parser.add_argument('--only', nargs='+', choices=('ghostty', 'neovim', 'herdr', 'hermes', 'powerlevel10k'),
                        default=('ghostty', 'neovim', 'herdr', 'hermes'))
    parser.add_argument('--no-reload', action='store_true', help='skip Herdr server reload (Hermes activation still verified)')
    parser.add_argument('--ghostty-config', help='absolute Ghostty config file (override automatic discovery)')
    parser.add_argument('--neovim-config', help='absolute Neovim configuration DIRECTORY')
    parser.add_argument('--herdr-config', help='absolute Herdr TOML config file')
    parser.add_argument('--hermes-home', help='absolute Hermes home/profile directory')
    parser.add_argument('--p10k-config', help='absolute Powerlevel10k config file (default: ${ZDOTDIR:-$HOME}/.p10k.zsh)')
    parser.add_argument('--backup-dir', help='new private backup directory outside the repository')
    args = parser.parse_args(argv)
    try:
        paths = discover_paths(overrides=vars(args))
        repo = Path(__file__).resolve().parents[1]
        result = install(repo, paths, only=args.only, dry_run=args.dry_run,
                         backup_dir=args.backup_dir, no_reload=args.no_reload)
        _report(result, args.dry_run, 'Updated')
        if not args.dry_run and result.changed:
            if 'ghostty' in args.only:
                print('Ghostty: reload configuration manually or restart the app.')
            if 'neovim' in args.only:
                print('Neovim: restart/reload your editor; github-nvim-theme must be available or vim.pack enabled.')
            if 'powerlevel10k' in args.only:
                print('Powerlevel10k: source the installed config in your current zsh; .zshrc was not changed.')
        return 0
    except (InstallerError, OSError, UnicodeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1


def restore_main(argv=None) -> int:
    import argparse
    import sys
    parser = argparse.ArgumentParser(description='Restore exact original files from a private theme backup (Python >= 3.11).')
    parser.add_argument('backup_dir', help='backup directory printed by apply')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--force', action='store_true', help='overwrite subsequent user edits (integrity checks still enforced)')
    parser.add_argument('--no-reload', action='store_true', help='skip Herdr server reload')
    args = parser.parse_args(argv)
    try:
        home = _absolute(os.environ.get('HOME', str(Path.home())), Path.home())
        backup = _absolute(args.backup_dir, home)
        result = restore(backup, dry_run=args.dry_run, force=args.force, no_reload=args.no_reload)
        _report(result, args.dry_run, 'Restored')
        if not args.dry_run and result.changed:
            print('Reload Ghostty/restart Neovim as needed; no applications were stopped.')
        return 0
    except (InstallerError, OSError, UnicodeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
