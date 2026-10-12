"""Powerlevel10k installation uses synthetic HOME, never the live shell config."""
import importlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))


class Powerlevel10kInstallerTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which('zsh'):
            self.skipTest('zsh is required for real syntax validation')
        self.temp = tempfile.TemporaryDirectory(
            prefix='terminal-theme-p10k-', dir=os.environ.get('TMPDIR'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / 'home with spaces'
        self.home.mkdir()
        self.repo = self.root / 'synthetic assets'
        (self.repo / 'zsh').mkdir(parents=True)
        self.asset = self.repo / 'zsh/p10k.zsh'
        self.asset.write_text('# synthetic prompt\ntypeset -g POWERLEVEL9K_DIR_FOREGROUND=4\n')
        self.env = dict(os.environ, HOME=str(self.home),
                        XDG_CONFIG_HOME=str(self.home / 'config'),
                        XDG_STATE_HOME=str(self.home / 'state'))
        self.env.pop('ZDOTDIR', None)
        self.mod = importlib.import_module('theme_installer')

    def inventory(self):
        return {str(p.relative_to(self.home)): (p.read_bytes(), p.stat().st_mode & 0o777)
                for p in self.home.rglob('*') if p.is_file()}

    def test_explicit_prompt_install_is_backed_up_idempotent_and_reversible(self):
        paths = self.mod.discover_paths(system='Linux', env=self.env)
        target = self.home / '.p10k.zsh'
        original = b'# synthetic existing prompt\r\n'
        target.write_bytes(original)
        target.chmod(0o640)
        startup = self.home / '.zshrc'
        startup.write_bytes(b'# synthetic private startup; must remain untouched\n')
        before = self.inventory()
        dry = self.mod.install(self.repo, paths, only=('powerlevel10k',),
                               env=self.env, dry_run=True, no_reload=True)
        self.assertEqual(dry.changed, (target,))
        self.assertIsNone(dry.backup)
        self.assertEqual(self.inventory(), before)
        result = self.mod.install(self.repo, paths, only=('powerlevel10k',),
                                  env=self.env, no_reload=True)
        self.assertEqual(result.changed, (target,))
        self.assertEqual(target.read_bytes(), self.asset.read_bytes())
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)
        self.assertEqual(startup.read_bytes(), before['.zshrc'][0])
        after = self.inventory()
        second = self.mod.install(self.repo, paths, only=('powerlevel10k',),
                                  env=self.env, no_reload=True)
        self.assertEqual(second.changed, ())
        self.assertEqual(self.inventory(), after)
        self.mod.restore(result.backup, env=self.env, no_reload=True)
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)
        self.assertEqual(startup.read_bytes(), before['.zshrc'][0])

    def test_prompt_path_respects_zdotdir_and_explicit_override(self):
        shell_dir = self.home / 'shell config'
        paths = self.mod.discover_paths(system='Linux', env=dict(self.env, ZDOTDIR=str(shell_dir)))
        self.assertEqual(paths.p10k_config, shell_dir / '.p10k.zsh')
        target = self.home / 'explicit prompt.zsh'
        paths = self.mod.discover_paths(system='Darwin', env=self.env,
                                       overrides={'p10k_config': str(target)})
        self.assertEqual(paths.p10k_config, target)
        self.mod.install(self.repo, paths, only=('powerlevel10k',), env=self.env, no_reload=True)
        self.assertEqual(target.read_bytes(), self.asset.read_bytes())
        self.assertFalse((self.home / '.p10k.zsh').exists())
        for invalid in (str(self.home / 'folder/../prompt.zsh'), '~/folder/../prompt.zsh',
                        str(self.home / 'bad\nfile'), str(self.home / 'bad\rfile'),
                        str(self.home / 'bad\0file'), 'relative/prompt.zsh'):
            with self.subTest(path=invalid):
                paths = self.mod.discover_paths(system='Linux', env=self.env,
                                               overrides={'p10k_config': invalid})
                before = self.inventory()
                for dry_run in (True, False):
                    with self.subTest(dry_run=dry_run), self.assertRaises(self.mod.InstallerError):
                        self.mod.install(self.repo, paths, only=('powerlevel10k',),
                                         env=self.env, dry_run=dry_run, no_reload=True)
                    self.assertEqual(self.inventory(), before)

    def test_unused_prompt_paths_do_not_block_ghostty(self):
        (self.repo / 'ghostty').mkdir()
        ghostty_asset = self.repo / 'ghostty/github-light.conf'
        ghostty_asset.write_text('background = #ffffff\nforeground = #1f2328\n')
        self.asset.unlink()  # The optional prompt asset must not be needed either.
        invalid_tokens = ('relative/shell', str(self.home / 'folder/../shell'),
                          str(self.home / 'bad\nfile'), str(self.home / 'bad\rfile'),
                          str(self.home / 'bad\0file'))
        cases = [(key, token) for key in ('ZDOTDIR', 'p10k_config') for token in invalid_tokens]
        for index, (key, token) in enumerate(cases):
            with self.subTest(key=key, token=token):
                env = dict(self.env, PATH='')
                overrides = {}
                if key == 'ZDOTDIR':
                    env[key] = token
                else:
                    overrides[key] = token
                paths = self.mod.discover_paths(system='Linux', env=env, overrides=overrides)
                before = self.inventory()
                dry = self.mod.install(self.repo, paths, only=('ghostty',),
                                       env=env, dry_run=True, no_reload=True)
                self.assertEqual(set(dry.changed), {paths.ghostty_theme, *paths.ghostty_configs})
                self.assertEqual(self.inventory(), before)
                backup = self.root / f'unrelated private backup {index}'
                applied = self.mod.install(self.repo, paths, only=('ghostty',), env=env,
                                           backup_dir=backup, no_reload=True)
                self.assertEqual(paths.ghostty_theme.read_bytes(), ghostty_asset.read_bytes())
                self.assertFalse((self.home / '.p10k.zsh').exists())
                self.mod.restore(applied.backup, env=env, no_reload=True)
                self.assertEqual(self.inventory(), before)

    def test_invalid_zdotdir_is_rejected_only_when_prompt_is_selected(self):
        for invalid in ('relative/shell', str(self.home / 'folder/../shell'),
                        '~/folder/../shell', str(self.home / 'bad\nfile'),
                        str(self.home / 'bad\rfile'), str(self.home / 'bad\0file')):
            with self.subTest(zdotdir=invalid):
                env = dict(self.env, ZDOTDIR=invalid)
                paths = self.mod.discover_paths(system='Linux', env=env)
                before = self.inventory()
                for dry_run in (True, False):
                    with self.subTest(dry_run=dry_run), self.assertRaises(self.mod.InstallerError):
                        self.mod.install(self.repo, paths, only=('powerlevel10k',),
                                         env=env, dry_run=dry_run, no_reload=True)
                    self.assertEqual(self.inventory(), before)
                    self.assertFalse(paths.state_dir.exists())

    def test_prompt_tilde_paths_bind_to_home_at_selection_time(self):
        selected_home = self.root / 'another synthetic home'
        selected_home.mkdir()
        selected_env = dict(self.env, HOME=str(selected_home))
        cases = ((self.env, {'p10k_config': '~/custom prompt.zsh'}, 'custom prompt.zsh'),
                 (dict(self.env, ZDOTDIR='~/shell config'), {}, 'shell config/.p10k.zsh'))
        for index, (discovery_env, overrides, relative_target) in enumerate(cases):
            with self.subTest(target=relative_target):
                paths = self.mod.discover_paths(system='Linux', env=discovery_env, overrides=overrides)
                env = dict(selected_env)
                if 'ZDOTDIR' in discovery_env:
                    env['ZDOTDIR'] = discovery_env['ZDOTDIR']
                result = self.mod.install(self.repo, paths, only=('powerlevel10k',), env=env,
                                          backup_dir=self.root / f'tilde private backup {index}',
                                          no_reload=True)
                target = selected_home / relative_target
                self.assertEqual(result.changed, (target,))
                self.assertEqual(target.read_bytes(), self.asset.read_bytes())
                self.assertFalse((self.home / relative_target).exists())

    def assert_prompt_target_rejected(self, target, env, message='(?i)zsh startup'):
        paths = self.mod.discover_paths(system='Linux', env=env,
                                       overrides={'p10k_config': str(target)})
        before = self.inventory()
        for dry_run in (True, False):
            with self.subTest(target=str(target), dry_run=dry_run):
                with self.assertRaisesRegex(self.mod.InstallerError, message):
                    self.mod.install(self.repo, paths, only=('powerlevel10k',),
                                     env=env, dry_run=dry_run, no_reload=True)
                self.assertEqual(self.inventory(), before)
                self.assertFalse(paths.state_dir.exists())

    def test_prompt_override_rejects_zsh_startup_filenames(self):
        for name in ('.zshenv', '.zprofile', '.zshrc', '.zlogin', '.zlogout'):
            startup = self.home / name
            startup.write_bytes(b'# synthetic startup; never replace\n')
            self.assert_prompt_target_rejected(startup, self.env)
        renamed = self.home / 'renamed startup.zsh'
        renamed.write_bytes(b'# synthetic symlinked startup; never replace\n')
        startup = self.home / '.zshrc'
        startup.unlink()
        startup.symlink_to(renamed)
        self.assert_prompt_target_rejected(startup, self.env)

    def test_prompt_case_variant_startup_filenames_are_rejected(self):
        startup = self.home / '.zshrc'
        startup.write_bytes(b'# synthetic case-insensitive startup; never replace\n')
        variant = self.home / '.ZSHRC'
        alias = self.home / 'case variant startup alias.zsh'
        alias.symlink_to(variant)
        for target in (variant, alias):
            self.assert_prompt_target_rejected(target, self.env)
        self.assertTrue(alias.is_symlink())

    def test_prompt_case_variant_renamed_startup_aliases_are_rejected(self):
        shell_dir = self.home / 'shell config'
        shell_dir.mkdir()
        env = dict(self.env, ZDOTDIR=str(shell_dir))
        for index, directory in enumerate((self.home, shell_dir)):
            with self.subTest(startup_directory=str(directory)):
                renamed = self.home / f'Renamed Startup {index}.zsh'
                renamed.write_bytes(b'# synthetic renamed startup; never replace\n')
                variant = renamed.with_name(renamed.name.upper())
                if not variant.exists():
                    self.skipTest('case-insensitive filesystem is required for renamed aliases')
                startup = directory / '.zshrc'
                startup.symlink_to(renamed)
                alias = self.home / f'case variant renamed alias {index}.zsh'
                alias.symlink_to(variant)
                self.assertTrue(variant.samefile(startup))
                for target in (variant, alias):
                    self.assert_prompt_target_rejected(target, env)
                self.assertTrue(startup.is_symlink())
                self.assertTrue(alias.is_symlink())

    def test_prompt_symlink_alias_to_zshrc_is_rejected(self):
        startup = self.home / '.zshrc'
        startup.write_bytes(b'# synthetic private startup\n')
        alias = self.home / 'startup alias.zsh'
        alias.symlink_to(startup)
        target = self.home / '.p10k.zsh'
        target.symlink_to(alias)
        self.assert_prompt_target_rejected(target, self.env)
        self.assertTrue(target.is_symlink())
        self.assertTrue(alias.is_symlink())

    def test_prompt_alias_to_renamed_zshrc_target_is_rejected(self):
        shell_dir = self.home / 'shell config'
        shell_dir.mkdir()
        env = dict(self.env, ZDOTDIR=str(shell_dir))
        for index, directory in enumerate((self.home, shell_dir)):
            with self.subTest(startup_directory=str(directory)):
                renamed = self.home / f'renamed startup {index}.zsh'
                renamed.write_bytes(b'# synthetic private startup target\n')
                startup = directory / '.zshrc'
                startup.symlink_to(renamed)
                alias = self.home / f'prompt alias {index}.zsh'
                alias.symlink_to(renamed)
                for target in (renamed, alias):
                    self.assert_prompt_target_rejected(target, env)
                self.assertTrue(startup.is_symlink())
                self.assertTrue(alias.is_symlink())

    def test_prompt_hardlink_to_startup_remains_rejected(self):
        startup = self.home / '.zshrc'
        startup.write_bytes(b'# synthetic hardlinked startup\n')
        target = self.home / '.p10k.zsh'
        target.hardlink_to(startup)
        self.assert_prompt_target_rejected(target, self.env, '(?i)hardlink')
        self.assertEqual(target.stat().st_ino, startup.stat().st_ino)

    def test_prompt_symlink_to_non_startup_config_is_reversible(self):
        real = self.home / 'private prompt.zsh'
        original = b'# synthetic prompt symlink destination\r\n'
        real.write_bytes(original)
        real.chmod(0o640)
        target = self.home / '.p10k.zsh'
        target.symlink_to(real)
        paths = self.mod.discover_paths(system='Linux', env=self.env)
        result = self.mod.install(self.repo, paths, only=('powerlevel10k',),
                                  env=self.env, no_reload=True)
        self.assertEqual(real.read_bytes(), self.asset.read_bytes())
        self.assertTrue(target.is_symlink())
        self.assertEqual(target.readlink(), real)
        self.assertEqual(self.mod.install(self.repo, paths, only=('powerlevel10k',),
                                         env=self.env, no_reload=True).changed, ())
        self.mod.restore(result.backup, env=self.env, no_reload=True)
        self.assertEqual(real.read_bytes(), original)
        self.assertEqual(real.stat().st_mode & 0o777, 0o640)
        self.assertTrue(target.is_symlink())

    def test_mixed_prompt_and_ghostty_failure_rolls_back_all_targets(self):
        import json
        from unittest.mock import patch
        (self.repo / 'ghostty').mkdir()
        (self.repo / 'ghostty/github-light.conf').write_text('background = #ffffff\nforeground = #1f2328\n')
        paths = self.mod.discover_paths(system='Linux', env=self.env)
        prompt = self.home / '.p10k.zsh'
        prompt.write_bytes(b'# synthetic original prompt\r\n')
        prompt.chmod(0o640)
        config = paths.ghostty_configs[0].resolve()
        config.parent.mkdir(parents=True)
        original_config = b'# synthetic original Ghostty config\r\nfont-size = 13\r\n'
        config.write_bytes(original_config)
        before = self.inventory()
        backup = self.root / 'mixed private backup'
        atomic_write = self.mod._atomic_write
        failed = []

        def fail_after_config_write(path, content, mode, created=None):
            atomic_write(path, content, mode, created)
            if path == config and content != original_config:
                self.assertEqual(prompt.read_bytes(), self.asset.read_bytes())
                self.assertTrue(paths.ghostty_theme.exists())
                failed.append(path)
                raise OSError('synthetic mid-apply failure')

        with patch.object(self.mod, '_atomic_write', side_effect=fail_after_config_write):
            with self.assertRaisesRegex(self.mod.InstallerError, 'original files restored'):
                self.mod.install(self.repo, paths, only=('ghostty', 'powerlevel10k'),
                                 env=self.env, backup_dir=backup, no_reload=True)
        self.assertEqual(failed, [config])
        self.assertEqual(self.inventory(), before)
        self.assertFalse(paths.ghostty_theme.exists())
        manifest = json.loads((backup / 'manifest.json').read_text())
        self.assertEqual(manifest['status'], 'rolled-back')
        self.assertEqual(len(manifest['files']), 3)
        self.assertEqual(self.mod.restore(backup, env=self.env, no_reload=True).changed, ())

    def test_invalid_prompt_is_rejected_before_any_target_writes(self):
        (self.repo / 'ghostty').mkdir()
        (self.repo / 'ghostty/github-light.conf').write_text('background = #ffffff\nforeground = #1f2328\n')
        self.asset.write_text('if then !!!\n')
        paths = self.mod.discover_paths(system='Linux', env=self.env)
        before = self.inventory()
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run), self.assertRaisesRegex(self.mod.InstallerError, 'Invalid Powerlevel10k'):
                self.mod.install(self.repo, paths, only=('ghostty', 'powerlevel10k'),
                                  env=self.env, dry_run=dry_run, no_reload=True)
            self.assertEqual(self.inventory(), before)

    def test_missing_zsh_fails_without_writes(self):
        env = dict(self.env, PATH='')
        paths = self.mod.discover_paths(system='Linux', env=env)
        with self.assertRaisesRegex(self.mod.InstallerError, 'zsh on PATH'):
            self.mod.install(self.repo, paths, only=('powerlevel10k',), env=env, no_reload=True)
        self.assertEqual(self.inventory(), {})

    def test_syntax_validation_does_not_execute_the_prompt(self):
        self.asset.write_text('print -r -- synthetic > "$HOME/must-not-exist"\n')
        paths = self.mod.discover_paths(system='Linux', env=self.env)
        self.mod.install(self.repo, paths, only=('powerlevel10k',), env=self.env, no_reload=True)
        self.assertFalse((self.home / 'must-not-exist').exists())
        self.assertEqual(paths.p10k_config.read_bytes(), self.asset.read_bytes())

    def test_cli_applies_explicit_prompt_target_and_restores(self):
        target = self.home / 'custom prompt.zsh'
        startup = self.home / '.zshrc'
        startup.write_text('# synthetic startup\n')
        before = self.inventory()
        backup = self.root / 'cli private backup'
        apply = [sys.executable, str(REPO / 'scripts/apply'), '--only', 'powerlevel10k',
                 '--p10k-config', str(target), '--no-reload']
        dry = subprocess.run([*apply, '--dry-run'], env=self.env, cwd=self.root,
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn('Would update:', dry.stdout)
        self.assertEqual(self.inventory(), before)
        result = subprocess.run([*apply, '--backup-dir', str(backup)], env=self.env, cwd=self.root,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(target.read_bytes(), (REPO / 'zsh/p10k.zsh').read_bytes())
        restored = subprocess.run([sys.executable, str(REPO / 'scripts/restore'), str(backup), '--no-reload'],
                                  env=self.env, cwd=self.root, capture_output=True, text=True, timeout=30)
        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertEqual(self.inventory(), before)


class Powerlevel10kAssetTests(unittest.TestCase):
    def test_optional_ghostty_appearance_contains_only_font_and_option_settings(self):
        text = (REPO / 'ghostty/pangho-appearance.conf').read_text()
        settings = dict(line.strip().split(' = ', 1) for line in text.splitlines()
                        if line.strip() and not line.lstrip().startswith('#'))
        self.assertEqual(settings, {'font-family': 'D2Koding Ligature Nerd Font',
                                    'macos-option-as-alt': 'true'})

    def test_prompt_snapshot_keeps_two_line_layout_and_terminal_palette_colors(self):
        asset = REPO / 'zsh/p10k.zsh'
        self.assertTrue(asset.is_file(), 'the configured Powerlevel10k snapshot is missing')
        text = asset.read_text()
        self.assertNotIn('/Users/patrick', text)
        self.assertNotIn('/opt/homebrew', text)
        for line in text.splitlines():
            if line.lstrip().startswith('#'):
                continue
            match = re.match(r'\s*typeset -g POWERLEVEL9K_\S*(?:FOREGROUND|BACKGROUND|COLOR)=(\d+)\s*$', line)
            if match:
                self.assertLessEqual(int(match[1]), 15, line)
            for color in re.findall(r'%(\d+)[FK]|%[FK]\{(\d+)\}|segment -[fb] (\d+)', line):
                self.assertLessEqual(int(next(value for value in color if value)), 15, line)
        executable = shutil.which('zsh')
        if not executable:
            self.skipTest('zsh is required for prompt behavior checks')
        probe = r'''
source "$1" || exit 1
[[ ${(j:,:)POWERLEVEL9K_LEFT_PROMPT_ELEMENTS} == dir,vcs,newline,prompt_char ]] || exit 2
[[ $POWERLEVEL9K_BACKGROUND == '' ]] || exit 3
[[ $POWERLEVEL9K_PROMPT_CHAR_OK_VIINS_FOREGROUND == 2 ]] || exit 4
[[ $POWERLEVEL9K_PROMPT_CHAR_ERROR_VIINS_FOREGROUND == 1 ]] || exit 5
[[ $POWERLEVEL9K_DIR_FOREGROUND == 4 && $POWERLEVEL9K_DIR_SHORTENED_FOREGROUND == 8 ]] || exit 6
[[ $POWERLEVEL9K_TIME_FOREGROUND == 8 && $POWERLEVEL9K_MULTILINE_FIRST_PROMPT_GAP_FOREGROUND == 8 ]] || exit 7
[[ $POWERLEVEL9K_TRANSIENT_PROMPT == always && $POWERLEVEL9K_MODE == nerdfont-v3 ]] || exit 8
typeset -g P9K_CONTENT='' VCS_STATUS_LOCAL_BRANCH=synthetic_branch
typeset -g VCS_STATUS_TAG='' VCS_STATUS_REMOTE_BRANCH='' VCS_STATUS_COMMIT_SUMMARY='' VCS_STATUS_ACTION=''
typeset -gi VCS_STATUS_COMMITS_AHEAD=0 VCS_STATUS_COMMITS_BEHIND=0
typeset -gi VCS_STATUS_PUSH_COMMITS_AHEAD=0 VCS_STATUS_PUSH_COMMITS_BEHIND=0
typeset -gi VCS_STATUS_STASHES=0 VCS_STATUS_NUM_CONFLICTED=1
typeset -gi VCS_STATUS_NUM_STAGED=1 VCS_STATUS_NUM_UNSTAGED=1 VCS_STATUS_NUM_UNTRACKED=1
typeset -gi VCS_STATUS_HAS_UNSTAGED=1
my_git_formatter 1
[[ $my_git_format == *'%2Fsynthetic_branch'* && $my_git_format == *'%1F~1'* && $my_git_format == *'%3F+1'* && $my_git_format == *'%4F?1'* ]] || exit 9
my_git_formatter 0
[[ $my_git_format == *'%8Fsynthetic_branch'* ]] || exit 10
'''
        result = subprocess.run([executable, '-dfc', probe, 'prompt-test', str(asset)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
