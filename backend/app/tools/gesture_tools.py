from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from backend.app.tools.registry import ToolDefinition, ToolRegistry
from backend.app.tools.safety import (
    bounded_number,
    require_confirmation,
    require_optional_dependency,
    require_platform,
)


@dataclass(slots=True)
class GestureState:
    running: bool = False
    mode: str = "cursor_click"
    camera_index: int = 0
    frames: int = 0
    clicks: int = 0
    started_at: float | None = None
    last_error: str = ""


@dataclass(slots=True)
class GestureRuntime:
    _state: GestureState = field(default_factory=GestureState)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _stop: threading.Event = field(default_factory=threading.Event)
    _ready: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            elapsed = time.monotonic() - self._state.started_at if self._state.started_at else 0.0
            return {
                "running": self._state.running,
                "mode": self._state.mode,
                "camera_index": self._state.camera_index,
                "frames_processed": self._state.frames,
                "clicks": self._state.clicks,
                "elapsed_seconds": round(elapsed, 1),
                "last_error": self._state.last_error or None,
            }

    def start(
        self,
        *,
        mode: str,
        camera_index: int,
        pinch_threshold: float,
        smoothing: float,
        max_runtime_seconds: float,
    ) -> dict[str, Any]:
        with self._lock:
            if self._state.running:
                return {"started": False, "reason": "already_running", **self.snapshot_unlocked()}
            self._state = GestureState(
                running=True,
                mode=mode,
                camera_index=camera_index,
                started_at=time.monotonic(),
            )
            self._stop.clear()
            self._ready.clear()
            self._thread = threading.Thread(
                target=self._run,
                kwargs={
                    "mode": mode,
                    "camera_index": camera_index,
                    "pinch_threshold": pinch_threshold,
                    "smoothing": smoothing,
                    "max_runtime_seconds": max_runtime_seconds,
                },
                name="arix-gesture-control",
                daemon=True,
            )
            self._thread.start()
        self._ready.wait(timeout=5)
        snapshot = self.snapshot()
        if snapshot["last_error"]:
            raise RuntimeError(str(snapshot["last_error"]))
        if not snapshot["running"]:
            raise RuntimeError("Gesture tracking stopped before the camera became ready")
        return {
            "started": True,
            **snapshot,
            "safety": "Move the pointer to a screen corner or call stop to end gesture control.",
        }

    def snapshot_unlocked(self) -> dict[str, Any]:
        elapsed = time.monotonic() - self._state.started_at if self._state.started_at else 0.0
        return {
            "running": self._state.running,
            "mode": self._state.mode,
            "camera_index": self._state.camera_index,
            "frames_processed": self._state.frames,
            "clicks": self._state.clicks,
            "elapsed_seconds": round(elapsed, 1),
            "last_error": self._state.last_error or None,
        }

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=3)
        snapshot = self.snapshot()
        return {"stopped": not snapshot["running"], **snapshot}

    def _fail(self, message: str) -> None:
        with self._lock:
            self._state.last_error = message[:500]
            self._state.running = False
        self._ready.set()

    def _run(
        self,
        *,
        mode: str,
        camera_index: int,
        pinch_threshold: float,
        smoothing: float,
        max_runtime_seconds: float,
    ) -> None:
        capture: Any = None
        hands: Any = None
        try:
            cv2 = require_optional_dependency("cv2", "pip install opencv-python")
            mediapipe = require_optional_dependency("mediapipe", "pip install mediapipe")
            pyautogui = require_optional_dependency("pyautogui", "pip install pyautogui")
            pyautogui.FAILSAFE = True
            screen_width, screen_height = pyautogui.size()
            capture = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
            if not capture.isOpened():
                raise RuntimeError(f"Could not open webcam index {camera_index}")
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            hands = mediapipe.solutions.hands.Hands(
                static_image_mode=False,
                max_num_hands=1,
                model_complexity=0,
                min_detection_confidence=0.65,
                min_tracking_confidence=0.65,
            )
            self._ready.set()
            filtered_x = screen_width / 2
            filtered_y = screen_height / 2
            pinch_down = False
            last_click = 0.0
            deadline = time.monotonic() + max_runtime_seconds
            while not self._stop.is_set() and time.monotonic() < deadline:
                ok, frame = capture.read()
                if not ok:
                    time.sleep(0.03)
                    continue
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = hands.process(rgb)
                with self._lock:
                    self._state.frames += 1
                if not result.multi_hand_landmarks:
                    pinch_down = False
                    continue
                landmarks = result.multi_hand_landmarks[0].landmark
                index_tip = landmarks[8]
                thumb_tip = landmarks[4]
                target_x = max(0, min(screen_width - 1, index_tip.x * screen_width))
                target_y = max(0, min(screen_height - 1, index_tip.y * screen_height))
                filtered_x += (target_x - filtered_x) * smoothing
                filtered_y += (target_y - filtered_y) * smoothing
                pyautogui.moveTo(int(filtered_x), int(filtered_y), duration=0)
                if mode == "cursor_click":
                    distance = math.hypot(index_tip.x - thumb_tip.x, index_tip.y - thumb_tip.y)
                    now = time.monotonic()
                    is_pinched = distance <= pinch_threshold
                    if is_pinched and not pinch_down and now - last_click >= 0.45:
                        pyautogui.click()
                        last_click = now
                        with self._lock:
                            self._state.clicks += 1
                    pinch_down = is_pinched
        except Exception as error:
            self._fail(str(error) or type(error).__name__)
            return
        finally:
            if hands is not None:
                hands.close()
            if capture is not None:
                capture.release()
            with self._lock:
                self._state.running = False
            self._ready.set()


_GESTURES = GestureRuntime()


async def gesture_control(
    action: str,
    mode: str = "cursor_click",
    camera_index: int = 0,
    pinch_threshold: float = 0.055,
    smoothing: float = 0.28,
    max_runtime_seconds: float = 900,
    confirmed: bool = False,
) -> dict[str, Any]:
    require_platform("Windows")
    if action == "status":
        return {"action": action, **_GESTURES.snapshot()}
    if action == "stop":
        return {"action": action, **_GESTURES.stop()}
    if action != "start":
        raise ValueError("action must be start, status, or stop")
    require_confirmation("allow webcam hand tracking to control the pointer", confirmed)
    if mode not in {"cursor", "cursor_click"}:
        raise ValueError("mode must be cursor or cursor_click")
    selected_camera = int(bounded_number(camera_index, minimum=0, maximum=10, field="camera_index"))
    threshold = bounded_number(pinch_threshold, minimum=0.02, maximum=0.15, field="pinch_threshold")
    smooth = bounded_number(smoothing, minimum=0.05, maximum=1, field="smoothing")
    runtime = bounded_number(max_runtime_seconds, minimum=10, maximum=3_600, field="max_runtime_seconds")
    return {
        "action": action,
        **_GESTURES.start(
            mode=mode,
            camera_index=selected_camera,
            pinch_threshold=threshold,
            smoothing=smooth,
            max_runtime_seconds=runtime,
        ),
    }


async def close_gesture_runtime() -> None:
    _GESTURES.stop()


def register_gesture_tools(registry: ToolRegistry) -> None:
    registry.register(ToolDefinition(
        name="gesture_control",
        description="Start, inspect, or stop guarded Windows webcam hand tracking. Cursor mode follows the index fingertip; cursor_click also maps a thumb-index pinch to one debounced click. Starting requires explicit confirmation and automatically stops at the bounded runtime.",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["start", "status", "stop"]},
                "mode": {"type": "string", "enum": ["cursor", "cursor_click"], "default": "cursor_click"},
                "camera_index": {"type": "integer", "minimum": 0, "maximum": 10, "default": 0},
                "pinch_threshold": {"type": "number", "minimum": 0.02, "maximum": 0.15, "default": 0.055},
                "smoothing": {"type": "number", "minimum": 0.05, "maximum": 1, "default": 0.28},
                "max_runtime_seconds": {"type": "number", "minimum": 10, "maximum": 3600, "default": 900},
                "confirmed": {"type": "boolean", "default": False},
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        handler=gesture_control,
    ))
