# スマ庫 — 大乱闘スマッシュブラザーズ 動画アーカイブ

合言葉を入れた人だけが見られる、スマブラ動画の自動アーカイブサイトです。
指定したYouTube／Twitchチャンネルの新着動画から、**「ドクターマリオ」に関する動画だけ** を
GitHubが自動で集めて一覧にします。基本は **無料** の範囲で動きます。

## ドクターマリオ絞り込みについて（重要）
動画の映像を見てキャラを画像認識するのは無料の自動処理では不可能なため、
**タイトル・説明文に「ドクターマリオ / ドクマリ / Dr. Mario」等が含まれる動画だけ** を保存します。
拾うキーワードは `config.json` の `filter_keywords` で自由に追加・変更できます。
（`require_keyword` を `false` にすると絞り込みを解除して全部保存します）

---

## 仕組み（かんたんに）

- **GitHub Pages** … サイトを表示する場所（無料）
- **GitHub Actions** … 3時間ごとに動いて、指定チャンネルの新着動画を自動収集（無料）
- **videos.json** … 集めた動画リンクの保存先
- **合言葉ゲート** … サイトを開くと合言葉を聞かれる。合っていれば入場できる

> ⚠️ 大事な注意：無料プランではリポジトリが「公開(Public)」になります。
> つまり合言葉を知らない人でも、頑張れば動画リンクの一覧そのもの（videos.json）は見られます。
> 合言葉は「知らない人がフラッと来ても中身を見せない、身内向けの鍵」だと考えてください。
> 本格的に隠したい場合は末尾「もっと安全にしたいとき」を参照。

---

## セットアップ手順（GitHubが初めてでもOK）

### 1. GitHubアカウントを作る
https://github.com/signup からメール・パスワードで登録。

### 2. 新しいリポジトリ（置き場）を作る
- 右上「＋」→ **New repository**
- Repository name: 例）`sumako`
- **Public** を選択（無料でPages/Actionsを使うため）
- 「Create repository」

### 3. ファイルをアップロードする
- リポジトリ画面の「**Add file**」→「**Upload files**」
- この `スマ庫` フォルダの中身を **すべて** ドラッグ＆ドロップ
  （`.github` フォルダも忘れずに。フォルダごとドラッグするとまとめて上がります）
- 下の「Commit changes」を押す

### 4. GitHub Pages を有効にする（サイトを公開）
- 「**Settings**」タブ →左メニュー「**Pages**」
- Source: **Deploy from a branch**
- Branch: **main** / **/(root)** → **Save**
- 数分待つと、上に公開URLが出ます：
  `https://（あなたのユーザー名）.github.io/sumako/`

### 5. 自動収集の権限をONにする
- 「Settings」→「**Actions**」→「**General**」
- 下の方「Workflow permissions」で **Read and write permissions** を選ぶ → **Save**
  （これで収集ボットが videos.json を更新できます）

### 6. 収集するチャンネルを設定する
- リポジトリの `config.json` を開く → 右上の鉛筆✏️で編集
- `youtube_channels` の `"UCXXXX..."` を、集めたいチャンネルに書き換える
  - チャンネルID（`UC` で始まる文字列）でも、`@ハンドル名` でもOK
  - 例）`"@SmashBrosJP"` や `"UCabc...123"`
  - 複数入れるなら `["@channelA", "@channelB"]` のようにカンマ区切り
- 「Commit changes」

### 7. 最初の収集を手動で走らせる
- 「**Actions**」タブ →「動画を自動収集」→「**Run workflow**」
- 1〜2分で videos.json が更新され、サイトに動画が並びます
- 以降は3時間ごとに自動で新着を追加します

### 8. 合言葉を自分のものに変える（オーナーだけの操作）
初期の合言葉は **`smashbros`** です。必ず変更してください。
1. ブラウザで `https://（ユーザー名）.github.io/sumako/tools/make-hash.html` を開く
2. 新しい合言葉を入力 → 表示された「ハッシュ」をコピー
3. リポジトリの `site-config.js` を編集し、`PASSPHRASE_HASH: "……"` の中身を貼り替える
4. 「Commit changes」→ 完了

合言葉を変えられるのは、このリポジトリを操作できる **オーナー（あなた）だけ** です。

---

### （任意）Twitchのアーカイブも集めたいとき
TwitchはYouTubeと違い、無料の公開RSSがないため **APIキー** が必要です。
1. https://dev.twitch.tv/console にログイン →「Register Your Application」
   - Name: 好きな名前 / OAuth Redirect URLs: `http://localhost` / Category: Website Integration
   - 作成後、**Client ID** と **Client Secret**（Newで生成）を控える
2. GitHubリポジトリ →「Settings」→「Secrets and variables」→「Actions」
   → 「New repository secret」で2つ登録：
   - `TWITCH_CLIENT_ID` … Client ID
   - `TWITCH_CLIENT_SECRET` … Client Secret
3. `config.json` の `twitch_channels` に配信者名を入れる：`["配信者ログイン名"]`
4. Actionsを再実行すれば、Twitchの過去配信(VOD)も対象になります

> ⚠️ Twitchの注意：VOD（過去配信）は Twitch 側の仕様で一定期間（通常7〜60日）で自動削除されます。
> 消えた配信は再生できなくなります（"半永久保存" にはなりません）。

## よくある質問

**Q. チャンネルIDはどこで分かる？**
チャンネルのページを開き、`@ハンドル名` をそのまま config.json に入れればOK（自動でIDに変換します）。
うまくいかないときは、チャンネルページのURLに含まれる `UC...` の文字列を使ってください。

**Q. 動画が増えすぎない？**
`config.json` の `max_keep`（初期500）で保存する最大本数を調整できます。

**Q. 収集の間隔を変えたい**
`.github/workflows/archive.yml` の `cron: "0 */3 * * *"` を編集（`*/3` が「3時間ごと」）。

---

## 登録済みチャンネル一覧（config.jsonの中身）
編集・削除の目安にどうぞ。並び順は config.json と同じです。

| # | チャンネル | ID |
|---|---|---|
| 1 | @ケイロンチーノ | UCJoMRVJFzKwnvPO-xY5V29w |
| 2 | @まえだくん | UC1wbp2hvbSfnhiY14fTd9fg |
| 3 | @Tamisumajp | UCI13aTPz_ip8lXGpjkGBCow |
| 4 | @滋賀県スマブラオフ | UCcXevFPHEeQI1QaDYaZNvoQ |
| 5 | @westerlies_gaming | UCFPaBLxpWvL-1ddHnWEjVdw |
| 6 | @AKはにゆ | UCWb-TYOIFA5LvEVpy2JBCTA |
| 7 | @kyokkan_smash | UCKek-22lQ2RYMIQZD8NtCCw |
| 8 | @岐阜スマ | UCuGnLR9zl7t38OTDsx7fgDA |
| 9 | @Tsumusuto | UC9NGb26s4iszCV3pcRKtd9w |
| 10 | @BUZZe-sports | UC0CNxYESc0khvnecH7pKS2Q |
| 11 | @B_ST_Stream | UC_62yzDG1VUUbjjnUmP4X_w |
| 12 | @pra-sma | UCUllYhRCcjlVUw8DqlBq3zA |
| 13 | @vgbootcamp | UCMo0JzwgHCZ435K9BAAi8Rg |
| 14 | @nugget9264 | UCG-DRzdif4Qi24YDJIsGAeg |
| 15 | @SmashLibrarian | UC-DgOAMR_o3Oi9ijt44--wQ |
| 16 | channel/UCf_AH…（URL指定） | UCf_AHbUGK2oQS3iS3HWUswg |
| 17 | @CommunityCUPgg | UCfP7zXrwSEHUnjh3F2DfhUA |
| 18 | @HachiSmash | UCP54rPveg9o3jq0l_0VnR_w |
| 19 | @SmashWorldReplays | UCYEmZia36kLiZ0UFtj-kgbw |
| 20 | @GamersGuildFGC | UCj1J3QuIftjOq9iv_rr7Egw |
| 21 | @M2Gsmash | UCZXqfK9UQoDKRjba-Fu76Ow |
| 22 | @nioxoinOnline | UCcGPLB0s_EmnQBLeJW6DMTQ |
| 23 | @sen-smash-chiba | UCLqzIfCONWhHHpKnYQi3yvw |
| 24 | @ovorozukiyo | UCPRnun4myv-BazdIMcF9fEA |

> 収集はYouTube公式RSSの仕様上、各チャンネルの **最新15本程度** が対象です。
> つまり「過去すべての遡り保存」はできませんが、動き続けるほど新着ドクマリ動画が自動でたまっていきます。

## もっと安全にしたいとき（任意）

- **GitHub Pro（月数ドル）** にすると、リポジトリを非公開(Private)のままPages公開できます。
- または videos.json を合言葉で **暗号化** して保存すれば、鍵を知らない人には中身が読めません（実装は要相談）。

必要になったら声をかけてください。
