# line-group-agent

> 🇬🇧 English: [README.md](README.md)

> LINE のグループに入り、メンションされた時だけ Claude で答える LINE bot。

line-group-agent は LINE 公式アカウントの裏で動く小さな server です。アカウントを
グループに入れておくと、誰かがメンションした時だけ、最近の会話を読み、web やグループの
過去の発言を調べて、短く答えます。それ以外の時は黙っています。

- **メンションされた時だけ答える。** LINE が「この bot 宛て」と印を付けたメンションだけを
  拾います。本文に bot の名前が書いてあるだけでは反応しません。
- **グループの話を覚えている。** 許したグループの text の発言は全部ローカルの記録に追記
  するので、「ホテルの話どうなったっけ」に後から答えられます。
- **調べて答える。** web 検索と web ページの読み込み (Claude API の server 側の道具) と、
  グループ自身の記録の検索。
- **候補をカードで見せる。** 候補を 2 件以上並べる時は、横にスワイプするカードの束
  (LINE の Flex Message の carousel) で送れます。候補ごとに、名前・値段・短い一言・
  あれば画像・ページへ飛ぶ「開く」ボタン。最大 10 枚。[カード](docs/reference/cards.md)
  を見てください。
- **送るのは決めた所だけ。** model が `<reply>…</reply>` の中に書いた文だけがグループに
  送られます。考えの途中は送られません。
- **月の予算の中で動く。** 毎回の額を API の usage から数えます。API を呼ぶ前に
  「今月の額 + 1 回の最大の見積もり」が上限を超えないか確かめ、超えるなら決まった文だけを
  返します。
- **グループの発言はデータとして扱う。** 発言は封筒に入れて model に渡し、指示としては
  読ませません。予約・支払い・グループの外へ送る道具は持っていません。

## 動き

```
LINE グループ ──▶ LINE Platform ──https──▶ あなたの HTTPS の入口 ──▶ line-group-agent (127.0.0.1:8790)
                                                                     │  POST /line/webhook
                                                                     │  1. 大きさの上限・署名の確認・すぐ 200
                                                                     │  2. 許したグループなら発言を記録
                                                                     │  3. メンションなら Claude API へ ──▶ web 検索 / web fetch
                                                                     │                               ├─▶ search_history (ローカルの記録)
                                                                     │                               └─▶ show_cards (候補をカードで)
                                                                     └─ 4. reply (文のあとにカード。token が切れていたら push)
```

- server は loopback でだけ待ち受けます。LINE から届く HTTPS の入口 (reverse proxy・
  tunnel・[Tailscale Funnel](https://tailscale.com/kb/1223/funnel) など) は自分で用意します。
- event は webhook が 200 を返した後に 1 つずつ処理するので、LINE を待たせません。
- 残す物は全部、自分で決めた 1 つの state の folder に入ります ([書く file](#書く-file))。

## 要る物

- macOS か Linux と [uv](https://docs.astral.sh/uv/) (Python 3.12 も uv が入れる)。
  [go-task](https://taskfile.dev/) は任意
- Messaging API の channel を持つ LINE 公式アカウント
  ([LINE Developers Console](https://developers.line.biz/console/))
- Claude API の key ([Claude Console](https://platform.claude.com/))
- agent の loopback の port へ転送する HTTPS の入口

## はじめかた

```bash
git clone https://github.com/Synforger/line-group-agent.git
cd line-group-agent
task setup                      # uv sync --python 3.12
```

1. 秘密を 1 つずつ別の file に置き、自分だけが読めるようにします (`chmod 600`):
   Claude API の key、Messaging API の channel の channel secret と channel access token。
2. [`configs/config.example.json`](configs/config.example.json) を repo の外に写し、
   `*_file` の設定を 3 つの file に向け、`state_dir` を決め、人格の file を書きます
   (例は [`configs/persona.example.md`](configs/persona.example.md))。相対 path は
   設定 file の在る folder から読みます。
3. 起動します:

   ```bash
   uv run line-group-agent --config /path/to/config.json
   ```

4. LINE Developers Console で webhook の URL を `https://<your-host>/line/webhook` にし、
   **Webhook の利用** を on、グループへの参加を許可、自動の応答メッセージを off にします。
5. アカウントをグループに招待します。agent はグループの ID を 1 行だけ log に出します
   (`join: joined a group that is not allowed: group_id=C…`)。その ID を
   `allowed_group_ids` に足して再起動すると、以後グループでメンションすれば答えます。

### 常駐させる

常駐させる時は、package を専用の環境に入れ、入った実行 file を直に呼びます:

```bash
uv sync --python 3.12 --no-dev
/path/to/line-group-agent/.venv/bin/line-group-agent --config /path/to/config.json
```

agent は設定を設定 file とそこに書かれた file からだけ取ります。API の key・宛先・proxy・
tracing は全部明示で渡すので、`ANTHROPIC_API_KEY`・`ANTHROPIC_BASE_URL`・`HTTPS_PROXY` の
ような環境変数は効きません。作業 folder にも頼らないので、launchd や systemd の定義には
この 1 行だけで足ります。定義の例は [`docs/setup/`](docs/setup/README.md) に
あります。

## 費用

agent は使った額を数えますが、料金は調べません。料金の表から `prices_usd` に書きます。
設定の例には 2026-11-18 時点の Claude Haiku 5.5 の料金を入れてあります:

| 項目 | 料金 (USD) |
|---|---|
| 入力 / 出力 (prompt が 10 万 token 以下) | 100 万 token あたり $0.10 / $0.50 |
| 入力 / 出力 (prompt が 10 万 token 超) | 100 万 token あたり $0.50 / $2.50 |
| cache の書き込み (5 分) / 読み出し | 100 万 token あたり $0.125 / $0.01 |
| web 検索 | 1,000 回あたり $10 |
| web fetch | 増えた token 以外は無料 |

出典: [pricing](https://platform.claude.com/docs/en/about-claude/pricing)・
[web search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool)・
[web fetch tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-fetch-tool)。

予算の守り方:

- `budget.monthly_limit` は `budget.currency` の額で、`currency_per_usd` でドルを換算
  します。月は機械の現地時刻で数え、替わったら 0 から。
- メンションに答える前に、1 回の最大の額を見積もります: 道具の往復の全部の要求
  (`max_tool_rounds + 1` 回) が、それぞれ `estimated_input_tokens_per_request` の prompt と
  `max_tokens` いっぱいの答えと、`max_uses` の分の web 検索を使った場合。今月の額に足して
  上限を超えるなら API を呼ばず、`budget.exhausted_text` を返します。
- 見積もりは守りで、請求ではありません。Claude Console でも key の workspace に額の上限を
  置いてください。
- 返事は LINE の reply token で送り、無料です。model の答えが token の寿命 (約 1 分) より
  遅れた時は push で送り直し、これはアカウントの月の送信数に数えられます。

## 書く file

全部 `state_dir` の下:

| Path | 中身 |
|---|---|
| `groups/<groupId>/messages.jsonl` | グループの text の発言全部と、bot が送った返事 (`from_bot` の印付き。カードを付けた返事は、末尾にその名前を並べた 1 行が付く)。1 行 1 発言。追記だけ |
| `conversations/<tab_name>.jsonl` | model に送った物と model の答え。chat の client が読むだけのタブとして見せる |
| `spend.json` | 今月の額: `{"month", "spent", "limit", "currency", "updated_at"}`。毎回全体を書き直す |

形は [`docs/reference/files.md`](docs/reference/files.md) にあります。

## 文書

- 設定の手順 (LINE の channel・常駐): [`docs/setup/`](docs/setup/README.md)
- 設定の全項目と file の形: [`docs/reference/`](docs/reference/README.md)
- 困った時: [`docs/troubleshooting/`](docs/troubleshooting/README.md)
- 開発に加わる人へ: [`docs/internals/`](docs/internals/README.md)

## License

Apache-2.0 ([`LICENSE`](LICENSE))。依存は
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)、脆弱性の報告は
[`SECURITY.md`](SECURITY.md) へ。
