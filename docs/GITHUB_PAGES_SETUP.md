# GitHub Pages で「全物件一覧」を公開する手順

メールの「全物件一覧（条件ポイント降順）」リンクをクリックしたときに、  
`docs/properties_list.html` を表示するために GitHub Pages を有効にします。

---

## 1. リポジトリを GitHub にプッシュしておく

- まだなら `git push` でリモートに反映しておく
- バッチ実行で `docs/properties_list.html` と `data/known_properties.json` がコミット・プッシュされる想定

---

## 2. GitHub で Pages を有効にする

1. GitHub でリポジトリを開く
2. 上部メニュー **Settings** をクリック
3. 左メニューの **Pages** をクリック（"Code and automation" の下）
4. **Build and deployment** の **Source** で次を選ぶ：
   - **Deploy from a branch** を選択
   - **Branch**: `main`（または使っているブランチ）
   - **Folder**: **/docs** を選択
   - **Save** をクリック

---

## 3. 公開URLを確認する

数分待つと、次のURLでサイトが公開されます。

```
https://<あなたのGitHubユーザー名>.github.io/<リポジトリ名>/properties_list.html
```

- **注意**: フォルダに `/docs` を選んだ場合、`docs` フォルダの中身がサイトの**ルート**になります。  
  そのため URL に `docs` は入らず、**`/properties_list.html`** だけでアクセスします。
- 例: ユーザー名が `tanaka`、リポジトリ名が `my_3rd_app` なら  
  `https://tanaka.github.io/my_3rd_app/properties_list.html`

ブラウザでこのURLを開き、全物件一覧が表示されればOKです（初回はバッチ未実行で空のページでも構いません）。

---

## 4. メールのリンク先 URL を設定する

メール本文に載せる「全物件一覧」のリンクを設定します。

**GitHub Actions で動かす場合（必須）:**

1. リポジトリの **Settings** → **Secrets and variables** → **Actions** を開く
2. **New repository secret** をクリック
3. **Name**: `PROPERTIES_LIST_PAGE_URL`（名前は正確に）
4. **Value**: `https://<あなたのGitHubユーザー名>.github.io/<リポジトリ名>/properties_list.html`
   - 例: `https://ichinichinikokushi2kai-beep.github.io/estate-scorer/properties_list.html`
5. **Add secret** をクリック

**ローカルでメール送信する場合（config.yaml）:**

```yaml
properties_list_page_url: https://<あなたのGitHubユーザー名>.github.io/<リポジトリ名>/properties_list.html
```

---

## 5. 動作の流れ

1. バッチ（`run_batch.py`）が実行され、`docs/properties_list.html` が生成される
2. ワークフローで `docs/properties_list.html` がコミット・プッシュされる
3. GitHub Pages は `main` の `/docs` を参照しているので、更新が自動で反映される
4. メールの「全物件一覧」リンク（`properties_list_page_url`）をクリックすると、そのページが開く

---

## うまく表示されないとき

- **404 になる**: Source の Branch / Folder が正しいか確認（Branch: main, Folder: /docs）
- **古い内容のまま**: プッシュ直後は数分かかることがある。最新コミットに `docs/properties_list.html` が含まれているか確認
- **リポジトリがプライベート**: 無料プランでは Pages はパブリックリポジトリのみ。プライベートの場合はリポジトリをパブリックにする必要あり
