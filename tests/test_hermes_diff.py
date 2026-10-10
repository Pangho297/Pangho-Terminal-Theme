"""Check skin assets and, when opted in, the actual installed Hermes CLI renderer.

Set HERMES_AGENT_SOURCE to an installed Hermes source checkout for runtime tests.
Synthetic diff text is clearly a test fixture; no user files or configs are edited.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
DIFF_COLORS = {
    'diff_added': '#dafbe1',
    'diff_added_word': '#116329',
    'diff_removed': '#ffebe9',
    'diff_removed_word': '#82071e',
}


class HermesDiffSkinTests(unittest.TestCase):
    def test_github_light_has_explicit_diff_backgrounds_and_foregrounds(self):
        text = (ROOT / 'hermes/github-light.yaml').read_text()
        for key, color in DIFF_COLORS.items():
            self.assertIn(f'{key}: "{color}"', text)


class HermesDiffRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value = os.environ.get('HERMES_AGENT_SOURCE')
        if not value:
            raise unittest.SkipTest('Set HERMES_AGENT_SOURCE to opt into installed CLI renderer checks')
        cls.source = Path(value).resolve()
        if not (cls.source / 'agent/display.py').is_file():
            raise unittest.SkipTest('Installed Hermes source unavailable at HERMES_AGENT_SOURCE')

    def render_check(self, code):
        prefix = (
            'import sys\n'
            f'sys.path.insert(0, {str(self.source)!r})\n'
            'import hermes_bootstrap\n'
            'from hermes_cli.skin_engine import SkinConfig\n'
            'from agent import display\n'
            'colors = ' + repr(DIFF_COLORS) + '\n'
            "colors.update({'ui_ok':'#1a7f37','ui_error':'#cf222e'})\n"
            "skin = SkinConfig(name='synthetic-github-light-diff', colors=colors)\n"
            'display._get_skin = lambda: skin\n'
        )
        done = subprocess.run([sys.executable, '-c', prefix + code],
                              text=True, capture_output=True, timeout=45)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_added_removed_lines_use_exact_light_background_and_dark_text(self):
        self.render_check("""
actual = display._diff_ansi()
assert actual['plus'] == '\\x1b[38;2;17;99;41;48;2;218;251;225m', repr(actual)
assert actual['minus'] == '\\x1b[38;2;130;7;30;48;2;255;235;233m', repr(actual)
""")

    def test_live_color_changes_do_not_reuse_stale_diff_cache(self):
        self.render_check("""
first = display._diff_ansi()['plus']
skin.colors['diff_added'] = '#ccffd8'
second = display._diff_ansi()['plus']
assert first != second, 'A skin edit must change subsequent rendered diffs'
assert '48;2;204;255;216m' in second
""")

    def test_other_skins_and_malformed_overrides_keep_legacy_fallback(self):
        self.render_check("""
skin.colors = {'ui_ok':'#1a7f37','ui_error':'#cf222e'}
expected = display._diff_ansi()
assert expected['plus'] == '\\x1b[38;2;255;255;255;48;2;10;63;13m'
assert expected['minus'] == '\\x1b[38;2;255;255;255;48;2;103;10;11m'
skin.colors.update({'diff_added':'#invalid','diff_added_word':'#116329'})
assert display._diff_ansi()['plus'] == expected['plus']
display._get_skin = lambda: None
assert display._diff_ansi()['plus'] == '\\x1b[38;2;255;255;255;48;2;20;90;20m'
""")

    def test_backgrounds_bypass_foreground_only_light_color_remapping(self):
        self.render_check("""
raw_get_color = skin.get_color
skin.get_color = lambda key, fallback='': '#000000' if key.startswith('diff_') else raw_get_color(key, fallback)
assert display._diff_ansi()['plus'] == '\\x1b[38;2;17;99;41;48;2;218;251;225m'
""")

    def test_real_inline_diff_keeps_content_and_colors_additions_deletions(self):
        self.render_check("""
import re
fixture = '--- a/synthetic.py\\n+++ b/synthetic.py\\n@@ -1 +1 @@\\n-old_value = 1\\n+new_value = 2\\n'
lines = display._render_inline_unified_diff(fixture)
added = next(line for line in lines if '+new_value' in line)
removed = next(line for line in lines if '-old_value' in line)
assert added.startswith('\\x1b[38;2;17;99;41;48;2;218;251;225m')
assert removed.startswith('\\x1b[38;2;130;7;30;48;2;255;235;233m')
strip = lambda line: re.sub(r'\\x1b\\[[0-9;]*m', '', line)
assert strip(added) == '+new_value = 2'
assert strip(removed) == '-old_value = 1'
""")


if __name__ == '__main__':
    unittest.main()
