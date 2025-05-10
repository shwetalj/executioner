import os
import subprocess
import pytest
import sys
from pathlib import Path

CONFIG_DIR = Path(__file__).parent.parent / "config"
EXECUTIONER = Path(__file__).parent.parent / "executioner.py"

# List of (config filename, expected exit code, description)
CONFIG_TESTS = [
    ("basic_test.json", 0, "Basic successful run"),
    ("minimal_job_test.json", 0, "Minimal job definition"),
    ("maximal_job_test.json", 0, "Maximal job definition"),
    ("parallel_test.json", 0, "Parallel execution"),
    ("retry_test.json", 0, "Retry logic"),
    ("failures_test.json", 1, "Failure triggers notification"),
    ("failures_test_array.json", 1, "Failure with array recipients"),
    ("failures_test_comma_string.json", 1, "Failure with comma-separated recipients"),
    ("failures_test_single_string.json", 1, "Failure with single string recipient"),
    ("smtp_invalid_test.json", 1, "Invalid SMTP config"),
    ("invalid_config_missing_fields.json", 1, "Missing required config fields"),
    ("invalid_config_bad_types.json", 1, "Bad types in config"),
    ("plugin_test.json", 0, "Plugin loading (no use)"),
    ("test_pre_post_checks.json", 0, "Pre/post checks"),
    ("shell_commands_test.json", 0, "Shell command execution"),
    ("security_test.json", 1, "Security test (should fail if shell not allowed)"),
    ("missing_deps_test.json", 1, "Missing dependency"),
    ("circular_deps_test.json", 1, "Circular dependency"),
]

@pytest.mark.parametrize("config_file,expected_exit,desc", CONFIG_TESTS)
def test_config_run(config_file, expected_exit, desc, tmp_path):
    """
    Run executioner.py with the given config file and check the exit code.
    """
    config_path = CONFIG_DIR / config_file
    assert config_path.exists(), f"Config file {config_path} does not exist!"
    cmd = [sys.executable, str(EXECUTIONER), "-c", str(config_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(f"\n--- {desc} ---\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    assert result.returncode == expected_exit, f"{desc}: Expected exit {expected_exit}, got {result.returncode}\nSTDERR: {result.stderr}" 