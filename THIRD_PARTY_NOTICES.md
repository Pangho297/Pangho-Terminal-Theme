# Third-party notices

The installer and appearance adapter are original code; no full Neovim plugin,
account configuration, credentials, or font files are vendored here. A
generated Powerlevel10k prompt configuration is included separately below.

## Ghostty palette

`ghostty/github-light.conf` snapshots the installed Ghostty **GitHub Light
Default** palette, distributed by the iTerm2-Color-Schemes collection.

- Source: https://github.com/mbadolato/iTerm2-Color-Schemes/tree/master/ghostty
- Collection license: `licenses/iTerm2-Color-Schemes-MIT.txt`
- The collection notes that individual themes retain their authors' licenses.
- GitHub theme project: https://github.com/primer/github-vscode-theme
- GitHub theme license: `licenses/github-vscode-theme-MIT.txt`

## Powerlevel10k prompt configuration

`zsh/p10k.zsh` is a customized generated configuration based on Powerlevel10k's
`config/p10k-lean.zsh`. It preserves the selected two-line prompt layout and
uses the terminal's ANSI palette for its active colors. The Powerlevel10k
plugin itself is an external dependency and is not vendored or downloaded
by the installer.

- Source: https://github.com/romkatv/powerlevel10k
- Copyright (c) 2009–2014 Robby Russell and contributors
- Copyright (c) 2014–2017 Ben Hilburn
- Copyright (c) 2019 Roman Perepelitsa and contributors
- License: `licenses/powerlevel10k-MIT.txt`

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
