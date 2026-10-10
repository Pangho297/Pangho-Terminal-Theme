"""Installer tests use explicitly synthetic configs/assets, never live app data."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))


class InstallerTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(os.environ.get('TMPDIR') or tempfile.gettempdir())
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-theme-test-', dir=scratch)
        self.root = Path(self.temp.name)
        self.home = self.root / 'home with spaces'
        self.home.mkdir()
        self.env = {'HOME': str(self.home), 'XDG_CONFIG_HOME': str(self.home / 'config space'),
                    'XDG_STATE_HOME': str(self.home / 'state'), 'PATH': ''}
        self.addCleanup(self.temp.cleanup)

    def installer(self):
        self.assertTrue((REPO / 'scripts/theme_installer.py').is_file(),
                        'portable installer module is not implemented')
        return importlib.import_module('theme_installer')

    def test_linux_path_discovery_respects_environment(self):
        mod = self.installer()
        self.env.update(NVIM_APPNAME='nvim-light', HERDR_CONFIG_PATH=str(self.home / 'private/herdr.toml'),
                        HERMES_HOME=str(self.home / 'hermes profile'))
        paths = mod.discover_paths(system='Linux', env=self.env)
        self.assertEqual(paths.ghostty_configs, (self.home / 'config space/ghostty/config.ghostty',))
        self.assertEqual(paths.ghostty_theme, self.home / 'config space/ghostty/themes/github-light.conf')
        self.assertEqual(paths.neovim_dir, self.home / 'config space/nvim-light')
        self.assertEqual(paths.herdr_config, self.home / 'private/herdr.toml')
        self.assertEqual(paths.hermes_home, self.home / 'hermes profile')
        self.assertEqual(paths.state_dir, self.home / 'state/terminal-theme/backups')

    def test_darwin_updates_all_existing_xdg_and_native_configs(self):
        mod = self.installer()
        native = self.home / 'Library/Application Support/com.mitchellh.ghostty'
        xdg = self.home / 'config space/ghostty'
        for folder in (native, xdg):
            folder.mkdir(parents=True)
            for name in ('config', 'config.ghostty'):
                (folder / name).write_text('# synthetic existing Ghostty config\n')
        paths = mod.discover_paths(system='Darwin', env=self.env)
        self.assertEqual(set(paths.ghostty_configs), {p / n for p in (native, xdg)
                                                    for n in ('config', 'config.ghostty')})
        explicit = self.home / 'explicit config'
        self.assertEqual(mod.discover_paths(system='Darwin', env=self.env,
                         overrides={'ghostty_config': str(explicit)}).ghostty_configs, (explicit,))

    def test_darwin_missing_configs_defaults_to_native(self):
        mod = self.installer()
        paths = mod.discover_paths(system='Darwin', env=self.env)
        self.assertEqual(paths.ghostty_configs,
                         (self.home / 'Library/Application Support/com.mitchellh.ghostty/config.ghostty',))

    def test_managed_block_preserves_other_settings_and_is_idempotent(self):
        mod = self.installer()
        self.assertTrue(callable(getattr(mod, 'managed_block', None)), 'managed block editor missing')
        original = 'font-family = Synthetic Font\ncommand = /synthetic/shell\ntheme = old\n'
        once = mod.managed_block(original, 'theme = /a path/github-light.conf', '#')
        self.assertTrue(once.startswith(original))
        self.assertEqual(mod.managed_block(once, 'theme = /a path/github-light.conf', '#'), once)
        replaced = mod.managed_block(once, 'theme = /other/theme', '#')
        self.assertNotIn('theme = /a path', replaced)
        self.assertEqual(replaced.count('# BEGIN terminal-theme github-light'), 1)
        with self.assertRaises(mod.InstallerError):
            mod.managed_block('# BEGIN terminal-theme github-light\n', 'theme = x', '#')

    def test_herdr_theme_subtree_only_preserves_non_theme_values_and_comments(self):
        import tomllib
        mod = self.installer()
        self.assertTrue(callable(getattr(mod, 'replace_toml_theme', None)), 'TOML theme editor missing')
        original = ('# synthetic Herdr fixture\nfont = "Unchanged" # keep\n'
                    '[theme]\nname = "old"\n[theme.custom]\nbackground = "#000000"\n'
                    '[shell]\ncommand = "/synthetic/shell"\nargs = ["-l"]\n'
                    '[notifications]\nenabled = true\n')
        fragment = '[theme]\nname = "terminal"\nauto_switch = false\n[theme.custom]\nbackground = "#ffffff"\n'
        updated = mod.replace_toml_theme(original, fragment)
        before, after = tomllib.loads(original), tomllib.loads(updated)
        before.pop('theme'); after.pop('theme')
        self.assertEqual(after, before)
        self.assertIn('font = "Unchanged" # keep', updated)
        self.assertIn('# synthetic Herdr fixture', updated)
        self.assertEqual(mod.replace_toml_theme(updated, fragment), updated)
        trap = 'script = """\n[theme]\nname = "not a table"\n"""\n[theme]\nname = "old"\n'
        with self.assertRaisesRegex(mod.InstallerError, 'multiline|unsupported'):
            mod.replace_toml_theme(trap, fragment)
        with self.assertRaises(mod.InstallerError):
            mod.replace_toml_theme('theme = { name = "old" }\n', fragment)
        with self.assertRaises(mod.InstallerError):
            mod.replace_toml_theme(original, fragment + '[shell]\ncommand = "bad"\n')

    def test_real_herdr_fragment_with_leading_comment_is_idempotent(self):
        mod = self.installer()
        fragment = (REPO / 'herdr/theme.toml').read_text()
        original = '# synthetic user settings\n[ui.toast]\ndelivery = "off"\n'
        once = mod.replace_toml_theme(original, fragment)
        self.assertEqual(mod.replace_toml_theme(once, fragment), once)

    def assets(self):
        repo = self.root / 'synthetic repo assets'
        repo.mkdir(exist_ok=True)
        # These deliberately tiny assets are synthetic installer fixtures, not app output.
        fixture_assets = {'ghostty/github-light.conf': 'background = #ffffff\nforeground = #1f2328\n',
                          'herdr/theme.toml': '[theme]\nname = "terminal"\nauto_switch = false\n[theme.custom]\nbackground = "#ffffff"\n',
                          'neovim/github_light.lua': 'local M = {}\nfunction M.setup() end\nreturn M\n',
                          'hermes/github-light.yaml': 'name: github-light\ncolors:\n  background: "#ffffff"\n'}
        for name, content in fixture_assets.items():
            target = repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        return repo

    def inventory(self):
        return {str(p.relative_to(self.home)): (p.read_bytes(), p.stat().st_mode & 0o777)
                for p in self.home.rglob('*') if p.is_file()}

    def test_ghostty_apply_dry_run_is_zero_writes_then_apply_is_idempotent(self):
        mod = self.installer()
        self.assertTrue(callable(getattr(mod, 'install', None)), 'transactional apply missing')
        repo = self.assets()
        paths = mod.discover_paths(system='Linux', env=self.env)
        target = paths.ghostty_configs[0]
        target.parent.mkdir(parents=True)
        original = b'# synthetic user config\ncommand = /synthetic/shell\nfont-size = 13\n'
        target.write_bytes(original)
        target.chmod(0o640)
        before = self.inventory()
        dry = mod.install(repo, paths, only=('ghostty',), env=self.env, dry_run=True, no_reload=True)
        self.assertIsNone(dry.backup)
        self.assertEqual(self.inventory(), before)
        self.assertFalse(paths.state_dir.exists())
        result = mod.install(repo, paths, only=('ghostty',), env=self.env, no_reload=True)
        self.assertTrue(result.backup.is_dir())
        self.assertTrue(target.read_bytes().startswith(original))
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)
        self.assertIn(f'theme = {paths.ghostty_theme}', target.read_text())
        self.assertEqual(paths.ghostty_theme.read_bytes(), (repo / 'ghostty/github-light.conf').read_bytes())
        after = self.inventory()
        second = mod.install(repo, paths, only=('ghostty',), env=self.env, no_reload=True)
        self.assertIsNone(second.backup)
        self.assertEqual(self.inventory(), after)
        self.assertEqual(result.backup.stat().st_mode & 0o777, 0o700)
        for private_file in result.backup.rglob('*'):
            if private_file.is_file():
                self.assertEqual(private_file.stat().st_mode & 0o777, 0o600)

    def test_ghostty_managed_colors_override_stale_settings_using_real_asset(self):
        mod = self.installer()
        paths = mod.discover_paths(system='Linux', env=self.env)
        config = paths.ghostty_configs[0]
        config.parent.mkdir(parents=True)
        original = (b'# synthetic user config\r\nfont-family = monospace\r\n'
                    b'command = /bin/sh\r\nfont-size = 13\r\n'
                    b'keybind = ctrl+shift+c=copy_to_clipboard\r\n'
                    b'background = #121212\r\nforeground = #aaaaaa\r\n'
                    b'cursor-color = #aaaaaa\r\ncursor-text = #121212\r\n'
                    b'selection-background = #121212\r\nselection-foreground = #aaaaaa\r\n'
                    + b''.join(f'palette = {i}=#121212\r\n'.encode() for i in range(16)))
        config.write_bytes(original)
        asset = (REPO / 'ghostty/github-light.conf').read_bytes()
        colors = [line for line in asset.decode().splitlines()
                  if line.strip() and not line.lstrip().startswith('#')]
        self.assertEqual(len(colors), 22)
        result = mod.install(REPO, paths, only=('ghostty',), env=self.env, no_reload=True)
        applied = config.read_bytes()
        self.assertTrue(applied.startswith(original))
        self.assertEqual(paths.ghostty_theme.read_bytes(), asset)
        block = applied[len(original):].decode()
        self.assertIn(f'theme = {paths.ghostty_theme}\n', block)
        for line in colors:
            self.assertIn(line + '\n', block)
        before = self.inventory()
        self.assertIsNone(mod.install(REPO, paths, only=('ghostty',), env=self.env,
                                     no_reload=True).backup)
        self.assertEqual(self.inventory(), before)
        mod.restore(result.backup, env=self.env, no_reload=True)
        self.assertEqual(config.read_bytes(), original)

    def test_real_ghostty_colors_override_stale_settings(self):
        import shutil
        import subprocess
        executable = shutil.which('ghostty')
        if not executable:
            self.skipTest('real Ghostty is not installed')
        mod = self.installer()
        paths = mod.discover_paths(system='Linux', env=self.env)
        config = paths.ghostty_configs[0]
        config.parent.mkdir(parents=True)
        original = ('background = #121212\nforeground = #aaaaaa\nfont-size = 13\n'
                    'cursor-color = #aaaaaa\ncursor-text = #121212\n'
                    'selection-background = #121212\nselection-foreground = #aaaaaa\n'
                    + ''.join(f'palette = {i}=#121212\n' for i in range(16)))
        config.write_text(original)
        isolated = dict(self.env, XDG_DATA_HOME=str(self.home / 'data'),
                        XDG_CACHE_HOME=str(self.home / 'cache'))
        # show-config uses default config discovery, isolated by HOME and XDG paths.
        command = [executable, '+show-config']
        before = subprocess.run(command, env=isolated, capture_output=True, text=True, timeout=30)
        self.assertEqual(before.returncode, 0, before.stderr)
        self.assertIn('background = #121212', before.stdout)
        mod.install(REPO, paths, only=('ghostty',), env=self.env, no_reload=True)
        result = subprocess.run(command, env=isolated, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        effective = [line.strip() for line in result.stdout.splitlines()]
        asset = (REPO / 'ghostty/github-light.conf').read_text()
        for line in asset.splitlines():
            if line.strip() and not line.lstrip().startswith('#'):
                self.assertIn(line, effective)
        self.assertIn('font-size = 13', effective)
        self.assertTrue(config.read_text().startswith(original))

    def test_restore_exact_original_bytes_modes_and_missing_files(self):
        mod = self.installer()
        self.assertTrue(callable(getattr(mod, 'restore', None)), 'complete restore missing')
        repo = self.assets()
        paths = mod.discover_paths(system='Linux', env=self.env)
        real = self.home / 'dotfiles/ghostty config'
        real.parent.mkdir()
        original = b'command = /synthetic/shell\r\nfont-size = 15\r\n'
        real.write_bytes(original)
        real.chmod(0o640)
        config = paths.ghostty_configs[0]
        config.parent.mkdir(parents=True)
        config.symlink_to(real)
        result = mod.install(repo, paths, only=('ghostty',), env=self.env, no_reload=True)
        self.assertTrue(config.is_symlink())
        applied = self.inventory()
        mod.restore(result.backup, dry_run=True, no_reload=True, env=self.env)
        self.assertEqual(self.inventory(), applied)
        mod.restore(result.backup, no_reload=True, env=self.env)
        self.assertTrue(config.is_symlink())
        self.assertEqual(real.read_bytes(), original)
        self.assertEqual(real.stat().st_mode & 0o777, 0o640)
        self.assertFalse(paths.ghostty_theme.exists())
        # A second restore is a safe no-op, not a new destructive transaction.
        mod.restore(result.backup, no_reload=True, env=self.env)

    def test_herdr_apply_is_theme_only_with_exact_restore_and_no_reload(self):
        import tomllib
        mod = self.installer()
        repo = self.assets()
        paths = mod.discover_paths(system='Linux', env=self.env)
        paths.herdr_config.parent.mkdir(parents=True)
        original = b'# synthetic Herdr config\n[shell]\ncommand = "/synthetic/zsh"\n[theme]\nname = "old"\n[notifications]\nenabled = true\n'
        paths.herdr_config.write_bytes(original)
        result = mod.install(repo, paths, only=('herdr',), env=self.env, no_reload=True)
        parsed = tomllib.loads(paths.herdr_config.read_text())
        self.assertEqual(parsed['shell']['command'], '/synthetic/zsh')
        self.assertTrue(parsed['notifications']['enabled'])
        self.assertEqual(parsed['theme']['name'], 'terminal')
        mod.restore(result.backup, env=self.env, no_reload=True)
        self.assertEqual(paths.herdr_config.read_bytes(), original)

    def test_neovim_installs_module_and_appends_only_one_safe_init_block(self):
        from unittest.mock import patch
        import subprocess
        mod = self.installer()
        self.assertTrue(callable(getattr(mod, '_validate_lua', None)), 'safe Neovim preflight missing')
        repo = self.assets()
        paths = mod.discover_paths(system='Linux', env=self.env)
        paths.neovim_dir.mkdir(parents=True)
        original = b'-- synthetic user init\nvim.keymap.set("n", "<leader>x", "<cmd>echo 1<cr>")\n'
        init = paths.neovim_dir / 'init.lua'
        init.write_bytes(original)
        validated = []
        def synthetic_nvim(argv, **kwargs):
            self.assertIn('--headless', argv)
            self.assertIn('loadfile', ' '.join(argv))
            validated.append(Path(kwargs['env']['TERMINAL_THEME_LUA']).read_bytes())
            self.assertNotEqual(kwargs['env']['HOME'], str(self.home))
            return subprocess.CompletedProcess(argv, 0, '', '')
        with patch.object(mod.shutil, 'which', return_value='/synthetic/nvim'), \
             patch.object(mod.subprocess, 'run', side_effect=synthetic_nvim):
            result = mod.install(repo, paths, only=('neovim',), env=self.env, no_reload=True)
            second = mod.install(repo, paths, only=('neovim',), env=self.env, no_reload=True)
        self.assertTrue(init.read_bytes().startswith(original))
        self.assertEqual(init.read_text().count("require('github_light').setup()"), 1)
        self.assertIsNone(second.backup)
        self.assertEqual((paths.neovim_dir / 'lua/github_light.lua').read_bytes(),
                         (repo / 'neovim/github_light.lua').read_bytes())
        self.assertTrue(any(b"require('github_light').setup()" in text for text in validated))
        mod.restore(result.backup, no_reload=True, env=self.env)
        self.assertEqual(init.read_bytes(), original)
        self.assertFalse((paths.neovim_dir / 'lua/github_light.lua').exists())

    def test_hermes_uses_official_setter_bound_home_and_verifies_readback(self):
        from unittest.mock import patch
        import subprocess
        mod = self.installer()
        self.assertTrue(callable(getattr(mod, '_hermes', None)), 'safe Hermes CLI integration missing')
        repo = self.assets()
        self.env['HERMES_HOME'] = str(self.home / 'hermes profile')
        paths = mod.discover_paths(system='Linux', env=self.env)
        paths.hermes_home.mkdir()
        config = paths.hermes_home / 'config.yaml'
        original = b'# synthetic private config\nmodel: synthetic-model\nprovider: synthetic-provider\ndisplay:\n  skin: synthetic-old\n'
        config.write_bytes(original)
        config.chmod(0o640)
        skin = paths.hermes_home / 'skins/github-light.yaml'
        skin.parent.mkdir()
        skin.write_bytes(b'name: synthetic-old-private-skin\n')
        skin.chmod(0o600)
        calls = []
        def synthetic_hermes(argv, **kwargs):
            self.assertEqual(kwargs['env']['HERMES_HOME'], str(paths.hermes_home))
            calls.append(argv)
            if argv == ['hermes', 'config', 'get', 'display.skin']:
                value = 'github-light' if b'skin: github-light' in config.read_bytes() else 'synthetic-old'
                return subprocess.CompletedProcess(argv, 0, value + '\n', '')
            self.assertEqual(argv, ['hermes', 'config', 'set', 'display.skin', 'github-light'])
            config.write_bytes(config.read_bytes().replace(b'skin: synthetic-old', b'skin: github-light'))
            return subprocess.CompletedProcess(argv, 0, 'synthetic setter result', '')
        with patch.object(mod.shutil, 'which', return_value='/synthetic/hermes'), \
             patch.object(mod.subprocess, 'run', side_effect=synthetic_hermes):
            before = self.inventory()
            mod.install(repo, paths, only=('hermes',), env=self.env, dry_run=True, no_reload=True)
            self.assertEqual(calls, [])
            self.assertEqual(self.inventory(), before)
            result = mod.install(repo, paths, only=('hermes',), env=self.env, no_reload=True)
            second = mod.install(repo, paths, only=('hermes',), env=self.env, no_reload=True)
        self.assertEqual(calls[:3], [['hermes', 'config', 'get', 'display.skin'],
                                   ['hermes', 'config', 'set', 'display.skin', 'github-light'],
                                   ['hermes', 'config', 'get', 'display.skin']])
        self.assertIsNone(second.backup)
        self.assertIn(b'provider: synthetic-provider', config.read_bytes())
        self.assertEqual(config.stat().st_mode & 0o777, 0o640)
        mod.restore(result.backup, env=self.env, no_reload=True)
        self.assertEqual(config.read_bytes(), original)
        self.assertEqual(skin.read_bytes(), b'name: synthetic-old-private-skin\n')

    def test_herdr_reload_is_verified_and_missing_server_is_a_warning(self):
        from unittest.mock import patch
        import subprocess
        mod = self.installer()
        repo = self.assets()
        paths = mod.discover_paths(system='Linux', env=self.env)
        calls = []
        def synthetic_applied(argv, **kwargs):
            self.assertEqual(argv, ['herdr', 'server', 'reload-config'])
            self.assertEqual(kwargs['env']['HERDR_CONFIG_PATH'], str(paths.herdr_config))
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, '{"result":{"status":"applied","diagnostics":[]}}', '')
        with patch.object(mod.shutil, 'which', return_value='/synthetic/herdr'), \
             patch.object(mod.subprocess, 'run', side_effect=synthetic_applied):
            result = mod.install(repo, paths, only=('herdr',), env=self.env)
            mod.install(repo, paths, only=('herdr',), env=self.env)
            self.assertEqual(len(calls), 1, 'only a real change should reload the server')
            mod.restore(result.backup, env=self.env)
            self.assertEqual(len(calls), 2)
        self.assertEqual(result.warnings, ())
        with patch.object(mod.shutil, 'which', return_value='/synthetic/herdr'), \
             patch.object(mod.subprocess, 'run', return_value=subprocess.CompletedProcess(
                 ['herdr'], 1, '', 'synthetic server not running')):
            warning = mod.install(repo, paths, only=('herdr',), env=self.env)
        self.assertTrue(any('not running' in w for w in warning.warnings))
        self.assertTrue(paths.herdr_config.exists())

    def test_executable_cli_dry_run_apply_restore_work_from_an_unrelated_cwd(self):
        import subprocess
        import shutil
        self.assertTrue((REPO / 'scripts/apply').is_file(), 'executable apply entrypoint missing')
        self.assertTrue((REPO / 'scripts/restore').is_file(), 'executable restore entrypoint missing')
        repo = self.assets()
        shutil.copytree(REPO / 'scripts', repo / 'scripts', ignore=shutil.ignore_patterns('__pycache__'))
        cli_env = dict(os.environ, **self.env, PYTHONDONTWRITEBYTECODE='1')
        # Use the interpreter explicitly so synthetic PATH does not resolve real app CLIs.
        apply = [sys.executable, str(repo / 'scripts/apply'), '--only', 'ghostty', '--no-reload']
        before = self.inventory()
        dry = subprocess.run([*apply, '--dry-run'], cwd=self.root, env=cli_env, text=True, capture_output=True)
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn('Would update:', dry.stdout)
        self.assertEqual(self.inventory(), before)
        backup = self.root / 'private backup'
        real = subprocess.run([*apply, '--backup-dir', str(backup)], cwd=self.root, env=cli_env,
                              text=True, capture_output=True)
        self.assertEqual(real.returncode, 0, real.stderr)
        self.assertTrue((backup / 'manifest.json').is_file())
        recovered = subprocess.run([sys.executable, str(repo / 'scripts/restore'), str(backup), '--no-reload'],
                                   cwd=self.root, env=cli_env, text=True, capture_output=True)
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertEqual(self.inventory(), before)
        for name in ('apply', 'restore'):
            self.assertTrue(os.access(REPO / 'scripts' / name, os.X_OK))

    def test_restore_refuses_user_edits_and_force_restores_original(self):
        mod = self.installer()
        repo = self.assets()
        paths = mod.discover_paths(system='Linux', env=self.env)
        result = mod.install(repo, paths, only=('ghostty',), env=self.env, no_reload=True)
        target = paths.ghostty_configs[0]
        target.write_text('# synthetic subsequent user edit\n')
        before = self.inventory()
        with self.assertRaisesRegex(mod.InstallerError, 'changed since apply'):
            mod.restore(result.backup, no_reload=True, env=self.env)
        self.assertEqual(self.inventory(), before)
        mod.restore(result.backup, force=True, no_reload=True, env=self.env)
        self.assertFalse(target.exists())
        self.assertFalse(paths.ghostty_theme.exists())

    def test_restore_rejects_tampered_payload_and_backup_path_traversal(self):
        import json
        mod = self.installer()
        repo = self.assets()
        paths = mod.discover_paths(system='Linux', env=self.env)
        config = paths.ghostty_configs[0]
        config.parent.mkdir(parents=True)
        config.write_text('# synthetic original\n')
        result = mod.install(repo, paths, only=('ghostty',), env=self.env, no_reload=True)
        manifest_path = result.backup / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        record = next(r for r in manifest['files'] if r['original'] is not None)
        payload = result.backup / record['original']
        original_payload = payload.read_bytes()
        payload.write_bytes(b'synthetic corruption')
        target_bytes = config.read_bytes()
        with self.assertRaisesRegex(mod.InstallerError, 'integrity'):
            mod.restore(result.backup, force=True, no_reload=True, env=self.env)
        self.assertEqual(config.read_bytes(), target_bytes)
        payload.write_bytes(original_payload)
        record['original'] = '../outside-secret'
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(mod.InstallerError, 'traversal'):
            mod.restore(result.backup, force=True, no_reload=True, env=self.env)
        self.assertEqual(config.read_bytes(), target_bytes)

    def test_dangling_symlinks_and_overlapping_targets_fail_before_writes(self):
        from dataclasses import replace
        mod = self.installer()
        repo = self.assets()
        paths = mod.discover_paths(system='Linux', env=self.env)
        config = paths.ghostty_configs[0]
        config.parent.mkdir(parents=True)
        config.symlink_to(self.home / 'nonexistent')
        with self.assertRaisesRegex(mod.InstallerError, 'Dangling'):
            mod.install(repo, paths, only=('ghostty',), env=self.env, no_reload=True)
        self.assertTrue(config.is_symlink())
        self.assertFalse(paths.state_dir.exists())
        config.unlink()
        config.symlink_to(paths.ghostty_theme)
        paths.ghostty_theme.parent.mkdir()
        paths.ghostty_theme.write_text('# synthetic existing theme\n')
        with self.assertRaisesRegex(mod.InstallerError, 'Overlapping'):
            mod.install(repo, paths, only=('ghostty',), env=self.env, no_reload=True)
        self.assertEqual(paths.ghostty_theme.read_text(), '# synthetic existing theme\n')
        self.assertFalse(paths.state_dir.exists())

    def test_hermes_missing_cli_is_preflight_failure_without_any_writes(self):
        mod = self.installer()
        repo = self.assets()
        paths = mod.discover_paths(system='Linux', env=self.env)
        with self.assertRaisesRegex(mod.InstallerError, 'CLI is missing'):
            mod.install(repo, paths, only=('ghostty', 'hermes'), env=self.env, no_reload=True)
        self.assertEqual(self.inventory(), {})

    def test_path_newlines_are_rejected(self):
        mod = self.installer()
        with self.assertRaisesRegex(mod.InstallerError, 'newlines'):
            mod.discover_paths(system='Linux', env=self.env,
                               overrides={'ghostty_config': str(self.home / 'bad\ncommand = evil')})

    def test_absolute_rejects_parent_traversal_without_normalizing(self):
        mod = self.installer()
        for value in (self.home / 'exists/../herdr.toml', '~/exists/../herdr.toml'):
            with self.subTest(value=value):
                with self.assertRaisesRegex(mod.InstallerError, '(?i)traversal') as raised:
                    mod._absolute(value, self.home)
                self.assertIn(str(value), str(raised.exception))
        ordinary = self.home / 'name..with..dots/herdr.toml'
        self.assertEqual(mod._absolute(ordinary, self.home), ordinary)

    def test_direct_paths_parent_traversal_is_rejected_before_writes(self):
        from dataclasses import replace
        mod = self.installer()
        repo = self.assets()
        paths = mod.discover_paths(system='Linux', env=self.env)
        (self.home / 'exists').mkdir()
        config = self.home / 'herdr.toml'
        original = b'# synthetic original\n[shell]\ncommand = "/bin/sh"\n'
        config.write_bytes(original)
        unsafe = self.home / 'exists/../herdr.toml'
        paths = replace(paths, herdr_config=unsafe)
        before = self.inventory()
        backup = self.root / 'rejected backup'
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run):
                with self.assertRaisesRegex(mod.InstallerError, '(?i)traversal'):
                    mod.install(repo, paths, only=('herdr',), env=self.env, no_reload=True,
                                dry_run=dry_run, backup_dir=backup)
                self.assertEqual(config.read_bytes(), original)
                self.assertEqual(self.inventory(), before)
                self.assertFalse(backup.exists())
                self.assertFalse(paths.state_dir.exists())

    def test_discovery_rejects_parent_traversal_overrides(self):
        mod = self.installer()
        (self.home / 'exists').mkdir()
        config = self.home / 'herdr.toml'
        original = b'# synthetic original\n[shell]\ncommand = "/bin/sh"\n'
        config.write_bytes(original)
        unsafe = str(self.home / 'exists/../herdr.toml')
        before = self.inventory()
        for key in ('ghostty_config', 'neovim_config', 'herdr_config', 'hermes_home'):
            with self.subTest(override=key):
                with self.assertRaisesRegex(mod.InstallerError, '(?i)traversal'):
                    mod.discover_paths(system='Linux', env=self.env, overrides={key: unsafe})
                self.assertEqual(self.inventory(), before)
        with self.assertRaisesRegex(mod.InstallerError, '(?i)traversal'):
            mod.discover_paths(system='Linux', env=dict(self.env, HERDR_CONFIG_PATH=unsafe))
        self.assertEqual(config.read_bytes(), original)

    def test_restore_rejects_parent_traversal_target_metadata(self):
        import json
        mod = self.installer()
        repo = self.assets()
        paths = mod.discover_paths(system='Linux', env=self.env)
        config = paths.herdr_config
        config.parent.mkdir(parents=True)
        config.write_text('# synthetic original\n[shell]\ncommand = "/bin/sh"\n')
        (config.parent / 'exists').mkdir()
        result = mod.install(repo, paths, only=('herdr',), env=self.env, no_reload=True)
        manifest_path = result.backup / 'manifest.json'
        original_manifest = json.loads(manifest_path.read_text())
        for field in ('path', 'requested'):
            with self.subTest(field=field):
                manifest = json.loads(json.dumps(original_manifest))
                manifest['files'][0][field] = str(config.parent / 'exists/..' / config.name)
                manifest_path.write_text(json.dumps(manifest))
                before = self.inventory()
                with self.assertRaisesRegex(mod.InstallerError, '(?i)traversal'):
                    mod.restore(result.backup, force=True, no_reload=True, env=self.env)
                self.assertEqual(self.inventory(), before)

    def test_dry_run_rejects_backup_and_config_targets_inside_repo(self):
        mod = self.installer()
        repo = self.assets()
        paths = mod.discover_paths(system='Linux', env=self.env,
                                   overrides={'ghostty_config': str(repo / 'private-config')})
        with self.assertRaisesRegex(mod.InstallerError, 'repository'):
            mod.install(repo, paths, only=('ghostty',), env=self.env, dry_run=True, no_reload=True)
        paths = mod.discover_paths(system='Linux', env=self.env)
        with self.assertRaisesRegex(mod.InstallerError, 'repository'):
            mod.install(repo, paths, only=('ghostty',), env=self.env, dry_run=True,
                        backup_dir=repo / 'private-backup', no_reload=True)
        self.assertEqual(self.inventory(), {})

    def test_hermes_failed_activation_or_wrong_readback_rolls_back_all_apps(self):
        from unittest.mock import patch
        import subprocess
        mod = self.installer()
        repo = self.assets()
        paths = mod.discover_paths(system='Linux', env=self.env)
        paths.hermes_home.mkdir()
        config = paths.hermes_home / 'config.yaml'
        original = b'model: synthetic-private-model\ndisplay:\n  skin: synthetic-old\n'
        config.write_bytes(original)
        config.chmod(0o640)
        for failure in ('setter', 'readback'):
            with self.subTest(failure=failure):
                calls = []
                def synthetic_failure(argv, **kwargs):
                    calls.append(argv)
                    if 'set' in argv:
                        config.write_bytes(b'synthetic partial config mutation\n')
                        return subprocess.CompletedProcess(argv, 1 if failure == 'setter' else 0,
                                                           '', 'synthetic-private-secret-not-for-logs')
                    return subprocess.CompletedProcess(argv, 0, 'synthetic-old\n', '')
                with patch.object(mod.shutil, 'which', return_value='/synthetic/hermes'), \
                     patch.object(mod.subprocess, 'run', side_effect=synthetic_failure):
                    with self.assertRaisesRegex(mod.InstallerError, 'original files restored') as raised:
                        mod.install(repo, paths, only=('ghostty', 'hermes'), env=self.env, no_reload=True,
                                    backup_dir=self.root / f'failure-backup-{failure}')
                self.assertNotIn('synthetic-private-secret', str(raised.exception))
                self.assertEqual(config.read_bytes(), original)
                self.assertEqual(config.stat().st_mode & 0o777, 0o640)
                self.assertFalse(paths.ghostty_configs[0].exists())
                self.assertFalse(paths.ghostty_theme.exists())
                self.assertFalse((paths.hermes_home / 'skins/github-light.yaml').exists())

    def test_neovim_missing_cli_and_init_vim_only_fail_without_writes(self):
        mod = self.installer()
        repo = self.assets()
        paths = mod.discover_paths(system='Linux', env=self.env)
        with self.assertRaisesRegex(mod.InstallerError, 'nvim on PATH'):
            mod.install(repo, paths, only=('ghostty', 'neovim'), env=self.env, no_reload=True)
        self.assertEqual(self.inventory(), {})
        paths.neovim_dir.mkdir(parents=True)
        (paths.neovim_dir / 'init.vim').write_text('" synthetic legacy config\n')
        before = self.inventory()
        with self.assertRaisesRegex(mod.InstallerError, 'init.vim-only'):
            mod.install(repo, paths, only=('ghostty', 'neovim'), env=self.env, no_reload=True)
        self.assertEqual(self.inventory(), before)

    def test_real_headless_neovim_rejects_invalid_lua_and_top_level_return(self):
        import shutil
        executable = shutil.which('nvim')
        if not executable:
            self.skipTest('real nvim is not installed; unit CLI fakes cover preflight flow')
        mod = self.installer()
        repo = self.assets()
        paths = mod.discover_paths(system='Linux', env=self.env)
        paths.neovim_dir.mkdir(parents=True)
        self.env['PATH'] = str(Path(executable).parent)
        init = paths.neovim_dir / 'init.lua'
        for source in ('return {}\n', 'this is invalid lua !!!\n'):
            with self.subTest(source=source):
                init.write_text(source)
                before = self.inventory()
                with self.assertRaisesRegex(mod.InstallerError, 'Invalid Lua'):
                    mod.install(repo, paths, only=('ghostty', 'neovim'), env=self.env, no_reload=True)
                self.assertEqual(self.inventory(), before)
        init.write_text('-- synthetic valid Lua fixture\nvim.g.synthetic_option = 1\n')
        result = mod.install(repo, paths, only=('neovim',), env=self.env, no_reload=True)
        self.assertTrue(result.backup.is_dir())
        mod.restore(result.backup, env=self.env, no_reload=True)
        self.assertEqual(init.read_text(), '-- synthetic valid Lua fixture\nvim.g.synthetic_option = 1\n')

    def test_herdr_bad_reload_status_rolls_back_files(self):
        from unittest.mock import patch
        import subprocess
        mod = self.installer()
        repo = self.assets()
        paths = mod.discover_paths(system='Linux', env=self.env)
        with patch.object(mod.shutil, 'which', return_value='/synthetic/herdr'), \
             patch.object(mod.subprocess, 'run', return_value=subprocess.CompletedProcess(
                 ['herdr'], 0, '{"result":{"status":"rejected","diagnostics":["synthetic error"]}}', '')):
            with self.assertRaisesRegex(mod.InstallerError, 'original files restored'):
                mod.install(repo, paths, only=('ghostty', 'herdr'), env=self.env)
        self.assertFalse(paths.ghostty_theme.exists())
        self.assertFalse(paths.ghostty_configs[0].exists())
        self.assertFalse(paths.herdr_config.exists())

    def test_config_and_theme_hardlink_overlap_is_rejected(self):
        mod = self.installer()
        repo = self.assets()
        paths = mod.discover_paths(system='Linux', env=self.env)
        config = paths.ghostty_configs[0]
        paths.ghostty_theme.parent.mkdir(parents=True)
        config.write_text('# synthetic hardlinked config\n')
        paths.ghostty_theme.hardlink_to(config)
        with self.assertRaisesRegex(mod.InstallerError, '(?i)overlapping|hardlink'):
            mod.install(repo, paths, only=('ghostty',), env=self.env, no_reload=True)
        self.assertFalse(paths.state_dir.exists())

    def test_ghostty_rejects_non_color_or_invalid_asset_before_writes(self):
        mod = self.installer()
        repo = self.assets()
        paths = mod.discover_paths(system='Linux', env=self.env)
        asset = repo / 'ghostty/github-light.conf'
        for text in ('background = #ffffff\nforeground = #1f2328\ncommand = /synthetic/evil\n',
                     'background = not-a-color\nforeground = #1f2328\n'):
            with self.subTest(asset=text):
                asset.write_text(text)
                with self.assertRaisesRegex(mod.InstallerError, 'Ghostty'):
                    mod.install(repo, paths, only=('ghostty',), env=self.env, no_reload=True)
                self.assertEqual(self.inventory(), {})

    def test_lua_validation_uses_system_scratch_when_tmpdir_is_unset(self):
        from unittest.mock import patch
        import subprocess
        mod = self.installer()
        with patch.dict(os.environ, {'HOME': str(self.home)}, clear=True), \
             patch.object(mod.tempfile, 'gettempdir', return_value=str(self.root)), \
             patch.object(mod.shutil, 'which', return_value='/synthetic/nvim'), \
             patch.object(mod.subprocess, 'run', return_value=subprocess.CompletedProcess(['nvim'], 0, '', '')):
            mod._validate_lua(b'-- synthetic valid Lua\n', self.env, 'synthetic.lua')
        self.assertFalse((self.home / '.hermes').exists())

    def test_invalid_single_quoted_hermes_asset_is_rejected_before_cli(self):
        from unittest.mock import patch
        mod = self.installer()
        repo = self.assets()
        paths = mod.discover_paths(system='Linux', env=self.env)
        asset = repo / 'hermes/github-light.yaml'
        asset.write_text('name: github-light\ndescription: \'unterminated\ncolors:\n  background: "#ffffff"\n')
        with patch.object(mod.shutil, 'which', return_value='/synthetic/hermes'), \
             patch.object(mod.subprocess, 'run') as runner:
            with self.assertRaisesRegex(mod.InstallerError, 'Hermes skin'):
                mod.install(repo, paths, only=('hermes',), env=self.env, dry_run=True, no_reload=True)
            runner.assert_not_called()
        self.assertEqual(self.inventory(), {})

    def test_hermes_activation_backs_up_unchanged_skin_touched_by_cli(self):
        from unittest.mock import patch
        import subprocess
        import json
        mod = self.installer()
        repo = self.assets()
        paths = mod.discover_paths(system='Linux', env=self.env)
        skin = paths.hermes_home / 'skins/github-light.yaml'
        skin.parent.mkdir(parents=True)
        skin.write_bytes((repo / 'hermes/github-light.yaml').read_bytes())
        config = paths.hermes_home / 'config.yaml'
        config.write_text('display:\n  skin: synthetic-old\n')
        def synthetic_cli(argv, **kwargs):
            if 'set' in argv:
                config.write_text('display:\n  skin: github-light\n')
                skin.touch()  # Mirrors the official writer's skin-watcher notification.
                return subprocess.CompletedProcess(argv, 0, '', '')
            value = 'github-light' if 'github-light' in config.read_text() else 'synthetic-old'
            return subprocess.CompletedProcess(argv, 0, value + '\n', '')
        with patch.object(mod.shutil, 'which', return_value='/synthetic/hermes'), \
             patch.object(mod.subprocess, 'run', side_effect=synthetic_cli):
            result = mod.install(repo, paths, only=('hermes',), env=self.env, no_reload=True)
        manifest = json.loads((result.backup / 'manifest.json').read_text())
        self.assertIn(str(skin), [record['requested'] for record in manifest['files']])


if __name__ == '__main__':
    unittest.main()
