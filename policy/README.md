# 共通の命名規約設定

機械で検証できる規則は`shared.json`を正本とし、利用先の設定は`local.json`に分離します。`NAMING.md`は設定から生成するagent・人向けの文書です。直接編集せず、設定を変更して再生成してください。

Workflow用Skillのinstallと規約のinstallは別々です。規約のinstallは対象のGitリポジトリに設定、生成文書、Git hook、PR用CIを追加します。Claude Code hookは任意です。

## ファイルと責務

| ファイル | 責務 |
|---|---|
| `shared.json` | 共通のtype、件名・タイトルとブランチの正規表現、summary末尾の禁止文字、利用先設定の既定値 |
| `local.json` | このリポジトリのscope許可一覧と意味判断の指示 |
| `local.example.json` | 他の利用先向けの設定例。読み込み時に自動採用しない |
| `NAMING.md` | このリポジトリ向けの生成文書 |
| `../scripts/policy/policy.py` | 設定の読み込み・検証・合成。後続のhook・CIでも利用する共通処理 |
| `../scripts/policy/generate_docs.py` | 文書生成と生成済み文書の整合確認 |
| `../scripts/policy/install.py` | Gitリポジトリへの導入・更新・解除 |

通常のスクリプトとして実装し、Skillとして公開しません。外部ライブラリ、LLM、ビルド処理、検証結果のキャッシュは使いません。Python 3.10以降で実行できます。

## 文書の生成

リポジトリのルートから実行します。WindowsとmacOS/Linuxで同じコマンドを使用できます。環境によって`python`を`python3`へ置き換えてください。

```text
python scripts/policy/generate_docs.py --shared policy/shared.json --local policy/local.json --output policy/NAMING.md
```

`--output`で指定した文書を生成・置換します。親ディレクトリは事前に用意してください。入力設定と同じパスへの出力は拒否します。設定が不正な場合は文書を書き換えず、終了コード1と理由を返します。

生成済み文書が設定と一致するか、書き換えずに確認できます。

```text
python scripts/policy/generate_docs.py --shared policy/shared.json --local policy/local.json --output policy/NAMING.md --check
```

`--output -`でUTF-8の文書を標準出力へ返します。生成ファイルもUTF-8・LFで、同じ設定からは同じバイト列を生成します。時刻や絶対パスは文書に含めません。

## install・更新・uninstall

Python 3.10以上とGitを使い、規約を導入するGitリポジトリを指定します。macOS / Linuxでは次を使います。

```sh
sh ../skill-architecture/scripts/install-policy.sh --project /path/to/project
sh ../skill-architecture/scripts/install-policy.sh --project /path/to/project --agent-hook claude
sh ../skill-architecture/scripts/install-policy.sh --project /path/to/project --uninstall
```

WindowsではPowerShell版を使います。

```powershell
../skill-architecture/scripts/install-policy.ps1 -Project C:\path\to\project
../skill-architecture/scripts/install-policy.ps1 -Project C:\path\to\project -ClaudeHook
../skill-architecture/scripts/install-policy.ps1 -Project C:\path\to\project -Uninstall
```

targetに既存の`policy/local.json`があれば保持します。ない場合は`local.example.json`を初期設定としてコピーします。共通設定、生成文書、スクリプト、workflow、`AGENTS.md`の管理参照はinstall manifestに記録します。再installでは利用先設定を使って文書を生成し、共通ファイルだけを更新します。

既存のGit `commit-msg` hookがあればバックアップして呼び出しを維持します。hook失敗時は命名規約の検証を続けずコミットを拒否します。`core.hooksPath`がリポジトリとGitディレクトリの外を指す場合、安全に解除できないためinstallを拒否します。既存のClaude設定はJSONとして読み、ほかのキーとhookを保って任意の`PreToolUse` entryを追加します。

uninstallは、このinstallが管理し変更されていないファイルだけを解除します。利用先で管理ファイルが編集または削除されている場合は、何も部分削除せず理由を返します。利用先固有の`policy/local.json`は常に保護し、install時に作った初期設定は未編集なら解除します。既存hookはinstall中の編集も含めて元の位置へ戻します。

CIではPR作成・更新・タイトルまたは本文の編集時に、PR内のコミット件名とPRメタデータを検証します。branch由来のissue番号はタイトルと本文で一致を求め、過去コミットのissue番号は現在のbranch番号へ変更しません。検証はローカルのclone先パスに依存せず、GitHub Actionsから呼び出します。必須チェックの設定はGitHub管理者が行います。

agent hookの初期対応は`git switch -c NAME [START_POINT]`、`git checkout -b NAME [START_POINT]`、`gh pr create`の明示的なタイトルと本文または本文ファイルです。シェルの複合コマンド、展開、対話形式、未対応の引数、必要な値を取得できない形式は理由を付けて拒否します。他製品や別操作のhook対応は、対象エージェントの入出力に合わせて追加します。

## 利用先設定

`local.example.json`を利用先が管理する設定ファイルへコピーし、`--local`へ明示的に渡します。共通設定を変更して利用先固有の規則を記載しないでください。

設定ファイルはUTF-8のJSONです。UTF-8 BOMも読み込めます。指定していない項目は共通設定の既定値を継承し、配列を指定した場合は既定値全体を置き換えます。scopeの各項目は個別に上書きします。

| 項目 | 指定方法 |
|---|---|
| `schema_version` | 必須。整数の`1` |
| `scope.allowed` | scope名の配列。`null`は許可一覧による制限なし、`[]`はscopeを指定不可 |
| `scope.required` | `true`ならすべてのtypeでscope必須。既定値は`false` |
| `scope.required_for_types` | scope必須にするtypeの配列。既定値は`[]`。共通設定にないtypeは指定不可 |
| `permanent_branches` | 命名検証を免除するブランチ名の完全一致一覧。既定値は`main`と`master`。`[]`で例外なし |
| `guidance` | 意味の判断が必要な指示の配列。機械判定には使わず、生成文書へ記載する |

scope必須条件は`required`と`required_for_types`のいずれかを満たす場合に適用します。scope指定不可とscope必須の組み合わせは拒否します。このリポジトリではscopeを一律に必須にせず、変更内容に応じた選択を`guidance`で指示しています。Skillを追加・改名した場合は`local.json`の許可一覧も更新してください。

`--local`を省略すると共通設定の既定値だけを使います。明示した設定ファイルが見つからない場合は失敗します。未知のキー、JSONキーや配列要素の重複、不正な型、未対応のバージョンは拒否します。共通のtypeや正規表現を利用先設定で上書きすることはできません。

## 共通設定

共通設定の`types`は名前と説明の一覧です。コミット・PR・ブランチで同じ一覧を使用します。`subject_pattern`と`branch_pattern`はPython正規表現で、`{types}`だけをエスケープ済みのtype一覧へ置き換えます。判定時は全文一致を使用します。

件名・タイトルは`type`、`scope`、`breaking`、`summary`、`issue`、ブランチは`type`、`issue`、`no_issue`、`description`という名前付きグループを持ちます。これらは後続の補完処理との契約です。summary末尾の禁止文字とscope必須条件は正規表現の評価に加えて確認します。

文書は形式の説明と、設定から展開した正規表現・条件を載せます。共通設定の正規表現を変えて形式自体を変更する場合は、文書生成の説明も同時に見直してください。意味判断の指示やissue参照を扱う際の原則は文書に残します。

## 検証

```text
python -B -m unittest discover -s tests/policy -v
```

設定の正常系・異常系、既定値と上書き、入力ファイルの保持、文書の再現性、設定との整合、CLIの診断を確認します。
