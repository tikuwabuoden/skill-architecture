---
name: render-markdown
description: Workflowから受け取ったJSONを指定されたスキーマで検証し、指定されたテンプレートから再現可能なMarkdownを生成する内部Capability。文書の用途や形式は決定せず、ユーザーから直接呼び出さない。
---

# Render Markdown

このCapabilityはWorkflowが内部Skillとして読み込んで使う。CodexのSkill探索対象へインストールせず、ユーザーの依頼から直接起動しない。

Workflowが所有するスキーマ、テンプレート、構造化データを受け取り、検証済みのMarkdownへ機械的に変換する。実装計画、Issueなどの文書用途や項目構成を自身に持たない。

## Input

- UTF-8のJSON Schemaファイル
- UTF-8のMarkdownテンプレート
- スキーマを満たすJSONデータ。JSONファイルまたは標準入力で渡せる
- Markdownの出力先。後続処理へ本文を渡す場合は標準出力を指定できる
- 既存ファイルを置換する場合は、その操作が依頼範囲に含まれること

スキーマ、テンプレート、データ内容、出力先、生成するタイミングは呼び出し元が決める。呼び出し元に永続的なJSONファイルの作成を要求しない。

使用できるスキーマキーワードとテンプレート構文は、実行時に[references/template-syntax.md](references/template-syntax.md)を最後まで読む。

## Rendering

1. スキーマとテンプレートを絶対パスに解決し、どちらも変更しない。
2. 呼び出し元から受け取った内容を、スキーマに合うJSONデータとして用意する。テンプレートがMarkdown構文を持ち、データは内容だけを持つようにする。
3. `scripts/render_markdown.py`へスキーマ、テンプレート、JSONデータ、出力先を渡す。モデル自身の編集で検証やMarkdown生成を再実装しない。
4. 入力、スキーマ、テンプレートの診断が返った場合は出力を採用せず、呼び出し元が修正できる診断を返す。同じ入力による再実行を繰り返さない。
5. 出力先が既存ファイルの場合は、置換が依頼範囲に含まれるときだけ`--overwrite`を使う。そうでなければ停止して出力先の変更または置換の判断を返す。

JSONファイルを使う場合:

```text
python scripts/render_markdown.py --schema <schema.json> --template <template.md> --data <values.json> --output <result.md>
```

JSONを標準入力から渡す場合は`--data -`、後続処理へMarkdown本文を渡す場合は`--output -`を使う。

## Boundaries

- 文書の目的、項目、見出し、図の位置、内容、公開先を決めない。
- 呼び出し元が渡したスキーマまたはテンプレートを入力に合わせて暗黙に変更しない。
- テンプレートにない構造を独断で追加または並べ替えない。
- 生成したMarkdownの保存後の利用、外部サービスへの送信、コミットは行わない。
- 他のCapabilityまたはAdapterを参照しない。

## Result

- 生成したMarkdown本文または出力ファイルの絶対パス
- 使用したスキーマとテンプレートの絶対パス
- 置換の有無
- 生成できなかった場合は入力、スキーマ、テンプレートのどこを修正すべきか分かる診断
