#!/usr/bin/env python3

import os
import shlex
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Set

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node


HELP_TEXT = """
usage: ros2 run driver driver_node [-- SENSORS [OUTPUT_DIR]]

SENSORS (optional, default: all)
    all              Start all available sensors (zed+vn+hesai)
    zed              Start ZED2i camera recording only
    vn               Start VectorNav and rosbag VectorNav topics
    hesai            Start Hesai LiDAR driver and rosbag /lidar_points
    zed+vn           Start ZED2i recording + VectorNav rosbag
    hesai+vn         Start Hesai + VectorNav into one bag (rosbag_lidar+vn)
    zed+hesai+vn     Start all three sensors (LiDAR+VN in rosbag_lidar+vn)

OUTPUT_DIR (optional)
  Path where the session folder will be created.
  Default: ~/ros2_bags/session_<timestamp>

Examples:
  ros2 run driver driver_node
  ros2 run driver driver_node -- zed
    ros2 run driver driver_node -- vn
    ros2 run driver driver_node -- hesai
    ros2 run driver driver_node -- zed+vn
    ros2 run driver driver_node -- hesai+vn
  ros2 run driver driver_node -- all
  ros2 run driver driver_node -- zed ~/.ros2_bags/my_session
  ros2 run driver driver_node -- zed+hesai+vn /data/recordings

Run 'ros2 run driver driver_node -- -h' to show this message.
"""

ALIASES = {
    "all": "all",
    "zed": "zed",
    "zed2i": "zed",
    "hesai": "hesai",
    "vectornav": "vn",
    "vn": "vn",
}


def parse_cli(argv: List[str]) -> tuple[str, str]:
    # Strip any ROS-injected args (everything from --ros-args onward)
    user_args = [
        a
        for a in argv[1:]
        if a != "--" and not a.startswith("__") and not a.startswith("--ros-")
    ]

    if user_args and user_args[0] in ("-h", "--help"):
        print(HELP_TEXT)
        raise SystemExit(0)

    selection = user_args[0] if len(user_args) > 0 else "all"
    output_dir = user_args[1] if len(user_args) > 1 else ""

    return selection, output_dir


def normalize_selection(value: str) -> Set[str]:
    cleaned = value.replace(",", "+").strip().lower()
    if not cleaned:
        cleaned = "all"

    tokens = [tok.strip() for tok in cleaned.split("+") if tok.strip()]
    if not tokens:
        tokens = ["all"]

    normalized = set()
    for token in tokens:
        mapped = ALIASES.get(token)
        if mapped is None:
            raise ValueError(
                f"Unknown sensor '{token}'.\n"
                "Run 'ros2 run driver driver_node -- -h' to see valid options."
            )
        if mapped == "all":
            return {"all"}
        normalized.add(mapped)

    return normalized


class DriverNode(Node):
    def __init__(self, selection: str, output_dir: str) -> None:
        super().__init__("driver_node")
        self._child_processes: dict[str, subprocess.Popen] = {}
        self._start_times: dict[str, float] = {}
        self._vn_bag_timer = None
        self._hesai_bag_timer = None
        self._session_path: str = ""

        normalized = normalize_selection(selection)
        requested = {"zed", "vn", "hesai"} if "all" in normalized else set(normalized)
        start_zed = "zed" in requested
        start_vn = "vn" in requested
        start_hesai = "hesai" in requested
        combine_lidar_vn_bag = start_hesai and start_vn

        if not (start_zed or start_vn or start_hesai):
            raise ValueError(
                "No runnable sensor selected.\n"
                "Run 'ros2 run driver driver_node -- -h' to see valid options."
            )

        session_path = self._resolve_session_path(output_dir)
        self._session_path = session_path
        self.get_logger().info(f"Session output: {session_path}")

        if start_zed:
            zed_cmd = [
                "ros2",
                "run",
                "zed2i",
                "zed2i_node",
                "--ros-args",
                "-p",
                f"output_dir:={session_path}",
            ]
            self._start_process("zed2i", zed_cmd)

        if start_vn:
            self._start_process("vectornav", ["ros2", "launch", "vectornav", "vectornav.launch.py"])
            self._vn_bag_timer = self.create_timer(
                8.0,
                lambda: self._start_vectornav_bag(session_path, include_lidar=combine_lidar_vn_bag),
            )

        if start_hesai:
            self._start_process(
                "hesai_ros_driver",
                ["ros2", "run", "hesai_ros_driver", "hesai_ros_driver_node"],
            )
            if not combine_lidar_vn_bag:
                self._hesai_bag_timer = self.create_timer(
                    5.0,
                    lambda: self._start_hesai_bag(session_path),
                )

        self._poll_timer = self.create_timer(1.0, self._poll_processes)
        self._status_timer = self.create_timer(10.0, self._print_status)

    def _resolve_session_path(self, output_dir: str) -> str:
        if output_dir:
            path = Path(os.path.expanduser(output_dir)).resolve()
            path.mkdir(parents=True, exist_ok=True)
            return str(path)

        base = Path(os.path.expanduser("~/ros2_bags")).resolve()
        base.mkdir(parents=True, exist_ok=True)
        session = base / datetime.now().strftime("session_%Y%m%d_%H%M%S")
        session.mkdir(parents=True, exist_ok=True)
        return str(session)

    def _start_hesai_bag(self, session_path: str) -> None:
        if self._hesai_bag_timer is not None:
            self._hesai_bag_timer.cancel()
            self._hesai_bag_timer = None

        bag_path = os.path.join(session_path, "rosbag_lidar")
        self._start_process(
            "rosbag_lidar",
            [
                "ros2",
                "bag",
                "record",
                "-o",
                bag_path,
                "--compression-mode",
                "file",
                "--compression-format",
                "zstd",
                "/lidar_points",
                "/lidar_imu",
                "/lidar_packets",
            ],
        )

    def _start_vectornav_bag(self, session_path: str, include_lidar: bool = False) -> None:
        if self._vn_bag_timer is not None:
            self._vn_bag_timer.cancel()
            self._vn_bag_timer = None

        if include_lidar:
            bag_name = "rosbag_lidar+vn"
            process_name = "rosbag_lidar_vn"
            topic_regex = "^(/vectornav/.*|/lidar_points|/lidar_imu|/lidar_packets)$"
        else:
            bag_name = "rosbag_vectornav"
            process_name = "rosbag_vectornav"
            topic_regex = "^/vectornav/.*"

        bag_path = os.path.join(session_path, bag_name)
        self._start_process(
            process_name,
            [
                "ros2",
                "bag",
                "record",
                "-o",
                bag_path,
                "--compression-mode",
                "file",
                "--compression-format",
                "zstd",
                "-e",
                topic_regex,
            ],
        )

    def _start_process(self, name: str, command: List[str]) -> None:
        self.get_logger().info("Starting %s: %s" % (name, " ".join(shlex.quote(x) for x in command)))
        process = subprocess.Popen(command, preexec_fn=os.setsid)
        self._child_processes[name] = process
        self._start_times[name] = time.monotonic()

    def _poll_processes(self) -> None:
        for name, process in list(self._child_processes.items()):
            rc = process.poll()
            if rc is None:
                continue
            if rc == 0:
                self.get_logger().info("Process '%s' exited cleanly." % name)
            else:
                self.get_logger().error("Process '%s' exited with code %d." % (name, rc))
            self._child_processes.pop(name, None)
            self._start_times.pop(name, None)

    def _print_status(self) -> None:
        if not self._child_processes:
            return
        now = time.monotonic()
        lines = ["--- Recording status ---"]
        for name, process in self._child_processes.items():
            elapsed = now - self._start_times.get(name, now)
            mins, secs = divmod(int(elapsed), 60)
            lines.append(f"  {name:<22} pid={process.pid}  up={mins:02d}m{secs:02d}s")
        if self._session_path:
            lines.append(f"  output → {self._session_path}")
        self.get_logger().info("\n".join(lines))

    def shutdown(self) -> None:
        if self._vn_bag_timer is not None:
            self._vn_bag_timer.cancel()
            self._vn_bag_timer = None
        if self._hesai_bag_timer is not None:
            self._hesai_bag_timer.cancel()
            self._hesai_bag_timer = None

        if hasattr(self, "_poll_timer"):
            self._poll_timer.cancel()
        if hasattr(self, "_status_timer"):
            self._status_timer.cancel()

        active: dict[str, subprocess.Popen] = {
            name: process
            for name, process in self._child_processes.items()
            if process.poll() is None
        }

        # Signal everyone first so all subprocesses begin shutdown immediately.
        for name, process in active.items():
            if rclpy.ok():
                self.get_logger().info(f"Stopping {name}...")
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGINT)
            except ProcessLookupError:
                pass

        # Wait for graceful exit, then escalate per process if needed.
        for name, process in active.items():
            try:
                process.wait(timeout=6)
                continue
            except subprocess.TimeoutExpired:
                pass
            except Exception:
                continue

            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                process.wait(timeout=3)
                continue
            except subprocess.TimeoutExpired:
                pass
            except ProcessLookupError:
                continue

            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass

        self._child_processes.clear()


def main() -> None:
    selection, output_dir = parse_cli(sys.argv)  # may raise SystemExit(0) for -h

    rclpy.init(args=sys.argv)
    node = None
    try:
        node = DriverNode(selection=selection, output_dir=output_dir)
        rclpy.spin(node)
    except ValueError as exc:
        if node is not None:
            node.get_logger().error(str(exc))
        else:
            print(exc)
        raise SystemExit(2) from exc
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.shutdown()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
