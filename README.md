# AIとガジェットの使い方ラボ(自動生成ブログ)

AIツール・アプリ・ガジェットの活用術をテーマに、記事の生成からサイトのビルド・公開までを
GitHub Actions上で自動化するブログです。ローカルPCは不要で、無料の範囲(GitHub Actions + GitHub Pages +
Gemini API 無料枠)で運用できます。

## 大事な前提(正直な話)

- これは「自動で必ず儲かる」仕組みではありません。収益化(広告・アフィリエイト)には審査や
  アクセスの積み上げが必要で、時間がかかります。
- Google AdSense はオリジナルで価値のあるコンテンツを要求します。AI生成記事を大量に流し込むだけでは
  ポリシー違反やペナルティのリスクがあります。**申請前に人間が記事内容をざっと確認・修正することを推奨します。**
- アフィリエイトリンクを設置する場合は、日本の景品表示法に基づき「広告」「PR」等の明示が必要です。
  `config.yaml` の `affiliate_disclosure` は既にフッターに表示される仕組みになっています。

## しくみ

```
scripts/generate_post.py   # トピックを選び、Gemini APIで記事を1本生成 (content/posts/*.md)
scripts/build_site.py      # Markdown記事 -> 静的HTML (public/) にビルド。RSS/sitemap/robots.txtも生成
templates/                 # Jinja2テンプレート(HTML)
static/style.css           # デザイン
.github/workflows/publish.yml  # 毎日自動実行: 記事生成 -> コミット -> ビルド -> GitHub Pagesへデプロイ
```

## セットアップ手順(最初の1回だけ人間が行う作業)

1. **GitHubリポジトリを作る**
   - このフォルダの内容をGitHubの新しいリポジトリにpushしてください。

2. **Gemini APIキーを取得する(無料)**
   - https://aistudio.google.com/app/apikey にアクセスし、Googleアカウントでログインして
     無料のAPIキーを発行します。
   - リポジトリの `Settings > Secrets and variables > Actions > New repository secret` で
     名前 `GEMINI_API_KEY` として登録してください。

3. **GitHub Pagesを有効化する**
   - リポジトリの `Settings > Pages` で、Source を **GitHub Actions** に設定してください。

4. **`config.yaml` の `base_url` を実際のURLに書き換える**
   - 例: `https://<あなたのユーザー名>.github.io/<リポジトリ名>/`

5. **ワークフローを一度手動実行する**
   - `Actions` タブ > `Generate & Deploy` > `Run workflow` を実行すると、最初の記事が生成・公開されます。
   - 以降は毎日自動で新しい記事が1本追加されます(スケジュールは `.github/workflows/publish.yml` の
     `cron` で変更できます)。

## ローカルでの動作確認

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# APIキーなしでプレースホルダー記事を生成して確認する場合
.venv\Scripts\python scripts\generate_post.py --allow-fallback

# 実際にGemini APIで記事を生成する場合
$env:GEMINI_API_KEY = "取得したキー"
.venv\Scripts\python scripts\generate_post.py

# サイトをビルドして public/ を確認
.venv\Scripts\python scripts\build_site.py
```

`public/index.html` をブラウザで開くと確認できます。

## 固定ページ(プライバシーポリシー・運営者情報・お問い合わせ)

`content/pages/*.md` に、AdSense/アフィリエイト審査で求められることが多い固定ページを用意しています。
`config.yaml` の `site.contact_email` を実際に受信できるアドレスに書き換えてから公開してください
(現在はダミーの `contact@example.com` になっています)。

## 収益化を追加するタイミング

サイトに記事が10〜20本以上たまり、多少アクセスが出てきたら、以下を検討してください。

1. **Google AdSense**: 審査に申し込み、通過したら `config.yaml` の
   `monetization.adsense_client_id` に `ca-pub-...` を設定するだけで全ページに広告が表示されます。
2. **アフィリエイト(Amazonアソシエイト / 楽天アフィリエイトなど)**: 審査通過後、記事本文中に
   商品リンクを含める形で `generate_post.py` のプロンプトを拡張するか、記事を手動で微調整してください。

## トピックの追加・変更

`scripts/topics_seed.yaml` に記事の種トピックを追加すると、その順番で記事化されます。
すべて使い切ると、AIが新しいトピック案を自動で考えて追加します(`scripts/topics_state.json` で管理)。

## ニッチを変える場合

`config.yaml` の `site.title` / `site.description` と、`scripts/generate_post.py` の `build_prompt`
内の指示文を書き換えれば、別ジャンルのブログに転用できます。
