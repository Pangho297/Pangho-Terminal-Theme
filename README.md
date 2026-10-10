# GitHub Light Terminal Theme

Ghostty · Neovim/Neo-tree/bufferline · Herdr · Hermes를 같은 GitHub Light 계열로 맞추는 **테마 전용 저장소**입니다.

- 기본 배경: `#ffffff`
- 보조 배경: `#f6f8fa`
- 기본 글씨: `#1f2328`
- 파란 포인트: `#0969da`

전체 개발 환경이나 개인 설정을 배포하지 않습니다. 셸 실행 경로, 글꼴, 키맵, LSP, 기존 플러그인 옵션, 모델/프로바이더 설정은 대상 기기의 것을 유지합니다.

## 구성

```text
terminal-theme/
├── ghostty/github-light.conf       # Ghostty 팔레트 스냅샷
├── neovim/github_light.lua         # 테마와 사이드바/탭 외형 모듈
├── herdr/theme.toml                # [theme] 부분만 담은 조각
├── hermes/github-light.yaml        # 계정 설정 없는 스킨
├── scripts/apply                   # 백업 후 테마 적용
├── scripts/restore                 # 적용 전 상태 복구
├── scripts/theme_installer.py      # 표준 라이브러리 설치 도구
├── tests/                          # 설치 도구/테마 테스트
└── THIRD_PARTY_NOTICES.md
```

## 준비 사항

- Python 3.11 이상. 확인: `python3 --version`.
- Ghostty, Herdr, Hermes, Neovim은 대상 기기에 이미 설치되어 있어야 합니다.
- 자동 테마 플러그인 설치에는 `vim.pack`을 지원하는 Neovim 0.12 이상과 첫 실행 시 Git/GitHub 연결이 필요합니다.
- 기존 플러그인 관리자로 `projekt0n/github-nvim-theme`를 설치했다면 자동 설치 없이 사용할 수 있습니다.
- Neo-tree와 bufferline은 이 저장소가 새로 설치하거나 기능 설정을 변경하지 않습니다. 이미 사용하는 환경을 전제로 합니다.
- 현재 Herdr/Hermes 버전이 사용자 지정 테마·스킨을 지원해야 합니다.

폰트는 배포하거나 강제로 바꾸지 않습니다. 같은 타이포그래피까지 원하면 양쪽 기기에 `D2KodingLigature Nerd Font`를 별도로 설치하고 Ghostty의 글꼴 설정을 맞추세요.

## macOS 또는 Linux에서 적용

저장소를 원하는 위치에 clone한 뒤, 먼저 변경 계획을 확인합니다.

```sh
cd ~/Projects/terminal-theme
./scripts/apply --dry-run
```

계획이 맞으면 적용합니다.

```sh
./scripts/apply
```

일부 앱만 적용하려면:

```sh
./scripts/apply --only ghostty neovim
./scripts/apply --only herdr hermes
```

서버 reload를 생략하려면 `--no-reload`를 추가하세요. 사용 가능한 옵션과 경로 재정의는 `./scripts/apply --help`에서 확인할 수 있습니다.

설치 도구는 기존 파일을 먼저 백업하고, 테마용 managed block/파일만 변경합니다. 재실행해도 같은 블록이 중복되지 않습니다. 오류가 발생하면 부분 적용을 되돌립니다. 지원하지 않는 설정 형식은 전체 파일을 덮어쓰는 대신 오류로 중단합니다.

### 경로와 운영체제 차이

- Ghostty는 XDG 경로와 macOS의 `~/Library/Application Support/com.mitchellh.ghostty/` 경로를 확인합니다. 이미 존재하는 여러 설정 파일에 동일한 테마 지정과 색상값을 넣습니다. 기존 `background`, `foreground`, `palette` 등 직접 지정된 색상보다 managed block의 GitHub Light 색상이 우선하도록 하되, 셸·글꼴·키 설정은 유지합니다.
- Neovim은 XDG 설정 경로와 `NVIM_APPNAME`을 존중합니다. 기존 `init.lua` 끝에 테마 모듈 호출만 추가합니다. `init.vim` 기반 환경은 자동 변경하지 않으므로 아래의 수동 통합 방법을 사용하세요.
- Herdr는 `HERDR_CONFIG_PATH`, Hermes는 `HERMES_HOME`을 존중합니다. Hermes 프로필을 여러 개 쓴다면 적용할 프로필의 `HERMES_HOME`을 명시하세요.
- Linux의 `/usr/bin/zsh` 같은 셸 경로는 이 저장소에 포함하지 않습니다.
- 경로 재정의에는 절대 경로를 사용하세요. 개행·NUL·`..`가 포함된 경로는 적용 전에 거부합니다.

### 적용 후

- Ghostty: 설정 reload 또는 새 창에서 확인하세요.
- Neovim: 작업을 저장한 뒤 다시 열어 확인하세요. 전체 `init.lua`를 다시 source하면 기존 autocommand/plugin 설정이 중복될 수 있으므로 권장하지 않습니다.
- Herdr: 실행 중인 서버가 있으면 설정 reload를 시도하며, 서버를 종료하지 않습니다. reload를 하지 못했으면 출력된 경고를 확인하고 다음 실행에서 확인하세요.
- Hermes: `hermes config get display.skin`이 `github-light`인지 확인하세요. 기존 화면에 이전 색이 남아 있다면 다음 실행에서도 확인하세요.

## 복구

apply가 출력한 백업 디렉터리 경로를 사용합니다.

```sh
./scripts/restore /path/to/the/printed/backup-directory --dry-run
./scripts/restore /path/to/the/printed/backup-directory
```

적용 이후 파일을 직접 편집했다면 복구는 기본적으로 중단하여 그 변경을 보호합니다. 내용을 확인하고 **변경을 버려도 될 때만** `--force`를 사용하세요. 백업에는 원래 설정이 들어갈 수 있으므로 공개 저장소나 메시지에 올리지 마세요.

기본 백업 위치는 `${XDG_STATE_HOME:-$HOME/.local/state}/terminal-theme/backups/`입니다. `--backup-dir`로 저장소 밖의 새 디렉터리를 지정할 수도 있습니다. 복구는 apply가 변경한 설정 파일·테마 모듈·스킨에 적용됩니다. Neovim 첫 실행에서 내려받은 테마 플러그인과 앱이 만든 캐시는 자동으로 삭제하지 않습니다.

## Neovim 수동 통합

자동 삽입이 적합하지 않거나 `init.vim`을 쓰는 경우:

1. `neovim/github_light.lua`를 대상 Neovim 설정의 `lua/github_light.lua`에 복사합니다.
2. 기존 플러그인 관리자로 `projekt0n/github-nvim-theme`를 추가합니다.
3. 기존 UI 플러그인 설정 뒤에서 호출합니다.

```lua
require('github_light').setup { auto_install = false }
```

`init.vim`에서는:

```vim
lua require('github_light').setup({ auto_install = false })
```

일반 자동 설치는 기존에 설치된 테마 플러그인을 우선 사용하고, 새로 설치하는 경우 검증 당시의 Git revision을 지정합니다. 이미 설치된 플러그인의 revision을 강제로 바꾸지는 않습니다.

모듈은 bufferline을 다시 `setup()`하지 않습니다. 닫기 동작·진단 옵션·키맵 등은 그대로 두고 highlight 색만 조정하며, 새 버퍼와 colorscheme 이벤트 뒤에도 외형을 맞춥니다. 사용자가 다른 colorscheme으로 전환하면 해당 테마를 계속 덮어쓰지 않습니다.

GitHub 테마의 캐시 때문에 사용자 지정 색이 반영되지 않을 때는 Neovim에서 `:GithubThemeCompile`을 실행한 뒤 다시 확인하세요.

## Hermes diff 색상과 CLI 호환 패치

추가 줄은 연녹색 배경 `#dafbe1` + 진녹색 글씨 `#116329`, 제거 줄은 연빨강 배경 `#ffebe9` + 진빨강 글씨 `#82071e`를 사용합니다. `diff_added`, `diff_added_word`, `diff_removed`, `diff_removed_word`에 지정되어 있으며, 다른 포인트·상태 색은 바꾸지 않습니다.

Hermes TUI는 이 스킨 키를 지원하지만, 여기서 검증한 CLI의 `agent/display.py`는 어두운 배경과 흰 글씨를 직접 계산하고 첫 결과를 계속 캐시했습니다. 스킨만 바꿔도 같은 문제가 남는 CLI를 위해 `hermes/cli-diff-colors.patch`를 제공합니다. 이 패치는 diff 전용 색상 쌍을 읽도록 하고 오래된 캐시를 제거하며, 별도 색상 지정이 없는 다른 스킨은 기존 표시를 유지합니다.

apply는 **스킨만 설치**하며 Hermes 소스 패치를 자동 적용하지 않습니다. CLI에서도 같은 증상이 있다면, 실제 Hermes 소스 위치를 확인한 뒤 다음 절차를 사용하세요. 기본 경로가 아닌 설치는 `HERMES_SOURCE`를 그 위치로 바꾸세요.

```sh
cd ~/Projects/terminal-theme
HERMES_SOURCE="$HOME/.hermes/hermes-agent"
THEME_REPO="$PWD"
git -C "$HERMES_SOURCE" status --short -- agent/display.py
# 기존 로컬 수정이 있으면 먼저 별도로 백업하고 충돌 여부를 검토하세요.
git -C "$HERMES_SOURCE" apply --check "$THEME_REPO/hermes/cli-diff-colors.patch"
# --check가 성공했을 때만 실행합니다.
git -C "$HERMES_SOURCE" apply "$THEME_REPO/hermes/cli-diff-colors.patch"
./scripts/apply --only hermes --no-reload
```

이미 설치된 CLI가 이 키를 지원하면 소스 패치는 필요 없습니다. 버전 차이로 `--check`가 실패하면 강제로 적용하지 마세요. 패치는 여기서 검증한 소스 구조와 호환되는 버전용이며, 모든 Hermes 버전에 적용된다고 보장하지 않습니다.

소스 코드는 실행 중인 프로세스에 자동으로 다시 로드되지 않으므로, 작업을 마친 뒤 Hermes를 다시 실행해야 새 CLI diff 표시가 반영됩니다. 이전 출력의 색이 소급 변경되지는 않습니다.

Hermes 업데이트 전이나 코드 패치를 되돌릴 때는 먼저 역적용 가능 여부를 확인하세요:

```sh
git -C "$HERMES_SOURCE" apply --reverse --check "$THEME_REPO/hermes/cli-diff-colors.patch"
git -C "$HERMES_SOURCE" apply --reverse "$THEME_REPO/hermes/cli-diff-colors.patch"
```

이 역패치는 렌더러 코드만 되돌립니다. 스킨은 apply가 만든 백업으로 별도 복구할 수 있습니다.

## 테스트

```sh
python3 -m unittest discover -s tests -v
```

실제 설치된 Hermes CLI 렌더러의 diff 색상도 검증하려면 호환 패치를 적용한 소스 위치를 명시합니다. 이 환경변수가 없으면 해당 렌더러 테스트는 skip되며, 스킨 파일 테스트는 계속 실행됩니다.

```sh
HERMES_AGENT_SOURCE="$HOME/.hermes/hermes-agent" python3 -m unittest discover -s tests -v
```

설치 도구 테스트는 임시 HOME과 명시적인 합성 fixture로 실행합니다. Darwin 경로 분기 테스트는 **macOS를 실제 실행한 테스트가 아니라 경로 시뮬레이션**입니다. Neovim 통합 테스트는 설치된 플러그인을 발견했을 때 네트워크 없이 실제 Neovim을 실행하고, 별도 cache/state를 사용합니다. 해당 도구/플러그인이 없으면 관련 테스트는 skip됩니다.

이 저장소를 만든 환경에서는 Linux의 실제 도구로 검사합니다. macOS 실기에서의 최종 적용 확인은 별도로 필요합니다.

초기 버전 검증:
- 자동 테스트 40개 통과, skip 없음.
- 격리된 HOME에서 실제 Ghostty/Neovim/Hermes의 적용·재적용·복구 확인.
- 별도 소켓의 임시 Herdr 서버에서 설정 reload와 복구 확인. 사용 중인 서버는 종료하지 않음.
- 직접 지정된 Ghostty 다크 색상 덮어쓰기와 `..` 경로 사전 거부 회귀 테스트 포함.
- 기존 기기의 앱 설정 파일은 변경하지 않음.

## GitHub에 직접 등록

이 로컬 저장소는 `main` 브랜치를 사용하며 origin은 설정하지 않습니다. GitHub에서 빈 저장소를 만든 다음:

```sh
git remote add origin <your-repository-url>
git push -u origin main
```

API 키, `.env`, 인증 파일, 세션/로그/DB, 전체 Hermes 설정과 백업은 올리지 마세요. `.gitignore`는 보조 안전장치일 뿐이므로, 업로드 전 `git status`와 `git diff --cached`도 확인하세요.

## 출처와 라이선스

원본 팔레트와 외부 테마 플러그인의 출처/라이선스는 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)에 정리했습니다. 이 저장소의 자체 설치 도구와 어댑터는 MIT 라이선스입니다.
