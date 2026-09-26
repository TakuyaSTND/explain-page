from __future__ import annotations

"""explain-page 公開版のブランド値（2026-09-25 新設・E2）。

開発元リポジトリの `.claude/hooks/visual/branding.py` と同じ名前・同じ型の
フィールドだけを持つ、公開リポジトリ向けの版。
`export_public.py` が開発元の `.claude/hooks/visual/branding.py` の代わりに
このファイルを `<DIR>/.claude/hooks/visual/branding.py` として書き出す。

⚠️フィールドの一覧は開発元の正本と1対1で揃える。増減したら export_public.py の
検査（test_export_public.py の branding 一致確認）が壊れる。
"""

# 表示・ディレクトリ名・環境変数名などに使う、この配布物自身の名前。
PRODUCT_NAME = "explain-page"

# %TEMP% 配下などに作る、この道具専用の置き場のフォルダ名。
ARTIFACT_DIR_NAME = "explain-page"

# Claude Code のプラグイン名・マーケットプレイス名（`/plugin install <name>@<marketplace>`）。
MARKETPLACE_NAME = "explain-page"

# LICENSE・README・plugin.json・marketplace.json にだけ出す作者表記。
AUTHOR_NAME = "TakuyaSTND"

# GitHub の `owner/repo`。marketplace.json の source・README の入れ方に使う。
REPO_SLUG = "TakuyaSTND/explain-page"

# プラグインの説明文（plugin.json の description）。
PLUGIN_DESCRIPTION = (
    "人に見せる頁（説明・報告・判断のHTML）を正規レンダラーで組んで検品まで通す"
    "フック一式。エージェントが書いた頁を、用語ホバー・図・根拠つきで検品する。"
)

# マーケットプレイスの説明文（marketplace.json の metadata.description）。
MARKETPLACE_DESCRIPTION = "explain-page 本体のマーケットプレイス（プラグイン1本のみ）。"

# 「毎回聞かず常に頁を出す／出さない」を切り替える環境変数名。
ENV_MODE = "EXPLAIN_PAGE_MODE"

# 公開版はレガシーの別名環境変数を持たない（1本化）。
LEGACY_ENV_OFF = None
LEGACY_ENV_MIN = None
LEGACY_ENV_BLOCKS = None

# 尋問の回答集めに使う、利用者の機械ごとの道具の名前（指示文の例外の1行に出す）。
# None なら、その例外の文を出さない（公開版はこの道具を持たない人が使う）。
QA_PAGE_TOOL = None
