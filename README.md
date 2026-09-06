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
    |   `-- verify-code-change/
    `-- adapters/
        `-- render-archify-diagram/
            `-- SKILL.md
```

機能追加の `implement-feature`、バグ修正の `fix-bug`、現状説明の `explain-implementation` Workflowと、5つのCapabilityを収録しています。現状説明は文章を基本とし、図解を添える場合は `render-archify-diagram` Adapterからインストール済みのArchify CLIを利用します。Archify本体はこのリポジトリに同梱しません。

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
