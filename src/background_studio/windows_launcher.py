from __future__ import annotations

import os
import socket
import threading
import webbrowser
from tkinter import BOTH, LEFT, Button, Frame, Label, StringVar, Tk, X, messagebox
from typing import Any

from background_studio import __version__


def _available_port() -> int:
    for port in range(8765, 8785):
        with socket.socket() as candidate:
            try:
                candidate.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("8765~8784 포트에서 사용 가능한 로컬 포트를 찾지 못했습니다.")


class Launcher:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title(f"Background Studio Python {__version__}")
        self.root.geometry("560x270")
        self.root.minsize(500, 250)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.status = StringVar(value="로컬 API를 준비하고 있습니다.")
        self.server: Any | None = None
        self.startup_error: str | None = None
        self.port = _available_port()

        header = Frame(self.root, padx=24, pady=20)
        header.pack(fill=X)
        Label(header, text="Background Studio Python", font=("Malgun Gothic", 18, "bold")).pack(
            anchor="w"
        )
        Label(
            header,
            text="이미지·동영상 배경 제거와 고급 편집을 내 PC에서 실행하는 로컬 API",
            fg="#5f6f66",
            font=("Malgun Gothic", 10),
        ).pack(anchor="w", pady=(5, 0))

        body = Frame(self.root, padx=24, pady=12, bg="#f3f6f1")
        body.pack(fill=BOTH, expand=True)
        Label(
            body,
            textvariable=self.status,
            bg="#f3f6f1",
            fg="#174c39",
            font=("Malgun Gothic", 10, "bold"),
            wraplength=500,
            justify=LEFT,
        ).pack(anchor="w", pady=(4, 14))
        Label(
            body,
            text=(
                "API 문서에서 파일과 편집값을 입력해 실행할 수 있습니다. "
                "모델은 첫 처리 때 사용자 캐시에 다운로드됩니다."
            ),
            bg="#f3f6f1",
            fg="#5f6f66",
            font=("Malgun Gothic", 9),
            wraplength=500,
            justify=LEFT,
        ).pack(anchor="w")

        actions = Frame(body, bg="#f3f6f1")
        actions.pack(fill=X, pady=(18, 0))
        self.open_button = Button(
            actions,
            text="API 문서 열기",
            state="disabled",
            command=self.open_docs,
            padx=18,
            pady=8,
        )
        self.open_button.pack(side=LEFT)
        Button(actions, text="종료", command=self.close, padx=18, pady=8).pack(side=LEFT, padx=8)

    def start(self) -> None:
        thread = threading.Thread(target=self._run_server, daemon=True)
        thread.start()
        self.root.after(200, lambda: self._wait_until_started(0))
        self.root.mainloop()

    def _run_server(self) -> None:
        try:
            import uvicorn

            from background_studio.api import app

            config = uvicorn.Config(
                app,
                host="127.0.0.1",
                port=self.port,
                log_level="warning",
                access_log=False,
                log_config=None,
            )
            self.server = uvicorn.Server(config)
            self.server.run()
        except Exception as exc:
            self.startup_error = str(exc)

    def _wait_until_started(self, attempts: int) -> None:
        if self.startup_error:
            messagebox.showerror("Background Studio", self.startup_error)
            self.close()
            return
        if self.server and self.server.started:
            self.status.set(
                f"실행 중 · http://127.0.0.1:{self.port} · 파일은 외부 서버로 전송되지 않습니다."
            )
            self.open_button.configure(state="normal")
            if os.environ.get("BACKGROUND_STUDIO_NO_BROWSER") != "1":
                self.open_docs()
            return
        if attempts >= 300:
            messagebox.showerror("Background Studio", "로컬 API를 시작하지 못했습니다.")
            self.close()
            return
        self.root.after(200, lambda: self._wait_until_started(attempts + 1))

    def open_docs(self) -> None:
        webbrowser.open(f"http://127.0.0.1:{self.port}/docs")

    def close(self) -> None:
        if self.server:
            self.server.should_exit = True
        self.root.destroy()


def main() -> None:
    from background_studio.desktop_app import main as run_desktop

    run_desktop()


if __name__ == "__main__":
    main()
