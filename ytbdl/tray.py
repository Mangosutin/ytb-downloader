"""Windows のタスクトレイアプリ。

左クリック: クリップボードの YouTube URL を実行キューに追加する。
右クリック: 固定位置の小さいウィンドウを表示する
  (実行中/待機中キューの詳細、入力フォーム + Stack/Run now/Clear/Quit ボタン)。
"""

from __future__ import annotations

import ctypes
import logging
import queue

from ytbdl.clipboard import find_youtube_url, get_clipboard_text
from ytbdl.config import Config
from ytbdl.queue import DownloadQueue, QueueStatus, describe_item

try:
    import win32api
    import win32con
    import win32gui
except ImportError:
    win32api = None
    win32con = None
    win32gui = None

logger = logging.getLogger(__name__)

# ウィンドウクラス名
_TRAY_CLASS = "YTBDownloader_Tray"
_CONTROL_CLASS = "YTBDownloader_Control"
_INPUT_EDIT_CLASS = "YTBDownloader_InputEdit"
_TOAST_CLASS = "YTBDownloader_Toast"

# トレイアイコンの callback メッセージ (WM_USER + 10)
_TRAY_CALLBACK = (win32con.WM_USER + 10) if win32con is not None else 1034

# コントロールウィンドウは画面中央下に固定配置する
_CONTROL_WIDTH = 440
_CONTROL_HEIGHT = 190
_TOAST_WIDTH = 440
_TOAST_HEIGHT = 60

# コントロールウィンドウ内のコントロールID
_ID_STATUS = 2001
_ID_QUEUE = 2002
_ID_HINT = 2003
_ID_INPUT = 2004
_ID_STACK = 2005
_ID_RUN_NOW = 2006
_ID_CLEAR = 2007
_ID_QUIT = 2008

_REFRESH_TIMER_ID = 1
_REFRESH_INTERVAL_MS = 500

_TIP_IDLE = "YTB Downloader"
_TOAST_DISMISS_MS = 6000

_TIP_RUNNING = "YTB Downloader: {desc}"
_TIP_QUEUED = "YTB Downloader: キュー済み({n}件)"

# 入力フォームのラベル文字列
_HINT_TEXT = "入力形式: <YouTube URL> [--mode audio|video]"


def parse_stacked_input(text: str) -> tuple[str, str]:
    """コントロールウィンドウの入力フォームから (url, mode) を解析する。

    入力形式:
        `<YouTube URL> [--mode audio|video] ...`
    - URL は左端トークンとして `find_youtube_url(text)` で抽出
      （引用符なしURL入力に対応）。
    - mode は `--mode audio|video` または `--mode=audio` 形式をスキャン。
      無効な値は無視する。
    - URL が見つからない場合は ("", "") を返す。
    """
    url = find_youtube_url(text)
    if not url:
        return "", ""
    mode = ""
    tokens = text.split()
    for index, token in enumerate(tokens):
        if token == "--mode":
            if index + 1 < len(tokens):
                value = tokens[index + 1]
                if value in ("audio", "video"):
                    mode = value
        elif token.startswith("--mode="):
            value = token[len("--mode="):]
            if value in ("audio", "video"):
                mode = value
    return url, mode


# ----------------------------------------------------------------------
# ウィンドウ生成ヘルパー

def _register_window_class(class_name: str, proc_fn) -> None:
    hinst = win32api.GetModuleHandle(None)
    wc = win32gui.WNDCLASS()
    wc.style = 0
    wc.lpfnWndProc = proc_fn
    wc.hInstance = hinst
    wc.lpszClassName = class_name
    try:
        win32gui.RegisterClass(wc)
    except win32gui.error:
        pass


def _create_window(class_name, title, style, ex_style, x, y, w, h, parent, id_):
    hinst = win32api.GetModuleHandle(None)
    return win32gui.CreateWindowEx(
        ex_style, class_name, title, style, x, y, w, h,
        parent, id_, hinst, None,
    )


def _set_timer(hwnd: int, timer_id: int, interval_ms: int) -> None:
    """Win32 の SetTimer（pywin32 未提供のため ctypes 経由）。

    lpTimerFunc=NULL のため、WM_TIMER メッセージが hwnd に投稿される。
    """
    ctypes.windll.user32.SetTimer(hwnd, timer_id, interval_ms, None)


def _work_area() -> tuple[int, int, int, int]:
    """タスクバーを除いた作業領域 (left, top, right, bottom) を返す。"""

    class _RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    work = _RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(work), 0)
    return (work.left, work.top, work.right, work.bottom)


def _control_rect() -> tuple[int, int, int, int]:
    work_left, work_top, work_right, work_bottom = _work_area()
    return (
        work_right - _CONTROL_WIDTH - 8,
        work_bottom - _CONTROL_HEIGHT - 8,
        _CONTROL_WIDTH,
        _CONTROL_HEIGHT,
    )


def _toast_rect(control_height: int = _CONTROL_HEIGHT) -> tuple[int, int, int, int]:
    work_left, work_top, work_right, work_bottom = _work_area()
    # 制御ウィンドウの上端の上に固定配置する
    y = work_bottom - control_height - 8 - _TOAST_HEIGHT - 8
    return (work_right - _TOAST_WIDTH - 8, y, _TOAST_WIDTH, _TOAST_HEIGHT)


# ----------------------------------------------------------------------
# トースト通知ウィンドウ

class ToastWindow:
    """短時間だけ表示する通知ウィンドウ（自動閉じ）。"""

    CLASS = _TOAST_CLASS

    def __init__(
        self,
        app: TrayApp,
        text: str,
        req=None,
        dismiss_after_ms: int = _TOAST_DISMISS_MS,
    ):
        self.app = app
        self.req = req
        self.dismiss_after_ms = dismiss_after_ms
        self.hwnd: int | None = None
        self._proc_ref = self._toast_proc
        _register_window_class(self.CLASS, self._proc_ref)
        control = self.app._control
        control_height = _CONTROL_HEIGHT
        if control.hwnd is not None:
            rect = win32gui.GetWindowRect(control.hwnd)
            control_height = rect[3] - rect[1]
        x, y, w, h = _toast_rect(control_height)
        self.hwnd = _create_window(
            self.CLASS,
            _TIP_IDLE,
            win32con.WS_POPUP,
            win32con.WS_EX_TOOLWINDOW | win32con.WS_EX_TOPMOST,
            x, y, w, h,
            None, 0,
        )
        win32gui.SetWindowText(self.hwnd, text)
        _set_timer(self.hwnd, 1, self.dismiss_after_ms)
        win32gui.ShowWindow(self.hwnd, win32con.SW_SHOWNOACTIVATE)

    def is_alive(self) -> bool:
        return self.hwnd is not None and win32gui.IsWindowVisible(self.hwnd)

    def update(self, text: str) -> None:
        if not self.is_alive():
            return
        win32gui.SetWindowText(self.hwnd, text)

    def close(self) -> None:
        if self.hwnd is not None:
            win32gui.DestroyWindow(self.hwnd)
            self.hwnd = None

    def _toast_proc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_TIMER:
            self.close()
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)


# ----------------------------------------------------------------------
# コントロールウィンドウ(右クリック時に表示)

class ControlWindow:
    """実行中/待機中キューの詳細と入力フォームを表示する小さなウィンドウ。

    位置は画面中央下に固定される。縦方向に連結:

        実行中項目の詳細
        待機中キュー(最大8件)
        入力フォーム(YouTube URL + 引数) + ボタン
    """

    CLASS = _CONTROL_CLASS
    TITLE = "YTB Downloader - 実行キューと入力"
    WIDTH = _CONTROL_WIDTH
    HEIGHT = _CONTROL_HEIGHT

    def __init__(self, app: TrayApp):
        self.app = app
        self.hwnd: int | None = None
        self._status_hwnd = 0
        self._queue_hwnd = 0
        self._hint_hwnd = 0
        self._input_hwnd = 0
        self._stack_hwnd = 0
        self._run_now_hwnd = 0
        self._clear_hwnd = 0
        self._quit_hwnd = 0

    def show(self) -> None:
        if self.hwnd is None:
            self._create()
        else:
            # A background tray app cannot be made foreground (Windows
            # rejects it); don't let that abort the show.
            try:
                win32gui.SetForegroundWindow(self.hwnd)
            except win32api.error:
                logger.debug(
                    "SetForegroundWindow failed in ControlWindow.show(); "
                    "showing the window without activation",
                    exc_info=True,
                )
        win32gui.ShowWindow(self.hwnd, win32con.SW_SHOWNORMAL)
        win32gui.BringWindowToTop(self.hwnd)
        self._refresh()

    def _create(self) -> None:
        # コールバックの生存参照をオブジェクトに保持する
        self._proc_ref = self._proc
        self._input_proc_ref = self._input_proc
        _register_window_class(_CONTROL_CLASS, self._proc_ref)
        _register_window_class(_INPUT_EDIT_CLASS, self._input_proc_ref)
        x, y, w, h = _control_rect()
        self.hwnd = _create_window(
            self.CLASS,
            self.TITLE,
            win32con.WS_OVERLAPPED | win32con.WS_CAPTION | win32con.WS_SYSMENU,
            0,
            x, y, w, h,
            None, 0,
        )
        # 実行中/待機中のステータス
        self._status_hwnd = _create_window(
            "STATIC", "",
            win32con.WS_CHILD | win32con.WS_VISIBLE, 0,
            8, 4, w - 16, 22, self.hwnd, 0,
        )
        # 待機中キューの一覧
        self._queue_hwnd = _create_window(
            "STATIC", "",
            win32con.WS_CHILD | win32con.WS_VISIBLE, 0,
            8, 28, w - 16, 68, self.hwnd, 0,
        )
        # 入力フォームのラベル
        self._hint_hwnd = _create_window(
            "STATIC", _HINT_TEXT,
            win32con.WS_CHILD | win32con.WS_VISIBLE, 0,
            8, 98, w - 16, 20, self.hwnd, 0,
        )
        # 入力フォーム(URL + 引数)
        self._input_hwnd = _create_window(
            _INPUT_EDIT_CLASS, "",
            win32con.WS_CHILD | win32con.WS_VISIBLE
            | win32con.ES_AUTOHSCROLL, 0,
            8, 124, w - 16, 24, self.hwnd, 0,
        )
        # ボタン
        self._stack_hwnd = self._create_button("Stack/追加", 8, 152, 84, _ID_STACK)
        self._run_now_hwnd = self._create_button("Run now/即実行", 96, 152, 102, _ID_RUN_NOW)
        self._clear_hwnd = self._create_button("Clear/消去", 202, 152, 60, _ID_CLEAR)
        self._quit_hwnd = self._create_button("Quit/終了", 268, 152, 52, _ID_QUIT)
        win32gui.UpdateWindow(self.hwnd)
        self._refresh()

    def _create_button(self, text: str, x: int, y: int, w: int, control_id: int):
        return _create_window(
            "BUTTON", text,
            win32con.WS_CHILD | win32con.WS_VISIBLE
            | win32con.BS_PUSHBUTTON, 0,
            x, y, w, 24, self.hwnd, control_id,
        )

    def _read_input(self) -> str:
        return win32gui.GetWindowText(self._input_hwnd)

    def _stack(self, priority: int = 0) -> None:
        self.app.enqueue_stack(self._read_input(), priority=priority)

    def _measure_text_height(self, text: str, width: int) -> int:
        if not text:
            text = " "
        hwnd = self._queue_hwnd
        hdc = win32gui.GetDC(hwnd)
        try:
            font = win32gui.SendMessage(hwnd, win32con.WM_GETFONT, 0, 0)
            old_font = None
            if font:
                old_font = win32gui.SelectObject(hdc, font)
            try:
                result = win32gui.DrawText(
                    hdc, text, -1, (0, 0, width, 0),
                    win32con.DT_CALCRECT | win32con.DT_WORDBREAK,
                )
                if isinstance(result, (list, tuple)):
                    if isinstance(result[-1], (list, tuple)):
                        height = result[-1][3] - result[-1][1]
                    else:
                        height = result[0]
                else:
                    height = result
                return max(14, height or 14)
            finally:
                if old_font is not None:
                    win32gui.SelectObject(hdc, old_font)
        finally:
            win32gui.ReleaseDC(hwnd, hdc)

    def _layout(self) -> None:
        if self.hwnd is None:
            return
        queue_text = win32gui.GetWindowText(self._queue_hwnd) or "(キューなし)"
        queue_h = self._measure_text_height(queue_text, _CONTROL_WIDTH - 16)
        status_h = 22
        hint_h = 20
        input_h = 24
        buttons_h = 24
        margin = 4
        gap = 4
        status_y = margin
        queue_y = status_y + status_h + gap
        hint_y = queue_y + queue_h + gap
        input_y = hint_y + hint_h + gap
        buttons_y = input_y + input_h + gap
        window_h = buttons_y + buttons_h + margin
        w = _CONTROL_WIDTH
        work_left, work_top, work_right, work_bottom = _work_area()
        # クライアント領域(window_h)からウィンドウ全体のサイズを算出
        # (キャプション/枠を含める; pywin32 に AdjustWindowRect がないため
        #  ctypes 経由で呼び出す)
        style = win32con.WS_OVERLAPPED | win32con.WS_CAPTION | win32con.WS_SYSMENU
        rect = (ctypes.c_long * 4)(0, 0, w, window_h)
        ctypes.windll.user32.AdjustWindowRect(ctypes.byref(rect), style, False)
        total_w = rect[2] - rect[0]
        total_h = rect[3] - rect[1]
        x = work_right - total_w - 8
        y = work_bottom - total_h - 8
        win32gui.SetWindowPos(
            self._status_hwnd, 0, 8, status_y, w - 16, status_h,
            win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE,
        )
        win32gui.SetWindowPos(
            self._queue_hwnd, 0, 8, queue_y, w - 16, queue_h,
            win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE,
        )
        win32gui.SetWindowPos(
            self._hint_hwnd, 0, 8, hint_y, w - 16, hint_h,
            win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE,
        )
        win32gui.SetWindowPos(
            self._input_hwnd, 0, 8, input_y, w - 16, input_h,
            win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE,
        )
        # ボタン幅はテキストに合わせて計測し、左から順に配置する
        button_items = (
            (self._stack_hwnd, "Stack/追加"),
            (self._run_now_hwnd, "Run now/即実行"),
            (self._clear_hwnd, "Clear/消去"),
            (self._quit_hwnd, "Quit/終了"),
        )
        button_widths = []
        for hwnd, text in button_items:
            hdc = win32gui.GetDC(hwnd)
            try:
                font = win32gui.SendMessage(hwnd, win32con.WM_GETFONT, 0, 0)
                old_font = None
                if font:
                    old_font = win32gui.SelectObject(hdc, font)
                try:
                    sz = win32gui.GetTextExtentPoint32(hdc, text)
                    button_widths.append(sz[0] + 16)
                finally:
                    if old_font is not None:
                        win32gui.SelectObject(hdc, old_font)
            finally:
                win32gui.ReleaseDC(hwnd, hdc)
        bx = 8
        for (hwnd, _), bw in zip(button_items, button_widths):
            win32gui.SetWindowPos(
                hwnd, 0, bx, buttons_y, bw, buttons_h,
                win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE,
            )
            bx += bw + 4
        win32gui.SetWindowPos(
            self.hwnd, 0, x, y, total_w, total_h,
            win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE,
        )

    def _refresh(self) -> None:
        if self.hwnd is None:
            return
        status = self.app.queue.status()
        if status.running is not None:
            win32gui.SetWindowText(
                self._status_hwnd, f"実行中: {describe_item(status.running)}"
            )
        else:
            queued_text = (
                f"待機中({len(status.queued)}件)" if status.queued else "待機中"
            )
            win32gui.SetWindowText(self._status_hwnd, queued_text)
        lines = [f"- {describe_item(item)}" for item in status.queued]
        if len(lines) > 8:
            lines = [f"... 他{len(lines) - 8}件"] + lines[-8:]
        win32gui.SetWindowText(
            self._queue_hwnd, "\n".join(lines) or "(キューなし)"
        )
        self._layout()

    def _proc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_COMMAND:
            control_id = wparam & 0xFFFF
            if control_id == _ID_STACK:
                self._stack(priority=0)
            elif control_id == _ID_RUN_NOW:
                self._stack(priority=1)
            elif control_id == _ID_CLEAR:
                self.app.clear_queue()
            elif control_id == _ID_QUIT:
                win32gui.PostQuitMessage(0)
            return 0
        if msg == win32con.WM_CLOSE:
            # ウィンドウを閉じない(右クリックで再表示できるようにする)
            win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def _input_proc(self, hwnd, msg, wparam, lparam):
        # 入力フォームで Enter キーは Stack に反映させる
        if msg == win32con.WM_KEYDOWN and wparam == win32con.VK_RETURN:
            self._stack(priority=0)
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)


# ----------------------------------------------------------------------
# トレイアプリ

class TrayApp:
    """トレイアプリのメインクラス。"""

    def __init__(
        self,
        config: Config,
        default_mode: str,
        download_queue=None,
    ):
        self.config = config
        self.default_mode = default_mode
        self._queue = (
            download_queue
            if download_queue is not None
            else DownloadQueue(config)
        )
        # UIスレッドにキュー状態を通知するstdlib queue
        self._ui_queue: queue.Queue = queue.Queue()
        self._toasts: list[ToastWindow] = []
        self._tray_hwnd: int | None = None
        self._tray_icon: int | None = None
        self._control = ControlWindow(self)

    @property
    def queue(self) -> DownloadQueue:
        return self._queue

    # ------------------------------------------------------------------
    # 公開API

    def enqueue_stack(self, text: str, priority: int = 0) -> None:
        """入力テキストから (url, mode) を解析し、キューに追加する。"""
        url, mode = parse_stacked_input(text)
        if not url:
            self._show_toast("YouTube URLを入力してください。")
            return
        mode = mode or self.default_mode
        req = self._queue.enqueue(url, mode, priority=priority)
        label = "即実行しました" if priority else "スタックしました"
        self._show_toast(f"{label}: {describe_item(req)}", req)

    def clear_queue(self) -> None:
        count = self._queue.clear()
        if count:
            self._show_toast(f"キューを消去しました({count}件)")
        else:
            self._show_toast("キューに未処理のものはありません")

    # ------------------------------------------------------------------
    # 内部処理

    def start(self) -> None:
        self._queue.status_callback = self._on_queue_status
        self._create_tray()
        self._control._create()
        _set_timer(self._tray_hwnd, _REFRESH_TIMER_ID, _REFRESH_INTERVAL_MS)
        self._tray_modify_tip(_TIP_IDLE)
        self._queue.start()

    def ui_loop(self) -> None:
        win32gui.PumpMessages()

    def shutdown(self) -> None:
        self._queue.stop()
        if self._tray_hwnd is not None:
            try:
                win32gui.Shell_NotifyIcon(
                    win32gui.NIM_DELETE, (self._tray_hwnd, 1)
                )
            except win32gui.error:
                pass
            win32gui.DestroyWindow(self._tray_hwnd)
            self._tray_hwnd = None
        if self._control.hwnd is not None:
            win32gui.DestroyWindow(self._control.hwnd)
            self._control.hwnd = None
        for toast in self._toasts:
            toast.close()

    def _on_clipboard_download(self) -> None:
        text = get_clipboard_text()
        if not find_youtube_url(text):
            self._show_toast("クリップボードにYouTube URLをコピーしてください。")
            return
        self.enqueue_stack(text)

    def _show_toast(self, text: str, req=None) -> ToastWindow:
        toast = ToastWindow(self, text, req)
        self._toasts.append(toast)
        return toast

    def _on_queue_status(self, status: QueueStatus) -> None:
        # ワーカースレッド -> UIスレッド (UIスレッドは WM_TIMER で drain)
        self._ui_queue.put(status)

    def _drain_events(self) -> None:
        # ステータス適用
        while True:
            try:
                status = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            self._apply_status(status)
        # トースト更新/削除
        running = self._queue.status().running
        for toast in list(self._toasts):
            if not toast.is_alive():
                toast.close()
                self._toasts.remove(toast)
            elif running is not None and toast.req is running:
                toast.update(f"実行中: {describe_item(running)}")

    def _apply_status(self, status: QueueStatus) -> None:
        self._control._refresh()
        if status.running is not None:
            self._tray_modify_tip(_TIP_RUNNING.format(desc=describe_item(status.running)))
        elif status.queued:
            self._tray_modify_tip(_TIP_QUEUED.format(n=len(status.queued)))
        else:
            self._tray_modify_tip(_TIP_IDLE)

    # ------------------------------------------------------------------
    # トレイアイコンの追加とツールチップの更新

    def _create_tray(self) -> None:
        self._tray_proc_ref = self._tray_proc
        _register_window_class(_TRAY_CLASS, self._tray_proc_ref)
        self._tray_hwnd = _create_window(
            _TRAY_CLASS, _TIP_IDLE, 0, 0,
            0, 0, 0, 0, None, 0,
        )
        self._tray_icon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
        flags = win32gui.NIF_MESSAGE | win32gui.NIF_ICON | win32gui.NIF_TIP
        nid = (
            self._tray_hwnd, 1, flags, _TRAY_CALLBACK,
            self._tray_icon, _TIP_IDLE,
        )
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)
        except win32gui.error:
            logger.exception("タスクトレイアイコンの追加に失敗しました。")

    def _tray_modify_tip(self, tip: str) -> None:
        if self._tray_hwnd is None:
            return
        flags = win32gui.NIF_MESSAGE | win32gui.NIF_ICON | win32gui.NIF_TIP
        nid = (
            self._tray_hwnd, 1, flags, _TRAY_CALLBACK,
            self._tray_icon, tip,
        )
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, nid)
        except win32gui.error:
            logger.debug("tray tooltip update failed", exc_info=True)

    def _tray_proc(self, hwnd, msg, wparam, lparam):
        if msg == _TRAY_CALLBACK:
            if lparam == win32con.WM_LBUTTONUP:
                self._on_clipboard_download()
            elif lparam == win32con.WM_RBUTTONUP:
                self._control.show()
            return 1
        if msg == win32con.WM_TIMER:
            self._drain_events()
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)


# ----------------------------------------------------------------------
# エントリポイント

def run_tray(config: Config, default_mode: str) -> int:
    """トレイアプリを起動して終了コードを返す。"""
    if win32gui is None:
        raise RuntimeError(
            "pywin32 がインストールされていないためトレイアプリを起動できません。"
            "`pip install -r requirements.txt` を実行してください。"
        )
    app = TrayApp(config, default_mode)
    try:
        app.start()
        app.ui_loop()
        return 0
    finally:
        app.shutdown()
