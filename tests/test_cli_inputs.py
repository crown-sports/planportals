import json

import pytest

from planportals.cli import main
from planportals.demo import demo_scene


@pytest.mark.parametrize("name", ["portals.json", "portals.svg"])
@pytest.mark.parametrize("alias", ["path", "hardlink", "symlink"])
def test_build_keeps_input_scene_before_any_output(tmp_path, capsys, name, alias):
    output = tmp_path / "result"
    output.mkdir()
    source = output / name if alias == "path" else tmp_path / "scene.json"
    _, scene = demo_scene()
    source.write_text(json.dumps(scene.to_dict()))
    target = output / name
    if alias == "hardlink":
        target.hardlink_to(source)
    elif alias == "symlink":
        target.symlink_to(source)
    original = source.read_bytes()
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    with pytest.raises(SystemExit) as error:
        main(["build", "--input", str(source), "--output", str(output)])
    assert error.value.code == 2
    assert source.read_bytes() == original
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before
    assert "choose a different --output directory" in capsys.readouterr().err


@pytest.mark.parametrize("content", [b"", b"PK\x03\x04broken archive"])
def test_build_reports_unreadable_label_archives(tmp_path, capsys, content):
    _, scene = demo_scene()
    source = tmp_path / "input.json"
    source.write_text(json.dumps(scene.to_dict()))
    labels = tmp_path / "openings.npz"
    labels.write_bytes(content)
    output = tmp_path / "result"
    with pytest.raises(SystemExit) as error:
        main(
            [
                "build",
                "--input",
                str(source),
                "--opening-mask",
                str(labels),
                "--door-classes",
                "1",
                "--output",
                str(output),
            ]
        )
    assert error.value.code == 2
    assert not output.exists()
    assert labels.read_bytes() == content
    assert "planportals:" in capsys.readouterr().err
