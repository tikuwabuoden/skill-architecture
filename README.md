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
    |   |-- create-github-issue/
    |   |   `-- SKILL.md
    |   |-- explain-implementation/
    |   |   `-- SKILL.md
    |   |-- fix-bug/
    |   |   `-- SKILL.md
    |   `-- implement-feature/
    |       `-- SKILL.md
    |-- capabilities/
    |   |-- analyze-codebase/
    |   |-- assess-change-impact/
    |   |-- draft-issue/
    |   |-- implement-code-change/
    |   |-- plan-code-change/
    |   |-- render-markdown/
    |   `-- verify-code-change/
    `-- adapters/
        |-- github-issues-gh/
        |   `-- SKILL.md
        `-- render-archify-diagram/
            `-- SKILL.md
```

## Included skills

### Workflow

- `create-github-issue`: 読み取り、Issue本文の生成、重複確認、明示承認を経てGitHub Issueを1件作成する
- `implement-feature`: 要求の具体化から実装と検証まで、機能追加の一連の作業を進める
- `fix-bug`: 不具合の再現と原因調査から修正、回帰検証までを進める
- `explain-implementation`: 既存コードを調査し、現在の仕組みと処理の流れを根拠付きで説明する

### Capability

- `draft-issue`: ユーザーの意図、根拠、リポジトリ規約から開発Issueの型付きデータを作る
- `analyze-codebase`: 実装経路、制約、既存パターン、関連テストを調査する
- `assess-change-impact`: コード変更がインターフェース、データ、設定、テスト、文書、運用へ与える影響を調査する
- `plan-code-change`: 要求と調査結果から、実装方針、機能単位の実施順、検証方法を決める
- `render-markdown`: JSONを指定されたスキーマで検証し、テンプレートから再現可能なMarkdownを生成する
- `implement-code-change`: 合意済みの方針に基づいて、コード、テスト、文書へ変更を適用する
- `verify-code-change`: 実装結果について、要求の充足、意図しない差分、回帰の有無を検証する

### Adapter

- `github-issues-gh`: インストール済みGitHub CLIでリポジトリ、ラベル、Issue候補を読み取り、承認済みのIssueを1件作成する
- `render-archify-diagram`: 仕様JSONをインストール済みのArchify CLIでHTML図へ変換し、成果物と診断を返す

Archify本体はこのリポジトリに同梱しません。

## Intermediate JSON

Skill間の受け渡しや文書・図の変換に使う中間JSONは、一時ファイルも含めディスクへ保存しません。メモリ上で保持し、コマンドにはUTF-8の標準入力で渡します。MarkdownやHTMLなどの成果物は保存できます。既存のSchemaや設定、固定のテスト資産、依頼された実装の一部となるJSONファイルはこの制約の対象外です。

`render-markdown`のデータ入力は`--data -`のみ対応します。従来のJSONファイル入力は使用できません。

`render-archify-diagram`は、標準入力に対応し、内部でも中間JSONを保存しないArchifyだけを使用します。現在確認しているArchifyはファイル入力と内部の仕様JSONコピーが必要なため、HTML図解を生成できません。`explain-implementation`はその理由と文章説明を返し、図解が必須の場合は未完了として報告します。

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
