# skill-architecture

複数のCodex Skillを、責務と依存関係に基づいて組み合わせるためのアーキテクチャを設計・検証するリポジトリです。

## Architecture

Skillを次の3種類に分けます。

- **Workflow**: 複数のSkillを組み合わせ、ユースケース全体を進める
- **Capability**: 調査、変換、生成、検証などの再利用可能な能力を提供する
- **Adapter**: 外部ツールやサービスなど、具体的な技術との接続を扱う

詳しい責務と依存ルールは [ARCHITECTURE.md](ARCHITECTURE.md) を参照してください。

## Repository structure

```text
.
|-- README.md
|-- ARCHITECTURE.md
`-- skills/
    |-- workflows/
    |   |-- explain-implementation/
    |   |   `-- SKILL.md
    |   |-- fix-bug/
    |   |   `-- SKILL.md
    |   `-- implement-feature/
    |       `-- SKILL.md
    |-- capabilities/
    |   |-- analyze-codebase/
    |   |-- assess-change-impact/
    |   |-- implement-code-change/
    |   |-- plan-code-change/
    |   |-- render-markdown/
    |   `-- verify-code-change/
    `-- adapters/
        `-- render-archify-diagram/
            `-- SKILL.md
```

## Included skills

### Workflow

- `implement-feature`: 要求の具体化から実装と検証まで、機能追加の一連の作業を進める
- `fix-bug`: 不具合の再現と原因調査から修正、回帰検証までを進める
- `explain-implementation`: 既存コードを調査し、現在の仕組みと処理の流れを根拠付きで説明する

### Capability

- `analyze-codebase`: 実装経路、制約、既存パターン、関連テストを調査する
- `assess-change-impact`: コード変更がインターフェース、データ、設定、テスト、文書、運用へ与える影響を調査する
- `plan-code-change`: 要求と調査結果から、実装方針、機能単位の実施順、検証方法を決める
- `render-markdown`: JSONを指定されたスキーマで検証し、テンプレートから再現可能なMarkdownを生成する
- `implement-code-change`: 合意済みの方針に基づいて、コード、テスト、文書へ変更を適用する
- `verify-code-change`: 実装結果について、要求の充足、意図しない差分、回帰の有無を検証する

### Adapter

- `render-archify-diagram`: 仕様JSONをインストール済みのArchify CLIでHTML図へ変換し、成果物と診断を返す

Archify本体はこのリポジトリに同梱しません。

## Naming policy

共通の命名規約設定と利用先設定を分離し、設定からコミット件名・PRタイトル・ブランチ名の規約文書を生成します。設定方法と生成手順は[policy/README.md](policy/README.md)、このリポジトリ向けの生成文書は[policy/NAMING.md](policy/NAMING.md)を参照してください。

Python 3.10以上が必要です。利用先リポジトリのルートで次を実行します。

macOS / Linux:

```sh
sh ../skill-architecture/scripts/install-policy.sh --project .
```

Windows:

```powershell
../skill-architecture/scripts/install-policy.ps1 -Project .
```

パスは命名規約リポジトリをcloneした場所に合わせてください。既定ではGitの`commit-msg` hook、共通設定、利用先設定例、生成文書、PRのCIを導入し、`AGENTS.md`へ生成文書の参照を追加します。利用先のscope設定は`policy/local.json`で編集します。共通設定の変更を取り込む場合は、clone先を更新してinstallを再実行します。利用先の設定と既存hookは引き継ぎます。

Claude CodeとCodexの`PreToolUse` hookは任意です。ポリシーに関わるBashコマンドを実行前に同じ判定ロジックで検証・補完します。

```sh
sh ../skill-architecture/scripts/install-policy.sh --project . --agent-hook claude
sh ../skill-architecture/scripts/install-policy.sh --project . --agent-hook codex
sh ../skill-architecture/scripts/install-policy.sh --project . --agent-hook claude --agent-hook codex
```

```powershell
../skill-architecture/scripts/install-policy.ps1 -Project . -ClaudeHook
../skill-architecture/scripts/install-policy.ps1 -Project . -CodexHook
../skill-architecture/scripts/install-policy.ps1 -Project . -ClaudeHook -CodexHook
```

Codexのproject hookは初回に信頼確認が必要です。Codexで`/hooks`を開き、導入した命名規約hookを確認して信頼してください。

解除時は利用先リポジトリで`--uninstall`または`-Uninstall`を付けます。導入したmanagedファイルを利用先で編集した場合は、それを保持して解除を止めます。ファイルを退避してから解除してください。GitHubの必須チェック設定は別途管理者が設定します。

## Install

次のスクリプトは、リポジトリ内のWorkflowだけをユーザー共通の `~/.agents/skills` へリンクします。CapabilityとAdapterはCodexのSkill探索対象へ追加しません。

Windows:

```powershell
./scripts/install-workflows.ps1
```

macOS / Linux:

```sh
./scripts/install-workflows.sh
```

リンク先を変える場合は、Windowsでは `-Destination`、macOS / Linuxでは `--destination` を指定します。インストール後にSkillが表示されない場合はCodexを再起動し、`/skills`で確認してください。

作成したリンクを削除する場合は次を実行します。他のSkillや通常のディレクトリは削除しません。

```powershell
./scripts/install-workflows.ps1 -Uninstall
```

```sh
./scripts/install-workflows.sh --uninstall
```
