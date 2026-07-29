from pathlib import Path

from background_studio.desktop_app import unique_output_path


def test_unique_output_path_keeps_existing_results(tmp_path: Path) -> None:
    source = tmp_path / "portrait.photo.png"
    first = unique_output_path(tmp_path, source, "webp")
    first.touch()

    second = unique_output_path(tmp_path, source, "webp")

    assert first.name == "portrait.photo-background-studio.webp"
    assert second.name == "portrait.photo-background-studio-2.webp"
