# backend/mock_cli/cli.py
"""Mock CLI pipeline that simulates the SPACESCANS linkage process."""
import json
import sys
import signal
import time
import csv
import random
from pathlib import Path
from datetime import datetime, timezone

cancelled = False

def signal_handler(sig, frame):
    global cancelled
    cancelled = True

signal.signal(signal.SIGTERM, signal_handler)

def write_status(task_dir: Path, status: str, progress: float = 0.0, message: str = "", error: str = ""):
    data = {
        "status": status,
        "progress": progress,
        "message": message,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "pid": None  # will be set below
    }
    if error:
        data["error"] = error
    data["pid"] = __import__("os").getpid()
    (task_dir / "status.json").write_text(json.dumps(data, indent=2))

def append_log(task_dir: Path, level: str, msg: str):
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "level": level, "msg": msg}
    with open(task_dir / "logs.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")

def validate_config(config: dict) -> list[str]:
    errors = []
    if "version" not in config:
        errors.append("Missing 'version' field")
    if "input_file" not in config:
        errors.append("Missing 'input_file' field")
    if "buffer" not in config or "shape" not in config.get("buffer", {}):
        errors.append("Missing or invalid 'buffer' field")
    if "variables" not in config or not isinstance(config.get("variables"), list):
        errors.append("Missing or invalid 'variables' field")
    return errors

def run(task_dir_path: str):
    global cancelled
    task_dir = Path(task_dir_path)

    # Validate config
    config_path = task_dir / "config.json"
    if not config_path.exists():
        write_status(task_dir, "error", error="config.json not found")
        return 1

    config = json.loads(config_path.read_text())
    errors = validate_config(config)
    if errors:
        write_status(task_dir, "error", error="; ".join(errors))
        append_log(task_dir, "error", f"Config validation failed: {'; '.join(errors)}")
        return 1

    input_path = task_dir / config["input_file"]
    if not input_path.exists():
        write_status(task_dir, "error", error=f"Input file not found: {config['input_file']}")
        return 1

    # Read input
    with open(input_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    variables = config["variables"]
    total = len(rows)
    batch_size = max(1, total // 5)
    batches = (total + batch_size - 1) // batch_size

    write_status(task_dir, "running", 0.0, f"Starting linkage for {total} records")
    append_log(task_dir, "info", f"Started linkage task")
    append_log(task_dir, "info", f"Loaded {total} patient records from {config['input_file']}")
    append_log(task_dir, "info", f"Buffer: {config['buffer']['shape']}, {config['buffer']['size']}{config['buffer']['unit']}")
    append_log(task_dir, "info", f"Variables: {', '.join(variables)}")
    exec_opts = config.get("execution", {})
    append_log(task_dir, "info", f"CPU cores: {exec_opts.get('cpu_cores', 'auto')}, Memory: {exec_opts.get('memory_limit_gb', 'auto')}GB")

    # Process in batches
    results = []
    for batch_idx in range(batches):
        if cancelled:
            write_status(task_dir, "cancelled", message="Task cancelled by user")
            append_log(task_dir, "info", "Task cancelled by user")
            return 0

        start = batch_idx * batch_size
        end = min(start + batch_size, total)
        progress = (batch_idx + 1) / batches
        msg = f"Processing batch {batch_idx + 1}/{batches} (records {start + 1}-{end})"

        write_status(task_dir, "running", round(progress, 2), msg)
        append_log(task_dir, "info", msg)

        # Simulate work
        for row in rows[start:end]:
            result_row = dict(row)
            for var in variables:
                result_row[var] = round(random.uniform(0, 100), 4)
            results.append(result_row)

        time.sleep(0.5)  # Simulate processing time

    # Write output
    output_dir = task_dir / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "result.csv"

    if results:
        fieldnames = list(results[0].keys())
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

    write_status(task_dir, "finished", 1.0, f"Completed linkage for {total} records")
    append_log(task_dir, "info", f"Results written to output/result.csv ({len(results)} rows)")
    append_log(task_dir, "info", "Task completed successfully")
    return 0

def main():
    if len(sys.argv) < 3 or sys.argv[1] != "run":
        print("Usage: python -m mock_cli.cli run <task_dir>", file=sys.stderr)
        sys.exit(1)
    sys.exit(run(sys.argv[2]))

if __name__ == "__main__":
    main()
