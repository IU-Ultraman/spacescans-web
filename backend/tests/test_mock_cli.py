# backend/tests/test_mock_cli.py
import json
import tempfile
import subprocess
import sys
from pathlib import Path

def create_task_dir(tmp_path: Path):
    task_dir = tmp_path / "task-test"
    task_dir.mkdir()
    (task_dir / "output").mkdir()
    config = {
        "version": 1,
        "input_file": "input.csv",
        "buffer": {"shape": "circle", "size": 1000, "unit": "meters"},
        "variables": ["var_a", "var_b"],
        "execution": {"cpu_cores": 2, "memory_limit_gb": 4}
    }
    (task_dir / "config.json").write_text(json.dumps(config))
    csv_content = "pid,startDate,endDate,longitude,latitude\n"
    for i in range(5):
        csv_content += f"P{i},2020-01-01,2020-12-31,-82.35,29.65\n"
    (task_dir / "input.csv").write_text(csv_content)
    return task_dir

def test_mock_cli_runs_to_completion():
    with tempfile.TemporaryDirectory() as tmp:
        task_dir = create_task_dir(Path(tmp))
        result = subprocess.run(
            [sys.executable, "-m", "mock_cli.cli", "run", str(task_dir)],
            capture_output=True, text=True, timeout=30,
            cwd=str(Path(__file__).resolve().parent.parent)
        )
        assert result.returncode == 0
        status = json.loads((task_dir / "status.json").read_text())
        assert status["status"] == "finished"
        assert status["progress"] == 1.0
        assert (task_dir / "output" / "result.csv").exists()
        assert (task_dir / "logs.jsonl").exists()
        logs = (task_dir / "logs.jsonl").read_text().strip().split("\n")
        assert len(logs) >= 2
        for line in logs:
            log = json.loads(line)
            assert "ts" in log
            assert "level" in log
            assert "msg" in log

def test_mock_cli_invalid_config():
    with tempfile.TemporaryDirectory() as tmp:
        task_dir = Path(tmp) / "task-bad"
        task_dir.mkdir()
        (task_dir / "config.json").write_text('{"bad": true}')
        result = subprocess.run(
            [sys.executable, "-m", "mock_cli.cli", "run", str(task_dir)],
            capture_output=True, text=True, timeout=10,
            cwd=str(Path(__file__).resolve().parent.parent)
        )
        status = json.loads((task_dir / "status.json").read_text())
        assert status["status"] == "error"
