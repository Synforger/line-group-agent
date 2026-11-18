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
- **グループごとに 1 本の会話を続ける。** メンションのたびに、前の自分の番からのグループの
  発言を足して、そのグループの会話を続けます。bot は自分の前の答えを踏まえて話せます。
  会話が長くなったら要約を作り、要約から続けます。
  [続いている会話](docs/reference/conversation.md)を見てください。
- **調べて答える。** web 検索と web ページの読み込み (Claude API の server 側の道具) と、
  グループ自身の記録の検索。
- **候補をカードで見せる。** 候補を 2 件以上並べる時は、横にスワイプするカードの束
  (LINE の Flex Message の carousel) で送れます。候補ごとに、名前・値段・短い一言・
  あれば画像・ページへ飛ぶ「開く」ボタン。最大 10 枚。[カード](docs/reference/cards.md)
  を見てください。
- **投票と日程合わせ。** 「投票して」と頼むと、選択肢ごとのボタンが付いたカードを送ります。
  ボタンを押すと model を呼ばずに票が数えられ、グループには何も流れません。日程合わせは、
  各自が都合のいい日をぜんぶ押せます。[グループの道具](docs/reference/group-tools.md)を
  見てください。
- **旅の予定表と割り勘。** グループに予定表が 1 つあり、頼まれたら bot が読み、書き直します
  (前の版は 5 つまで残る)。「itinerary」だけのメンションには、費用なしで予定表をそのまま返します。
  割り勘は code で正確に計算し、精算の回数が最少の一覧を返します。
- **写真と場所。** 前の自分の番より後に送られた写真の新しい分を model に見せます。共有された
  位置は記録に残り、bot も場所を地図のメッセージで送れます。質問の下にタップで答えるボタンを
  付けたり、新しく入った人に一言かけたりもできます。
- **送るのは決めた所だけ。** model が `<reply>…</reply>` の中に書いた文だけがグループに
  送られます。考えの途中は送られません。返事は素の文 (LINE は Markdown を表示しません) で、
  呼んだ発言を引用して返します。
- **時間がかかる時・答えられない時はグループに一言。** 遅くなりそうな答えの前に「ちょっと
  待ってね」の文、答えられなかった時は決まった一言を送ります。1 人が 1 時間に呼べる回数にも
  上限があります。[通知・上限・知らせ](docs/reference/notices-and-limits.md)を見てください。
- **頼まれたら消す。** 自分の発言を「消して」と頼むか送信取消すると、グループの記録と会話から
  消え、その発言を除いた要約から会話が新しく始まります。決めた日数 (既定 30 日) より古い記録も
  消えます (今の会話と要約は除く)。要約がその発言を引用していたら、引用を除いて書き直します。
  [発言を消す](docs/reference/deleting.md)を見てください。
- **昔のトーク履歴を取り込める。** `line-group-agent import-history` で、LINE の「トーク履歴を
  送信」で作った text の file をグループの記録に入れます。
  [昔のトーク履歴の取り込み](docs/reference/importing-history.md)を見てください。
- **止まった時は知らせる。** Claude API の失敗が続いた時・今月の額が上限の 80% を超えた時・
  LINE への送信が失敗した時に、短い push の通知が届きます。
- **月の予算の中で動く。** 毎回の額を API の usage から数えます。API を呼ぶ前に
  「今月の額 + 1 回の最大の見積もり」が上限を超えないか、全体とそのグループ (上限を
  グループの数で割った額) の両方で確かめ、超えるなら決まった文だけを返します。
- **グループの発言はデータとして扱う。** 発言は封筒に入れて model に渡し、指示としては
  読ませません。予約・支払い・グループの外へ送る道具は持っていません。

## 動き

```
LINE グループ ──▶ LINE Platform ──https──▶ あなたの HTTPS の入口 ──▶ line-group-agent (127.0.0.1:8790)
                                                                     │  POST /line/webhook
                                                                     │  1. 大きさの上限・署名の確認・すぐ 200
                                                                     │  2. 許したグループなら発言を記録
                                                                     │  3. メンションならグループの会話を続けて Claude API へ ──▶ web 検索 / web fetch
                                                                     │                               ├─▶ search_history (ローカルの記録)
                                                                     │                               ├─▶ delete_messages (呼んだ人自身の発言・bot の返事)
                                                                     │                               ├─▶ show_cards (候補をカードで)
                                                                     │                               └─▶ 投票・予定表・split_bill・send_location・suggest_replies
                                                                     └─ 4. reply (文・カード・投票や場所・クイックリプライ。token が切れていたら push)
                                                                     (投票カードのボタンは postback で届き、返事なしで数える)
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
| cache の書き込み (5 分 / 1 時間) / 読み出し | 100 万 token あたり $0.125 / $0.20 / $0.01 |
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
- 会話はメンションのたびに送り直すので、API の prompt cache が効きます。cache の読み出しは
  通常の入力の 10 分の 1 です。`cache_ttl` で cache の寿命を選びます。既定の `1h` は書き込みが
  入力の 2 倍 (`5m` は 1.25 倍) ですが、数分〜数時間おきに呼ばれるグループでも安い読み出しで
  続けられます。呼ばれる時が集中するなら `5m` の方が書き込みは安くなります。
- グループごとの上限は月の上限をグループの数で割った額で、満杯の会話を要約する要求の額も
  そのグループに数えます。
- 見積もりは守りで、請求ではありません。Claude Console でも key の workspace に額の上限を
  置いてください。
- 返事は LINE の reply token で送り、無料です。model の答えが token の寿命 (約 1 分) より
  遅れた時は push で送り直し、これはアカウントの月の送信数に数えられます。カード・投票・
  地図のメッセージ・クイックリプライは文と同じ 1 回の呼び出しで送ります。投票の 1 票と
  新しい人への一言は、送信数を使いません。
- model に渡した写真は、ほかの入力と同じように token を使います (写真は先に
  `max_image_edge_pixels` まで縮め、1 回のメンションに付くのは `max_images_per_turn` 枚まで)。
- 答えに web の作業が要る時は、先に短い「待ってね」の文を reply token で送り、答えは push で
  送ります。LINE が今月の送信の残りを十分に返す間だけ (`wait_min_push_left`) 送ります。

## 書く file

全部 `state_dir` の下:

| Path | 中身 |
|---|---|
| `groups/<groupId>/messages.jsonl` | グループの text の発言全部と、写真 (`[写真]`)・位置 (`[位置]`) ごとの 1 行と、bot が送った返事 (`from_bot` の印付き。カード・投票・場所を付けた返事は、末尾にその名前を並べた行が付く)。1 行 1 発言。追記される。消した発言と `retention_days` より古い発言は取り除かれる |
| `groups/<groupId>/images/` | グループの写真 (model に渡せる大きさに縮めた物)。発言と一緒に消える |
| `groups/<groupId>/polls.json` | グループの投票と、誰が何に票を入れたか |
| `groups/<groupId>/itinerary.json` | グループの旅の予定表と、前の 5 つの版 |
| `conversations/g-<groupId>.jsonl` | グループの続いている会話: model に送った物と model の答え。chat の client が読むだけのタブとして見せる |
| `groups/<groupId>/journal/<date>-gen<N>.md` | グループの会話の N 本目を入れ替えた時に書いた要約。消されない |
| `groups/<groupId>/spend.json` | グループの今月の額 (`spend.json` と同じ形) |
| `spend.json` | agent 全体の今月の額: `{"month", "spent", "limit", "currency", "updated_at"}`。毎回全体を書き直す |
| `tabs.json` | グループの一覧と、文脈の量・額・世代。chat の client が読む (path は `tabs_file`) |

設定 file (`settings_file`・例は [`configs/settings.example.json`](configs/settings.example.json)) で、
月の予算・文脈の窓・入れ替えの閾値を、再起動せずに設定画面から変えられます。

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
