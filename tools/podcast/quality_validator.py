#!/usr/bin/env python3
"""
Podcast Audio Quality Validator

Pre-flight checks before publishing:
- Detects clipping (peaks above -1.0 dBFS)
- Finds long silences (>2 seconds)
- Checks for sudden volume spikes
- Validates duration matches expected
"""

import sys
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Tuple

# Add repo root to path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


class QualityIssue:
    """Represents a quality issue found during validation."""

    SEVERITY_ERROR = "ERROR"
    SEVERITY_WARNING = "WARNING"
    SEVERITY_INFO = "INFO"

    def __init__(self, severity: str, issue_type: str, message: str, timestamp: float = None):
        self.severity = severity
        self.issue_type = issue_type
        self.message = message
        self.timestamp = timestamp

    def __str__(self):
        prefix = "❌" if self.severity == self.SEVERITY_ERROR else "⚠️" if self.severity == self.SEVERITY_WARNING else "ℹ️"
        time_str = f" @ {int(self.timestamp//60)}:{int(self.timestamp%60):02d}" if self.timestamp else ""
        return f"{prefix} [{self.severity}] {self.issue_type}: {self.message}{time_str}"


def check_clipping(audio_file: Path, threshold_db: float = -1.0) -> List[QualityIssue]:
    """
    Check for audio clipping (peaks above threshold).

    Args:
        audio_file: Path to audio file
        threshold_db: Peak threshold in dB (default: -1.0 dBFS)

    Returns:
        List of quality issues found
    """
    issues = []

    # Use ffmpeg volumedetect to get peak level
    cmd = [
        "ffmpeg",
        "-i", str(audio_file),
        "-af", "volumedetect",
        "-f", "null",
        "-"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    # Parse output for max_volume
    for line in result.stderr.split("\n"):
        if "max_volume:" in line:
            # Format: "[Parsed_volumedetect_0 @ 0x...] max_volume: -X.X dB"
            parts = line.split("max_volume:")
            if len(parts) > 1:
                max_vol_str = parts[1].strip().replace(" dB", "")
                try:
                    max_vol = float(max_vol_str)
                    if max_vol > threshold_db:
                        issues.append(QualityIssue(
                            QualityIssue.SEVERITY_ERROR,
                            "CLIPPING",
                            f"Peak level {max_vol:.1f} dB exceeds safe threshold ({threshold_db} dB). Audio may be clipped."
                        ))
                except ValueError:
                    pass

    return issues


def check_silence(audio_file: Path, silence_threshold_db: int = -50, min_duration: float = 2.0,
                  expected_outro_duration: float = None, total_duration: float = None) -> List[QualityIssue]:
    """
    Detect long periods of silence.

    Args:
        audio_file: Path to audio file
        silence_threshold_db: Volume threshold for silence (default: -50 dB)
        min_duration: Minimum silence duration to flag (default: 2.0s)
        expected_outro_duration: Expected music outro duration (to ignore)
        total_duration: Total audio duration (to identify outro silence)

    Returns:
        List of quality issues found
    """
    issues = []

    # Use ffmpeg silencedetect
    cmd = [
        "ffmpeg",
        "-i", str(audio_file),
        "-af", f"silencedetect=noise={silence_threshold_db}dB:d={min_duration}",
        "-f", "null",
        "-"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    # Parse silence periods
    silence_starts = []
    for line in result.stderr.split("\n"):
        if "silence_start:" in line:
            parts = line.split("silence_start:")
            if len(parts) > 1:
                try:
                    timestamp = float(parts[1].strip())
                    silence_starts.append(timestamp)
                except ValueError:
                    pass
        elif "silence_duration:" in line:
            parts = line.split("silence_duration:")
            if len(parts) > 1 and silence_starts:
                try:
                    duration = float(parts[1].strip())
                    start_time = silence_starts[-1]

                    # Skip if this is the expected music outro silence
                    is_outro = (expected_outro_duration and total_duration and
                               start_time > total_duration - expected_outro_duration - 10)

                    if not is_outro:
                        issues.append(QualityIssue(
                            QualityIssue.SEVERITY_WARNING,
                            "LONG_SILENCE",
                            f"Silent period of {duration:.1f}s detected",
                            timestamp=start_time
                        ))
                except ValueError:
                    pass

    return issues


def check_volume_consistency(audio_file: Path) -> List[QualityIssue]:
    """
    Check for sudden volume spikes or inconsistencies.

    Uses LUFS measurements to detect problematic sections.

    Returns:
        List of quality issues found
    """
    issues = []

    # Get loudness stats
    cmd = [
        "ffmpeg",
        "-i", str(audio_file),
        "-af", "ebur128=framelog=verbose",
        "-f", "null",
        "-"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    # Look for LRA (Loudness Range) in output
    for line in result.stderr.split("\n"):
        if "LRA:" in line:
            parts = line.split("LRA:")
            if len(parts) > 1:
                lra_str = parts[1].strip().split()[0]
                try:
                    lra = float(lra_str)
                    # LRA > 15 indicates significant volume variation
                    if lra > 15:
                        issues.append(QualityIssue(
                            QualityIssue.SEVERITY_WARNING,
                            "VOLUME_VARIATION",
                            f"High loudness range ({lra:.1f} LU). Volume may be inconsistent."
                        ))
                except ValueError:
                    pass

    return issues


def validate_duration(audio_file: Path, expected_duration: float, tolerance: float = 5.0) -> List[QualityIssue]:
    """
    Validate audio duration matches expected length.

    Args:
        audio_file: Path to audio file
        expected_duration: Expected duration in seconds
        tolerance: Acceptable difference in seconds

    Returns:
        List of quality issues found
    """
    issues = []

    # Get actual duration
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_file)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

    try:
        actual_duration = float(result.stdout.strip())
        diff = abs(actual_duration - expected_duration)

        if diff > tolerance:
            issues.append(QualityIssue(
                QualityIssue.SEVERITY_WARNING,
                "DURATION_MISMATCH",
                f"Duration {int(actual_duration)}s differs from expected {int(expected_duration)}s by {int(diff)}s"
            ))
    except ValueError:
        issues.append(QualityIssue(
            QualityIssue.SEVERITY_ERROR,
            "DURATION_CHECK_FAILED",
            "Could not determine audio duration"
        ))

    return issues


def validate_episode(episode_id: str, auto_fix: bool = False) -> Tuple[bool, List[QualityIssue]]:
    """
    Run all quality checks on an episode.

    Args:
        episode_id: Episode ID (e.g., sololaw-030)
        auto_fix: Attempt to auto-fix issues (not yet implemented)

    Returns:
        (passed, issues) - True if validation passed, list of issues found
    """
    import yaml

    config_path = REPO_ROOT / "agents" / "podcast" / "args" / "podcast.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    episodes_base = Path(config["paths"]["episodes_dir"])

    # Find episode directory
    if episode_id.count("-") >= 2 and episode_id.split("-")[0].isdigit():
        parts = episode_id.split("-", 2)
        podcast_name = parts[2]
        episode_dir = episodes_base / podcast_name / episode_id
    else:
        podcast_name, ep_num = episode_id.split("-", 1)
        episode_dir = episodes_base / config["podcasts"][podcast_name]["name"] / ep_num

    # Load episode state for expected duration
    state_file = episode_dir / "state.json"
    expected_duration = None
    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)
            expected_duration = state.get("actual_duration_seconds")
            # Add outro duration
            outro = config["audio"].get("music_outro_seconds", 0)
            if expected_duration:
                expected_duration += outro

    audio_file = episode_dir / "mixed_final.mp3"
    if not audio_file.exists():
        return False, [QualityIssue(
            QualityIssue.SEVERITY_ERROR,
            "FILE_NOT_FOUND",
            f"Audio file not found: {audio_file}"
        )]

    print(f"🔍 Validating audio quality for {episode_id}...")
    print(f"   File: {audio_file.name} ({audio_file.stat().st_size / 1024 / 1024:.1f} MB)")

    # Get actual duration for outro detection
    from subprocess import run
    duration_cmd = run([
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_file)
    ], capture_output=True, text=True, timeout=10)

    try:
        actual_duration = float(duration_cmd.stdout.strip())
    except:
        actual_duration = None

    # Get expected outro duration from config
    outro_duration = config["audio"].get("music_outro_seconds", 0)

    all_issues = []

    # Run all checks
    all_issues.extend(check_clipping(audio_file))
    all_issues.extend(check_silence(audio_file, expected_outro_duration=outro_duration, total_duration=actual_duration))
    all_issues.extend(check_volume_consistency(audio_file))

    if expected_duration:
        all_issues.extend(validate_duration(audio_file, expected_duration))

    # Report results
    print()
    if not all_issues:
        print("✅ All quality checks passed!")
        return True, []

    errors = [i for i in all_issues if i.severity == QualityIssue.SEVERITY_ERROR]
    warnings = [i for i in all_issues if i.severity == QualityIssue.SEVERITY_WARNING]

    print(f"📋 Found {len(errors)} error(s) and {len(warnings)} warning(s):\n")
    for issue in all_issues:
        print(f"   {issue}")

    passed = len(errors) == 0
    return passed, all_issues


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Validate podcast audio quality")
    parser.add_argument("--episode-id", required=True, help="Episode ID (e.g., sololaw-030)")
    parser.add_argument("--auto-fix", action="store_true", help="Attempt to auto-fix issues")

    args = parser.parse_args()

    passed, issues = validate_episode(args.episode_id, args.auto_fix)

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
