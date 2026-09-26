# explain-page

人に見せる頁（説明・報告・判断のHTML）を、正規レンダラーで組んで検品まで通す
フック一式のプラグイン版。正本は `TakuyaSTND/explain-page` リポジトリの `.claude/`
（このプラグインは `.claude/scripts/build_plugin.py` がそこから生成した写し）。

## 入れ方

1. `/plugin marketplace add <このリポジトリのpathまたはURL>`
2. `/plugin install explain-page@explain-page`

## 有効にする

プラグインを入れただけでは何も起きない（安全の掟①）。使いたいプロジェクトの根で
次を走らせ、そのプロジェクトの `.claude/` へ設定と雛形を置く。

```
python <プラグインの場所>/scripts/init_project.py <プロジェクトの根>
```

既にあるファイルは上書きしない。`.claude/visual-hook-policy.json` が置かれた
プロジェクトでだけ、このプラグインのフックが動き出す。

## 安全の掟

- そのプロジェクトに `.claude/visual-hook-policy.json` が無ければ、フックは
  何もせず終了する（関係ないリポジトリに影響しない）。
- そのプロジェクトの `.claude/settings.json` か `.claude/settings.local.json` に
  この仕組みを直接呼ぶ配線が既にあれば、プラグイン側は何もせず終了する
  （プラグインのフックと直接書いたフックは両方走るため、二重発火を防ぐ）。
- 共通の用語集（`glossary-shared.md`）と読みやすさ規則（`readability-rules.md`）は、
  プロジェクト側に無ければプラグイン同梱の控え・雛形を使う。

## Codexについて

このプラグインは Claude Code 専用。Codex では対象外＝`codex-build/` 側の
雛形（overlay等）を使うこと。

