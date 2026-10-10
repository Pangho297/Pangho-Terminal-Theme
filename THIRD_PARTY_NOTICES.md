# Third-party notices

The installer and appearance adapter are original code; no full Neovim plugin,
application configuration, credentials, or font files are vendored here.

## Ghostty palette

`ghostty/github-light.conf` snapshots the installed Ghostty **GitHub Light
Default** palette, distributed by the iTerm2-Color-Schemes collection.

- Source: https://github.com/mbadolato/iTerm2-Color-Schemes/tree/master/ghostty
- Collection license: `licenses/iTerm2-Color-Schemes-MIT.txt`
- The collection notes that individual themes retain their authors' licenses.
- GitHub theme project: https://github.com/primer/github-vscode-theme
- GitHub theme license: `licenses/github-vscode-theme-MIT.txt`

## Neovim dependency

`projekt0n/github-nvim-theme` is an external MIT-licensed dependency, not
vendored plugin code. The automatic fresh installation uses revision
`c106c9472154d6b2c74b74565616b877ae8ed31d`; already-installed plugin revisions
are not automatically upgraded or replaced.

- Source: https://github.com/projekt0n/github-nvim-theme
- License: `licenses/github-nvim-theme-MIT.txt`

## Hermes CLI compatibility patch

`hermes/cli-diff-colors.patch` contains a minimal modification and context from
Hermes Agent's MIT-licensed `agent/display.py`, enabling its CLI to consume the
same explicit diff colors as its TUI.

- Source: https://github.com/NousResearch/hermes-agent
- Copyright (c) 2025 Nous Research
- License: `licenses/hermes-agent-MIT.txt`

Other applications and optional UI plugins keep their own licenses.
