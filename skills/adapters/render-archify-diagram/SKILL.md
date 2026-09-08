---
name: render-archify-diagram
description: インストール済みArchify CLIを使い、指定された仕様JSONをHTML図へ描画・検証して成果物と診断を返す。図の内容と出力条件が決まっているときに使う。コード調査、説明内容の選択、図の意味の設計には使わない。
---

# Render Archify Diagram

外部ツールのArchify CLIへの入出力を扱う。他のSkillを読み込んだり呼び出したりしない。

## Input

- 図の種類: `architecture`、`workflow`、`sequence`、`dataflow`、`lifecycle`
- インストール済みArchifyのルートパス（不明なら下記の方法で確認）
- そのバージョンのスキーマに従う仕様JSONのパス
- HTML出力先と品質: `standard`または`showcase`

呼び出し元が仕様を作る際の形式資料は、ツール内の`schemas/<type>.schema.json`、`schemas/common.schema.json`と`examples/`の対応するJSON。新規workflowは対応バージョンでschema v2を使う。品質指定はJSONの`meta.quality_profile`と一致させる。

## CLI access

指定されたルートを優先する。未指定ならユーザー共通の`~/.agents/skills/archify`、`$CODEX_HOME/skills/archify`（未設定なら`~/.codex/skills/archify`）で`bin/archify.mjs`の存在を確認する。複数候補で選択が曖昧なら候補を返す。作業ディレクトリやユーザー名を固定しない。

Node.jsとCLIの存在、インストール済みCLIの`--help`で必要なコマンドを確認する。不足や非対応は呼び出し元へ返し、自動インストール・更新しない。

## Operation

呼び出し元から指定された入力・出力を絶対パスに解決する。入力JSONを変更しない。出力先が既存ファイルなら、置換が依頼されているかを確認し、未指定なら出力先の再指定を求める結果を返す。

最終成果物は描画と検証をまとめて行うCLIの`deliver`で生成する。次はプレースホルダーを実際のパスと引数に置き換えて実行する例。

```text
node "<archify-root>/bin/archify.mjs" deliver <type> "<input.json>" "<output.html>" --quality <quality> --json
```

終了コード、標準出力のJSON、標準エラーを取得して返す。CLIが必要とする修正は診断として返し、Adapter自身は修正方針を判断せず、仕様変更・再試行を行わない。これはCLI自身の内部検証を妨げない。

非ゼロ終了を成功と扱わない。失敗時に出力先へ既存HTMLが残っていても今回の成果物として返さない。ブラウザを開く`--open`や常駐する`preview`はこの操作に含めない。

## Result

- 実行したCLIと入力・出力の絶対パス
- 終了コード、標準エラー、CLIの検証結果と診断
- 成功時のHTMLパスと、CLIが返した仕様・成果物のハッシュ等のreceipt
- ツール不足、入力不足、非対応、生成失敗の区別
- ブラウザ確認と見た目の確認は未実施（機械検証の成功とは別）
