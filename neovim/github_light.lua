-- GitHub Light appearance adapter; never reconfigure plugins or keymaps.
local M = {}

M.plugin = {
  src = 'https://github.com/projekt0n/github-nvim-theme',
  version = 'c106c9472154d6b2c74b74565616b877ae8ed31d',
}

function M.bufferline_highlights()
  local highlights = {
    fill = { fg = '#57606a', bg = '#f6f8fa' },
    background = { fg = '#57606a', bg = '#f6f8fa' },
    tab = { fg = '#57606a', bg = '#f6f8fa' },
    tab_selected = { fg = '#1f2328', bg = '#ffffff' },
    tab_close = { fg = '#57606a', bg = '#f6f8fa' },
    tab_separator = { fg = '#d0d7de', bg = '#f6f8fa' },
    tab_separator_selected = { fg = '#d0d7de', bg = '#ffffff' },
    buffer_visible = { fg = '#1f2328', bg = '#f6f8fa' },
    buffer_selected = { fg = '#1f2328', bg = '#ffffff', bold = true, italic = false },
    indicator_visible = { fg = '#d0d7de', bg = '#f6f8fa' },
    indicator_selected = { fg = '#0969da', bg = '#ffffff' },
    offset_separator = { fg = '#d0d7de', bg = '#f6f8fa' },
    trunc_marker = { fg = '#57606a', bg = '#f6f8fa' },
  }
  for _, name in ipairs {
    'close_button', 'numbers', 'diagnostic', 'hint', 'hint_diagnostic',
    'info', 'info_diagnostic', 'warning', 'warning_diagnostic', 'error',
    'error_diagnostic', 'modified', 'duplicate', 'separator', 'pick',
  } do
    for _, suffix in ipairs { '', '_visible', '_selected' } do
      highlights[name .. suffix] = { bg = suffix == '_selected' and '#ffffff' or '#f6f8fa' }
    end
  end
  for _, name in ipairs { 'separator', 'separator_visible', 'separator_selected' } do
    highlights[name].fg = '#d0d7de'
  end
  return highlights
end

local function set_overrides(name, overrides)
  local value = vim.api.nvim_get_hl(0, { name = name, link = false })
  -- Existing default=true would prevent a deliberate appearance override.
  value.default = nil
  value.link = nil
  for key, color in pairs(overrides) do
    value[key] = color
  end
  vim.api.nvim_set_hl(0, name, value)
end

function M.refresh()
  if vim.g.colors_name ~= 'github_light_default' then
    return
  end
  -- Includes dynamically generated devicon groups. Keep diagnostic/icon colors.
  for name in pairs(vim.api.nvim_get_hl(0, {})) do
    if name:match('^BufferLine') then
      set_overrides(name, { bg = name:match('Selected$') and '#ffffff' or '#f6f8fa' })
    end
  end
  for role, overrides in pairs(M.bufferline_highlights()) do
    local suffix = role:gsub('_(%l)', string.upper)
    suffix = suffix:sub(1, 1):upper() .. suffix:sub(2)
    set_overrides('BufferLine' .. suffix, overrides)
  end
end

local function load_plugin(options)
  local found, plugin = pcall(require, 'github-theme')
  if found then
    return plugin
  end
  -- Activate an existing optional package without changing its pinned revision.
  pcall(vim.cmd.packadd, 'github-nvim-theme')
  found, plugin = pcall(require, 'github-theme')
  if found then
    return plugin
  end
  if options.auto_install == false or not (vim.pack and vim.pack.add) then
    error('github-nvim-theme is required. Install projekt0n/github-nvim-theme with your plugin manager, '
      .. 'or use Neovim with vim.pack support and allow auto_install.')
  end
  -- Only this new theme dependency is installed; existing plugins are untouched.
  vim.pack.add({ M.plugin }, { confirm = false })
  return require('github-theme')
end

function M.setup(options)
  options = options or {}
  local plugin = load_plugin(options)
  vim.opt.background = 'light'
  vim.opt.termguicolors = true
  plugin.setup {
    options = { transparent = false, styles = { comments = 'NONE' } },
    palettes = { github_light_default = { bg1 = '#ffffff', fg1 = '#1f2328' } },
    groups = {
      github_light_default = {
        StatusLine = { fg = '#1f2328', bg = '#f6f8fa' },
        StatusLineNC = { fg = '#57606a', bg = '#f6f8fa' },
      },
    },
  }
  local group = vim.api.nvim_create_augroup('TerminalThemeGithubLight', { clear = true })
  vim.api.nvim_create_autocmd({ 'ColorScheme', 'VimEnter', 'BufEnter', 'BufWinEnter' }, {
    group = group,
    callback = function()
      -- Let bufferline/lazy plugin callbacks finish before applying colors.
      vim.schedule(M.refresh)
    end,
  })
  vim.cmd.colorscheme 'github_light_default'
  M.refresh()
  vim.schedule(M.refresh)
end

return M
