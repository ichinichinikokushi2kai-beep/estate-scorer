# GitHub に上げて Actions で動かす手順

## 前提

- GitHub アカウントがあること
- リポジトリを新規作成するか、既存の空リポジトリを用意すること
- **config.yaml は .gitignore に入っていること**（プッシュされない）

---

## ステップ 1: Git の準備とリポジトリの初期化

### 1-1. Git が入っているか確認

PowerShell で：

```powershell
git --version
```

- バージョンが表示されれば OK
- 「認識されません」と出る場合は [Git for Windows](https://git-scm.com/download/win) をインストールし、**PowerShell を開き直して**再度確認

### 1-2. まだリポジトリになっていない場合

プロジェクトフォルダで：

```powershell
cd "c:\Users\zawa_\OneDrive\Desktop\my_3rd_app"
git init
```

すでに `git init` 済みなら不要。

### 1-3. 初回コミット（まだ何もコミットしていない場合）

```powershell
git add .
git status
```

- **config.yaml が一覧に出ていなければ** OK（.gitignore が効いている）
- 出ていたら .gitignore に `config.yaml` が入っているか確認

```powershell
git commit -m "Initial commit: SUUMO batch"
```

---

## ステップ 2: GitHub にリポジトリを作成してプッシュ

### 2-1. GitHub でリポジトリを作成

1. [GitHub](https://github.com) にログイン
2. 右上 **+** → **New repository**
3. **Repository name**: 例 `my_3rd_app`（任意）
4. **Public** または **Private** を選択
5. **Add a README file** は**チェックしない**（既に手元にコードがあるため）
6. **Create repository** をクリック

### 2-2. リモートを追加してプッシュ

作成直後の画面に「…or push an existing repository from the command line」と出ています。その 2 行を実行します（URL はあなたのリポジトリに合わせて書き換え）。

```powershell
git remote add origin https://github.com/<あなたのユーザー名>/<リポジトリ名>.git
git branch -M main
git push -u origin main
```

- 初回プッシュ時に **GitHub のログイン**を求められたら、ブラウザまたはトークンで認証する
- ユーザー名・リポジトリ名は、作成したリポジトリの URL の部分（例: `https://github.com/tanaka/my_3rd_app` → `tanaka` と `my_3rd_app`）

---

## ステップ 3: Secrets の登録

Actions でメールを送るために、**リポジトリの Secrets** に次の 6 つを登録します。

### 3-1. 開く場所

1. GitHub でそのリポジトリを開く
2. **Settings** タブをクリック
3. 左メニュー **Secrets and variables** → **Actions** をクリック
4. **New repository secret** をクリックして、以下を **1つずつ** 追加

### 3-2. 登録する Secret（名前は一字違いに注意）

| Name（名前） | Value（値） | 例 |
|--------------|------------------|
| `SMTP_HOST` | Gmail の SMTP サーバー | `smtp.gmail.com` |
| `SMTP_PORT` | ポート番号 | `587` |
| `SMTP_USER` | 送信に使う Gmail アドレス | `your_email@gmail.com` |
| `SMTP_PASS` | その Gmail の**アプリパスワード**（16文字） | （発行したパスワード） |
| `FROM_EMAIL` | 差出人アドレス（通常は SMTP_USER と同じ） | `your_email@gmail.com` |
| `TO_EMAILS` | 送信先をカンマ区切りで1つにまとめる | `aaa@gmail.com,bbb@gmail.com` |

- **TO_EMAILS** だけは「複数アドレスをカンマでつなげた1つの文字列」にします。  
  例: `ichinichinikokushi2kai@gmail.com,other@gmail.com`
- 名前は **大文字・小文字を正確に**（`SMTP_HOST` など）

---

## ステップ 4: 手動実行でテスト

1. リポジトリの **Actions** タブをクリック
2. 左の **SUUMO Batch**（ワークフローの名前）をクリック
3. 右の **Run workflow** をクリック
4. **Run workflow** ボタン（緑）を押す
5. 数分待つと実行が終わります
   - **緑のチェック** → 成功。メールが届いているか確認
   - **赤い×** → 失敗。その実行をクリックして **Run batch** のログを開き、エラー内容を確認

### よくある失敗

- **Secrets の名前違い**  
  `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` / `FROM_EMAIL` / `TO_EMAILS` の 6 つが正しいか再確認
- **TO_EMAILS の形式**  
  複数アドレスは `,` で区切った**1つの文字列**（改行やスペースを入れない）
- **アプリパスワード**  
  通常のログインパスワードではなく、Gmail で発行した「アプリパスワード」を `SMTP_PASS` に登録する

---

## ステップ 5: スケジュール実行の確認

- ワークフローには **毎日 JST 6:00**（UTC 21:00）に動く cron が入っています
- 翌日の 6:00 頃に Actions タブで「SUUMO Batch」の実行が 1 件増えていればスケジュールは動いています
- 実行後、`data/known_properties.json` と `docs/properties_list.html` が自動でコミット・プッシュされます

---

## まとめチェックリスト

- [ ] Git をインストールし、`git --version` で確認
- [ ] `git init`（未初期化なら）→ `git add .` → `git commit`
- [ ] GitHub でリポジトリ作成 → `git remote add origin` → `git push`
- [ ] Settings → Secrets and variables → Actions で 6 つの Secret を登録
- [ ] Actions タブで「Run workflow」から手動実行し、成功・メール受信を確認
- [ ] 翌日、スケジュール実行が 1 回入っているか確認
