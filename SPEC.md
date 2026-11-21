# YTB downloader 仕様書 v0.1（2026-11-14 設計確定）

## 概要
- 個人用の YouTube ダウンローダー。観測画像カレンダー（ytb_uploader）とは無関係の別ツール。
- 目的: 見たい／聴きたい動画と曲を、決まった命名規則でローカルに保存する。

## 技術構成
- Python 3.13 ＋ yt-dlp（ライブラリとして呼ぶ薄いラッパー）
- ffmpeg: ツールフォルダに同梱を既定とし、設定でパスを変更可能（マージ・音声変換用）
- 設定ファイル: TOML（config.toml）
- 起動: `py run.py "URL"`（Windows / ポータブル運用、配置先は E:\app 配下を想定）
- 実行ログをファイルに残す

## 機能
- 入力: URL（単発動画／プレイリスト両対応。チャンネルの全動画一括は対象外）
- モード: 動画モード／音声（曲）モード
- 重複防止: yt-dlp の download archive（動画ID記録）を使う

## 動画モード
- 最高画質（bestvideo+bestaudio）を取得し mp4 にマージ
- ファイル名: `タイトル [動画ID].mp4`
- 保存先: 既定はツール配下の downloads\（設定で変更可）

## 音声（曲）モード
- 形式: 既定は mp3（元音声のままの保存も設定で選べるようにする）
- ファイル名規則: `曲名 (feat. ○○) (○○Remix) (Cover) - アーティスト`
  - 各要素が無い場合は、そのカッコごと省略する
  - feat の表記は統一する（ft. / featuring などは feat. に正規化）
  - 例: feat も remix も無い曲 → `夜に駆ける - YOASOBI`
- 曲名・アーティストの取得:
  1. yt-dlp のメタデータ（track / artist）が取れればそれを使う（公式音源系）
  2. 取れなければタイトルを正規表現で解析する（feat. / Remix の抽出、「アーティスト - 曲名」分割、uploader からの推定）
  3. 解析できない要素は省略してフォールバックする
- cover の扱い（方式A）:
  - 判定: タイトルに「歌ってみた」「Cover」「カバー」を含む
  - アーティスト欄はカバー歌い手にし、曲名側に `(Cover)` を付ける
  - 原アーティストはファイル名に入れず、メタデータタグ側に残す

## その他の出力設定
- 字幕・サムネイル・メタデータ埋め込み: 既定 OFF、設定で ON にできる

## 通信設定（v0.1.4）
- yt-dlpのメタデータ取得とメディア取得の両方でIPv4を既定使用する。
- `force_ipv4` 設定で有効・無効を切り替えられる（既定値: true）。
- IPv4固定時はyt-dlpの `source_address = "0.0.0.0"` を使用する。
- HTTP 403時はIPv4設定状態を含む診断用メッセージをログに記録する。

## 認証
- 初期実装では Cookie なし
- 将来の拡張用に、設定項目 `cookies` だけ先に用意しておく（未使用）

## 対象外（v0.1）
- GUI（将来のオプションとして検討のみ）
- チャンネル全動画の一括ダウンロード
- 年齢制限・メンバー限定など Cookie が必要な動画

## ダウンロード実行方式（v0.1.5）
- yt-dlpのオプション（形式選択・後処理・通信設定）を初期化時にまとめて適用する。
- メタデータ抽出とメディア取得は、同一の `YoutubeDL` インスタンス内で実行する。
- プレイリストか単体動画かによって保存先が決まるため、抽出後に出力テンプレートのみ更新する。

## ダウンロード実行方式（v0.1.6）
- メタデータ抽出とメディア取得は、別々の `YoutubeDL` インスタンスで実行する。
- 抽出用のインスタンスには `download_archive` を含めない。ダウンロード用のインスタンスでのみ有効化する。
- アーカイブ済みの動画や、全件取得済みのプレイリストはエラーではなく正常終了する（「すべて取得済みです」を記録する）。
- `PlaylistEntries` は list 化して実体化し、プレイリスト本体に音声命名を適用しない。
- `EntryNotInPlaylist` は全件取得済みとして正常終了する。
- watch?v=...&list=...&index=N 形式の URL は、その index（1始まり）の1曲だけをダウンロードする（yt-dlp の `playlist_items` を使用）。
- index が不正・範囲外の場合は警告を記録し、v の単体動画としてダウンロードする。
- `music.youtube.com` の watch URL（`v` と `list` を含む）は、index の有無にかかわらず `v` の単体動画として1曲だけをダウンロードする（YouTube Music の曲ID&listID 形式）。
- 上記以外の index のない watch URL と playlist URL は従来どおりプレイリスト全体をダウンロードする。

## 音声設定（v0.1.6）
- 音声モードでは、既定で動画のサムネイルをアルバムアートとして MP3 へ埋め込む（`embed_album_art`、既定 true）。
- 埋め込み用の一時サムネイルファイルは downloads フォルダに残さない。
- MP3 変換の既定ビットレートは 256 kbps（`audio_bitrate`、単位 kbps）。
- 量子化ビット数（`audio_bit_depth`: 16 / 24 / 32）とサンプリング周波数（`audio_sample_rate`: Hz）を指定できる。未指定は元のまま変換しない。
- mp3 は非可逆形式のため、ビット深度の指定は ffmpeg の変換段階（PCM 段階／エンコード前処理）に効くものである。`audio_format` が original で変換が走らない場合は適用されない。

## v0.1.7 追加仕様

### MusicBrainz によるジャンル照合

- genre_lookup：bool、既定 true。音声モードで MusicBrainz recording を検索し、recording → release-group → artist の順にジャンルを探索する。false で無効化可能。
- User-Agent を付与し、リクエスト間隔を最低1秒とする。失敗は警告のみ。

### 音声ストリームハッシュ

- record_audio_hash：bool、既定 true。音声モードで変換完了後の音声ストリーム SHA-256 を ffmpeg streamhash で計算し、AUDIO_STREAM_SHA256 タグとして codec copy で記録する。失敗は警告のみ。

### JSON リンクリスト

- --linklist PATH：URL 文字列配列または {"url": "...", "mode": "audio" | "video"} 配列を読み込む。mode 省略時は CLI 指定、設定ファイル既定値の順で解決する。全件処理後に成功・スキップ・失敗件数を集計し、失敗があれば終了コード1。

## v0.1.8 追加仕様

### トレイアプリ（Issue #5）

- 依存追加: pywin32（requirements.txt に追加済み。未インストール時はトレイ起動が明確なエラーメッセージで失敗し、`pip install -r requirements.txt` でインストールできます）
- `py run.py`（引数なし・Windows）または `py run.py --tray` でタスクトレイアプリを起動する。URL指定時はこれまでどおり CLI 実行する。
- 左クリック: クリップボードの YouTube URL を読み取り、実行キューに追加する。Toast(通知)で「スタックしました: <desc>」を表示する。
- 左クリック時の実行内容は Toast とトレイのツールチップで確認できる: モード(audio/video)、単体/プレイリスト、タイトル(playlistName/videoTitle)。
- 右クリック: 固定位置の小さなウィンドウを表示する:
  - 実行中項目の詳細(`audio | 単体 | タイトル [abc123]` 等)
  - 待機中キュー(最大8件、`... 他N件` を表示)
  - 入力フォーム(YouTube URL + 引数)とラベル
  - ボタン: Stack/追加、Run now/即実行、Clear/消去、Quit/終了
  - 入力形式: `<YouTube URL> [--mode audio|video]` — 左端はURL(引用符なし)、空白区切りで `--mode audio|video` または `--mode=audio` を追記可能（無効な値は無視）。Enterキーでも Stack に反映される。
- 実行キュー(DownloadQueue):
  - FIFO 順に1件ずつ順次実行(最大1件並列)。
  - Run now はキュー先頭に積む(優先度)。
  - ダウンロード前に archive 済みの動画IDはスキップする。
  - 項目実行中の例外は `DownloadRequest.error` に保存しキューは継続する。
