from pathlib import Path

from background_studio.desktop_app import DesktopJob, runnable_desktop_jobs, unique_output_path


def test_unique_output_path_keeps_existing_results(tmp_path: Path) -> None:
    source = tmp_path / "portrait.photo.png"
    first = unique_output_path(tmp_path, source, "webp")
    first.touch()

    second = unique_output_path(tmp_path, source, "webp")

    assert first.name == "portrait.photo-background-studio.webp"
    assert second.name == "portrait.photo-background-studio-2.webp"


def test_new_file_does_not_requeue_completed_jobs(tmp_path: Path) -> None:
    saved = DesktopJob(tmp_path / "saved.png", False, status="저장됨")
    completed = DesktopJob(tmp_path / "completed.png", False, status="완료")
    pending = DesktopJob(tmp_path / "new.png", False)

    assert runnable_desktop_jobs([saved, completed, pending]) == [pending]
