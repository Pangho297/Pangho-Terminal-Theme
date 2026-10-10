"""Asset checks and real, network-free Neovim integration tests.

Neovim tests use already-installed dependencies, isolated cache/state directories,
and -u NONE; they never load or edit the user's live configuration.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ThemeAssetTests(unittest.TestCase):
    def test_ghostty_snapshot_is_complete_and_not_machine_specific(self):
        text = (ROOT / "ghostty/github-light.conf").read_text()
        values = [line.strip().split("=", 1) for line in text.splitlines()
                  if line.strip() and not line.lstrip().startswith("#")]
        palette = {}
        settings = {}
        for key, value in values:
            key, value = key.strip(), value.strip()
            if key == "palette":
                index, color = value.split("=", 1)
                palette[int(index)] = color
            else:
                settings[key] = value
        self.assertEqual(set(palette), set(range(16)))
        self.assertEqual(settings["background"], "#ffffff")
        self.assertEqual(settings["foreground"], "#1f2328")
        self.assertEqual(settings["cursor-color"], "#0969da")
        self.assertFalse({"command", "font-family", "font-size", "theme"} & settings.keys())
        self.assertNotIn("/home/", text)

    def test_herdr_asset_contains_only_theme_settings(self):
        data = tomllib.loads((ROOT / "herdr/theme.toml").read_text())
        self.assertEqual(set(data), {"theme"})
        self.assertEqual(data["theme"]["name"], "terminal")
        self.assertFalse(data["theme"]["auto_switch"])
        colors = data["theme"]["custom"]
        self.assertEqual(colors["panel_bg"], "#ffffff")
        self.assertEqual(colors["sidebar_bg"], "#f6f8fa")
        self.assertEqual(colors["text"], "#1f2328")
        self.assertEqual(colors["accent"], "#0969da")

    def test_hermes_skin_is_light_and_contains_no_account_config(self):
        text = (ROOT / "hermes/github-light.yaml").read_text()
        self.assertIn("name: github-light", text)
        for line in ('background: "#ffffff"', 'ui_accent: "#0969da"',
                     'banner_text: "#1f2328"', 'status_bar_bg: "#f6f8fa"',
                     'completion_menu_bg: "#f6f8fa"'):
            self.assertIn(line, text)
        for forbidden in ("api_key:", "provider:", "model:", "password:", "access_token:"):
            self.assertNotIn(forbidden, text)

    def test_neovim_asset_exists_and_has_no_local_home_path(self):
        text = (ROOT / "neovim/github_light.lua").read_text()
        self.assertIn("github_light_default", text)
        self.assertNotIn("/home/pangho", text)
        self.assertNotIn("/usr/bin/zsh", text)


class NeovimIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nvim = shutil.which("nvim")
        data = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
        cls.pack = data / os.environ.get("NVIM_APPNAME", "nvim") / "site/pack/core/opt"
        if not cls.nvim:
            raise unittest.SkipTest("Neovim is not installed")

    def run_lua(self, lua, dependencies=()):
        assert self.nvim is not None
        with tempfile.TemporaryDirectory(prefix="terminal-theme-nvim-test-") as directory:
            fixture = Path(directory)
            env = os.environ.copy()
            env.update({"HOME": str(fixture), "XDG_CONFIG_HOME": str(fixture / "config"),
                        "XDG_CACHE_HOME": str(fixture / "cache"), "XDG_STATE_HOME": str(fixture / "state"),
                        "XDG_DATA_HOME": str(fixture / "data"), "NVIM_APPNAME": "nvim"})
            paths = []
            for name in dependencies:
                path = self.pack / name
                if not path.is_dir():
                    self.skipTest("Already-installed dependency unavailable: " + name)
                paths.append(path)
            prelude = "\n".join("vim.opt.runtimepath:append(" + json.dumps(str(path), ensure_ascii=False) + ")"
                                for path in paths)
            script = fixture / "check.lua"
            script.write_text(prelude + "\nlocal ok, err = pcall(function()\n" + lua +
                              "\nend)\nif not ok then io.stderr:write(tostring(err) .. '\\n'); vim.cmd('cquit 1') end\n")
            done = subprocess.run([self.nvim, "--headless", "-u", "NONE", "-i", "NONE",
                                   "+luafile " + str(script), "+qa!"], env=env,
                                  text=True, capture_output=True, timeout=45)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            return done.stdout + done.stderr

    def test_missing_plugin_fails_clearly_without_network(self):
        module = json.dumps(str(ROOT / "neovim/github_light.lua"), ensure_ascii=False)
        self.run_lua("""
local theme = dofile(MODULE)
local ok, err = pcall(theme.setup, { auto_install = false })
assert(not ok, 'a missing plugin must not be hidden')
assert(tostring(err):find('github%-nvim%-theme'), 'error must identify the required plugin')
""".replace("MODULE", module))

    def test_real_github_theme_and_bufferline_preserve_behavior(self):
        module = json.dumps(str(ROOT / "neovim/github_light.lua"), ensure_ascii=False)
        output = self.run_lua("""
vim.o.number = true
vim.keymap.set('n', '<F6>', ':echo "existing mapping"<CR>')
local existing_close = function() return 'existing-close' end
require('bufferline').setup {
  options = { always_show_bufferline = false, separator_style = 'thin',
              close_command = existing_close, diagnostics = 'nvim_lsp' },
  highlights = { error_selected = { fg = '#cf222e' } },
}
local theme = dofile(MODULE)
theme.setup { auto_install = false }
vim.wait(1000, function()
  local h = vim.api.nvim_get_hl(0, { name = 'BufferLineFill', link = false })
  return h.bg == tonumber('f6f8fa', 16)
end)
assert(vim.g.colors_name == 'github_light_default')
assert(vim.o.background == 'light')
assert(vim.o.number, 'number option must be preserved')
assert(vim.fn.maparg('<F6>', 'n'):find('existing mapping'), 'mapping must be preserved')
local config = require('bufferline.config').get()
assert(config.options.close_command == existing_close, 'close callback must not be reset')
assert(config.options.always_show_bufferline == false, 'bufferline options must not be reset')
assert(config.options.separator_style == 'thin')
local expected = {
  Normal = { fg = '#1f2328', bg = '#ffffff' },
  NeoTreeNormal = { fg = '#1f2328', bg = '#f6f8fa' },
  BufferLineFill = { fg = '#57606a', bg = '#f6f8fa' },
  BufferLineBufferSelected = { fg = '#1f2328', bg = '#ffffff' },
  BufferLineIndicatorSelected = { fg = '#0969da', bg = '#ffffff' },
  StatusLine = { fg = '#1f2328', bg = '#f6f8fa' },
}
for name, wanted in pairs(expected) do
  local actual = vim.api.nvim_get_hl(0, { name = name, link = false })
  for key, color in pairs(wanted) do
    assert(actual[key] == tonumber(color:sub(2), 16), name .. '.' .. key .. ' mismatch')
  end
end
assert(vim.api.nvim_get_hl(0, {name='BufferLineErrorSelected',link=false}).fg == tonumber('cf222e',16),
       'diagnostic foreground must be preserved')
local before = #vim.api.nvim_get_autocmds { group = 'TerminalThemeGithubLight' }
theme.setup { auto_install = false }
vim.wait(50, function() return false end)
assert(#vim.api.nvim_get_autocmds { group = 'TerminalThemeGithubLight' } == before,
       'repeated setup must not duplicate autocommands')
vim.cmd('colorscheme github_light_default')
vim.wait(1000, function()
  return vim.api.nvim_get_hl(0,{name='BufferLineFill',link=false}).bg == tonumber('f6f8fa',16)
end)
assert(vim.api.nvim_get_hl(0,{name='BufferLineFill',link=false}).bg == tonumber('f6f8fa',16))
assert(vim.v.errmsg == '', 'startup must be error-free')
print('NEOVIM_THEME_INTEGRATION_PASS')
""".replace("MODULE", module), dependencies=("github-nvim-theme", "bufferline.nvim"))
        self.assertIn("NEOVIM_THEME_INTEGRATION_PASS", output)


if __name__ == "__main__":
    unittest.main()
