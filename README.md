# YTB downloader

Version: 0.1.5

Windows / Python 3.13 向けの個人用 YouTube ダウンローダーです。

yt-dlpをPythonライブラリとして利用し、動画・音声を指定した命名規則で保存します。

## 1. 動作環境

- Windows
- Python 3.13
- yt-dlp（`yt-dlp[default]`）
- Deno（YouTubeのJavaScriptチャレンジ処理用）
- ffmpeg / ffprobe

## 2. ディレクトリ構成

```text
YTB downloader/
├── main.py
├── config.example.toml
├── config.toml
├── requirements.txt
├── run.bat
├── run.ps1
├── run.py
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

フォルダまたは実行ファイルのパスを指定してください。Windowsの絶対パスを指定するときは、TOMLのバックスラッシュがエスケープ文字として扱われないよう、次のいずれかの形式にしてください。

```toml
# 推奨: シングルクォートのリテラル文字列
ffmpeg_location = 'E:\app\ffmpeg'

# または、バックスラッシュを2つずつ記述
ffmpeg_location = "E:\\app\\ffmpeg"
```

通常はプロジェクト直下の`ffmpeg`フォルダを使う`ffmpeg_location = "ffmpeg"`のままで問題ありません。

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
force_ipv4 = true

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
| force_ipv4 | yt-dlpの通信をIPv4に固定 | true |
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
# PowerShellではrun.pyを使用
python .\run.py 'https://www.youtube.com/watch?v=VIDEO_ID' --mode video
```

最高画質の映像・音声を取得し、MP4にマージします。

ファイル名：

```text
タイトル [動画ID].mp4
```

### 音声モード

```bat
run.bat "https://www.youtube.com/watch?v=VIDEO_ID" --mode audio
# PowerShellではrun.pyを使用
python .\run.py 'https://www.youtube.com/watch?v=VIDEO_ID' --mode audio
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

URLに`&`が含まれる場合、PowerShellではPythonランチャー`run.py`を直接使用してください。PowerShellの文字列クォートがURL全体を保護し、`cmd.exe`のバッチ引数処理を通さずにPythonへ1つの引数として渡します。

```powershell
python .\run.py 'https://www.youtube.com/playlist?list=PLAYLIST_ID'
python .\run.py 'https://www.youtube.com/watch?v=1jdTOxzXskE&list=PLM1t88YmeLxs&pp=0gcJCYgGa94AFGB0sAgC'
```

音声モードや設定ファイルも指定できます。

```powershell
python .\run.py 'https://www.youtube.com/watch?v=VIDEO_ID&list=PLAYLIST_ID' --mode audio
python .\run.py 'https://www.youtube.com/watch?v=VIDEO_ID' --config '.\config.toml'
```

`.venv`を有効化していない場合も、プロジェクト内の仮想環境があれば`run.ps1`が自動選択します。PowerShellの実行ポリシーでスクリプトがブロックされる場合は、次のようにプロセス単位のBypassで起動できます（システム設定は変更しません）。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 -Url 'https://www.youtube.com/watch?v=VIDEO_ID&list=PLAYLIST_ID'
```

`run.bat`はコマンドプロンプト（cmd.exe）から使うためのランチャーです。PowerShellからURL付きで`run.bat`を呼び出すと、`&`の扱いがシェル間で変わるため避けてください。PowerShellでは上記の`run.py`を推奨します。

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

## 8. 通信設定

既定では`force_ipv4 = true`として、yt-dlpのメタデータ取得とメディア取得の両方をIPv4に固定します。yt-dlpの`source_address = "0.0.0.0"`を使用します。

IPv4固定を無効にする場合は、`config.toml`で次のように指定します。

```toml
force_ipv4 = false
```

## 9. 重複防止

yt-dlpのdownload archiveを使用します。

ダウンロード済み動画のIDがarchiveに記録されます。

同じ動画IDは再ダウンロード対象から除外されます。

## 10. ログ

`logs/`に日時付きのログファイルを保存します。

例：

```text
logs/
└── ytbdl_20261114_120000.log
```

ログにはダウンロードの開始・終了、進捗、警告、エラー、yt-dlpのバージョン、IPv4固定の状態を記録します。

HTTP 403が発生した場合は、IPv4設定の状態と確認項目を追加表示します。IPv4固定だけで全ての403が解消するわけではありません。

## 11. テスト

pytestを使用して設定・URL処理・命名規則・IPv4通信オプションをテストできます。

```bat
python -m pip install pytest
python -m pytest tests/
```

## 12. 対象外

v0.1.5時点では以下に対応しません。

- GUI
- チャンネル全動画の一括ダウンロード
- Cookie認証
- 年齢制限・メンバー限定などCookieが必要な動画

## 13. バージョン

v0.1.5

### v0.1.5 の変更点

- メタデータ取得とメディア取得を同じ `YoutubeDL` インスタンスで実行するよう変更
- 音声形式・動画形式・後処理・IPv4設定をURL抽出前に適用
- プレイリスト判定後に保存先テンプレートだけを更新
- yt-dlpの抽出時状態と通信コンテキストをダウンロード処理まで維持

### v0.1.4 の変更点

- yt-dlpのメタデータ取得・メディア取得の両方でIPv4を既定使用
- `force_ipv4`設定を追加し、必要に応じてIPv4固定を無効化できるように変更
- HTTP 403発生時に、IPv4設定状態と追加確認項目をログへ出力
- 起動時ログにyt-dlpのバージョンを追加

### v0.1.3 の変更点

- PowerShellからURL内に`&`を含むURLを安全に渡せるPythonランチャー`run.py`を追加
- `run.ps1`をWindows PowerShell 5.1向けに簡素化し、UTF-8 BOM付きで保存
- `run.bat`をコマンドプロンプト専用ランチャーとして整理
- PowerShellでは`.bat`を介さずPythonへ直接渡す利用方法をREADMEに明記

### v0.1.2 の変更点

- PowerShell用の`run.ps1`を追加し、URLをPythonへ直接1引数として渡すように変更
- `run.bat`はURLを環境変数経由で渡し、Python起動コマンドへURLを再展開しないように変更
- コマンドラインURLが省略された場合に、ランチャーから渡された環境変数を利用する機能を追加
- PowerShellでのプレイリストURLの実行例を追加
