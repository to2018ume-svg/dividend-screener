# dividend-screener

S&P500の配当株をスクリーニングして月1回メールで通知するツール。

## スクリーニング条件（デフォルト）

| 指標 | 条件 |
|---|---|
| 配当利回り | 2.5% ～ 10.0% |
| 連続配当年数 | 5年以上 |
| 配当性向 | 75%以下 |
| 負債資本比率 (D/E) | 2.0以下 |
| 流動比率 | 1.0以上 |

条件は環境変数 (`MIN_YIELD`, `MIN_STREAK` など) で上書き可能。

## セットアップ

```bash
pip install -r requirements.txt
cp .env.example .env   # メール設定を記入
python screener.py
```

## GitHub Actions（自動実行）

毎月1日 09:00 JST に自動実行されます。  
以下の Secrets をリポジトリに登録してください。

| Secret名 | 内容 |
|---|---|
| `EMAIL_FROM` | 送信元メールアドレス |
| `EMAIL_TO` | 送信先メールアドレス（複数の場合はカンマ区切り） |
| `EMAIL_PASS` | Gmailアプリパスワード |
| `SMTP_HOST` | SMTPサーバー（デフォルト: `smtp.gmail.com`） |
| `SMTP_PORT` | SMTPポート（デフォルト: `587`） |

### Gmail アプリパスワードの取得手順

1. Googleアカウント → セキュリティ → 2段階認証をオン
2. 「アプリパスワード」を検索 → 新規作成
3. 生成された16桁のパスワードを `EMAIL_PASS` に設定

### 手動実行

GitHub → Actions → "Monthly Dividend Screener" → "Run workflow"

## 出力

- メールでHTMLレポートを送信
- `results.csv` をArtifactとして90日間保存（GitHub Actions実行時）

## ファイル構成

```
dividend-screener/
├── screener.py                    # メインスクリプト
├── requirements.txt
├── .env.example                   # 環境変数テンプレート
└── .github/workflows/monthly.yml  # GitHub Actions定義
```
