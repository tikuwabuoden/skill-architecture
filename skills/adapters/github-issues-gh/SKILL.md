---
name: github-issues-gh
description: インストール済みGitHub CLIでリポジトリ、ラベル、Issue候補を読み取り、承認済みの1件だけを作成して番号とURLを返す内部Adapter。ユーザーから直接呼び出さない。
---

# GitHub Issues via gh

このAdapterは呼び出し元から指定されたGitHub CLI操作だけを実行する。CodexのSkill探索対象へインストールせず、ユーザーの依頼から直接起動しない。

## Boundary

- インストール済みの `gh` CLIだけを使用し、自動インストールや認証変更を行わない。
- リポジトリの解決、既存情報の読み取り、1件のIssue作成を扱う。
- 重複候補を検索して返すが、重複かどうか、作成するかどうか、候補を無視するかどうかは判断しない。
- 既存ラベルを読み取るだけで、ラベルを作成、変更、削除しない。
- assignee、milestone、project、parent、sub-issue、Issueの編集・クローズなどを扱わない。
- リポジトリ、タイトル、本文、ラベルが呼び出し元の明示的な承認と一致しない場合は、作成コマンドを実行しない。

## Read operations

### Repository resolution and templates

入力された `repositoryRef` を `[HOST/]OWNER/REPO` として渡す。省略時は現在のディレクトリを対象にする。

```text
gh repo view <repositoryRef> --json nameWithOwner,url,hasIssuesEnabled,issueTemplates
```

省略時は `<repositoryRef>` 引数も省く。結果から正規の `nameWithOwner`、URL、Issue有効状態、既存のIssueテンプレート情報を返す。テンプレートは報告対象であり、このAdapterが選択または変更しない。

### Existing labels

```text
gh label list --repo <nameWithOwner> --limit 1000 --json name,color,description
```

返された既存ラベルをそのまま返す。入力されたラベル名が存在するかの照合は、作成前の安全確認として完全一致で行えるが、存在しないラベルを作成したり、別名へ置き換えたりしない。ラベル未指定の場合も作成入力では空配列として扱う。

### Duplicate candidates

```text
gh issue list --repo <nameWithOwner> --state all --search "in:title <title>" --limit 30 --json number,title,state,url
```

`<title>` は1つの引数としてGitHub検索へ渡し、シェル展開を行わない。検索結果のIssue番号、タイトル、状態、URL、使用した検索文字列を返す。候補の順位付け、同一性判定、作成停止の判断は行わない。

## Create operation

作成入力は、作成対象と承認を別々に持つ。

```json
{
  "mutation": {
    "repository": "OWNER/REPO",
    "title": "Issue title",
    "body": "exact body\n",
    "labels": ["existing-label"]
  },
  "authorization": {
    "confirmed": true,
    "repository": "OWNER/REPO",
    "title": "Issue title",
    "body": "exact body\n",
    "labels": ["existing-label"]
  }
}
```

次のすべてを事前に確認する。

1. `authorization.confirmed` が明示的な `true` である。
2. `mutation` と `authorization` のリポジトリ、タイトル、本文、ラベル配列が完全一致する。
3. リポジトリが解決結果の正規名と一致する。
4. 指定ラベルが既存ラベルの名前と完全一致する。

1つでも満たさなければ、`gh issue create` を実行せず診断を返す。承認をこのAdapterが推測したり、本文・タイトル・ラベルを補正したりしない。

確認を通過したときだけ、本文を一時ファイルへUTF-8で書き、次の1回のコマンドを実行する。ラベルは指定された順序で必要な回数だけ `--label` を繰り返す。ラベルが空の場合はフラグを付けない。

```text
gh issue create --repo <nameWithOwner> --title <title> --body-file <temporary-body-file> [--label <label>]...
```

タイトル、本文、ラベルはシェル文字列連結せず、引数または一時ファイルとして安全に渡す。`--web`、対話プロンプト、テンプレート、添付、その他の作成オプションは使わない。

## Result and failure handling

- 成功時は、`gh issue create` が出力したIssue URLから `number` を取得し、`number` と完全な `url`、正規リポジトリ名を返す。
- 終了コードが非ゼロの場合は作成を再試行しない。要求がGitHubへ到達した可能性がある場合は `ambiguous` として、同じタイトルの手動確認を促す診断を返す。
- 成功終了でもURLを取得できない場合は結果を確定せず `ambiguous` とし、再試行しない。
- 認証、権限、入力、ネットワーク、GitHub CLI未導入などの読み取り失敗は、コマンド、終了コード、標準エラーを含む診断として返す。作成失敗を成功扱いにしない。
- Adapterは失敗後に同じ作成コマンドを盲目的に繰り返さない。再開時は呼び出し元が手動確認の結果を受けて新しい判断を渡す。
