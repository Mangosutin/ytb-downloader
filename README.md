# YTB downloader

Version: 0.1.0

Windows / Python 3.13 向けの個人用 YouTube ダウンローダーです。

yt-dlpをPythonライブラリとして利用し、動画・音声を指定した命名規則で保存します。

## 1. 動作環境

- Windows
- Python 3.13
- yt-dlp
- ffmpeg / ffprobe

## 2. ディレクトリ構成

```text
YTB downloader/
├── main.py
├── config.example.toml
├── config.toml
├── requirements.txt
├── run.bat
├── README.md
├── .gitignore
│
├── ytbdl/
│   ├── __init__.py
│   ├── config.py
│   ├── naming.py
│   └── core.py
│
├── tests/
│   └── test_naming.py
│
├── ffmpeg/
│   ├── ffmpeg.exe
│   └── ffprobe.exe
│
├── downloads/
├── logs/
└── archive.txt
```

## 3. インストール

Python 3.13をインストールしてください。

プロジェクトフォルダで以下を実行します。

```bat
py -3.13 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

## 4. ffmpegの配置

既定では、プロジェクト直下の`ffmpeg`フォルダを使用します。

```text
ffmpeg/
├── ffmpeg.exe
└── ffprobe.exe
```

ffmpegは外部同梱とし、requirements.txtには含めません。

別の場所に配置している場合は、config.tomlの`ffmpeg_location`で指定できます。

フォルダまたは実行ファイルのパスを指定してください。

## 5. 設定ファイル

`config.example.toml`をコピーして`config.toml`を作成します。

```toml
download_dir = "downloads"
archive_file = "archive.txt"
log_dir = "logs"

default_mode = "video"
audio_format = "mp3"

ffmpeg_location = "ffmpeg"

subtitles = false
thumbnails = false
embed_metadata = false

cookies = ""
```

### 設定項目

| 項目 | 説明 | 既定値 |
| --- | --- | --- |
| download_dir | 保存先 | downloads |
| archive_file | 重複防止用ファイル | archive.txt |
| log_dir | ログ保存先 | logs |
| default_mode | 既定モード | video |
| audio_format | 音声形式 | mp3 |
| ffmpeg_location | ffmpegの場所 | ffmpeg |
| subtitles | 字幕保存 | false |
| thumbnails | サムネイル保存 | false |
| embed_metadata | メタデータ埋め込み | false |
| cookies | 将来用のCookie設定 | 空 |

相対パスは設定ファイルの配置場所を基準に解決します。

### audio_format

- `mp3`: MP3に変換して保存
- `original`: 元の音声形式のまま保存

## 6. 使用方法

### 動画モード

```bat
run.bat "https://www.youtube.com/watch?v=VIDEO_ID" --mode video
```

最高画質の映像・音声を取得し、MP4にマージします。

ファイル名：

```text
タイトル [動画ID].mp4
```

### 音声モード

```bat
run.bat "https://www.youtube.com/watch?v=VIDEO_ID" --mode audio
```

既定ではMP3に変換します。

```bat
run.bat "https://www.youtube.com/watch?v=VIDEO_ID" --mode audio --config config.toml
```

### 既定モードを使用

```bat
run.bat "https://www.youtube.com/watch?v=VIDEO_ID"
```

config.tomlの`default_mode`が使用されます。

### プレイリスト

プレイリストURLを指定します。

```bat
run.bat "https://www.youtube.com/playlist?list=PLAYLIST_ID"
```

プレイリスト名のフォルダを作成し、その中に動画を保存します。

単発動画はdownloads直下に保存します。

## 7. 命名規則

### 動画

```text
タイトル [動画ID].mp4
```

### 音声

```text
曲名 (feat. アーティスト) (Remix) (Cover) - アーティスト.mp3
```

存在しない要素は省略します。

#### feat表記

以下の表記を統一します。

- feat.
- ft.
- featuring

出力は`feat.`に統一します。

#### Remix

Remix表記は曲名の後ろに配置します。

複数のRemix表記にも対応します。

#### Cover

次の文字列を含むタイトルをCoverとして判定します。

- 歌ってみた
- Cover
- カバー

Coverの場合は曲名に`(Cover)`を付けます。

カバー歌い手をアーティストとして使用します。

歌い手が取得できない場合はuploaderを使用します。

原アーティストはファイル名に含めず、メタデータ埋め込みが有効な場合はメタデータ側に保持します。

### 曲名・アーティストの取得順序

1. yt-dlpのtrack / artistメタデータ
2. タイトルの正規表現解析
3. uploaderによるアーティスト推定

解析できない場合は取得したタイトルをフォールバックとして使用します。

## 8. 重複防止

yt-dlpのdownload archiveを使用します。

ダウンロード済み動画のIDがarchiveに記録されます。

同じ動画IDは再ダウンロード対象から除外されます。

## 9. ログ

`logs/`に日時付きのログファイルを保存します。

例：

```text
logs/
└── ytbdl_20261114_120000.log
```

ログにはダウンロードの開始・終了、進捗、警告、エラーを記録します。

## 10. テスト

pytestを使用して命名処理をテストできます。

```bat
python -m pip install pytest
python -m pytest tests/
```

## 11. 対象外

v0.1.0では以下に対応しません。

- GUI
- チャンネル全動画の一括ダウンロード
- Cookie認証
- 年齢制限・メンバー限定などCookieが必要な動画

## 12. バージョン

v0.1.0
