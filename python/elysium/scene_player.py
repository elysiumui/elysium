"""Run Designer-exported animated .esk scenes as transparent desktop applications."""

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image


class SceneAnimation:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.data = json.loads((self.path / "scene-animation.json").read_text())
        if self.data.get("schema_version") != 1 or self.data.get("fps") != 60:
            raise ValueError("Unsupported scene animation schema or fps")
        self.size = self.data["size"]
        self.scale = self.data["asset_scale"]
        self.frames = self.data["frames"]
        self.deploy_count = self.data["deploy_frames"]
        if (
            not isinstance(self.size, int)
            or not 64 <= self.size <= 1024
            or self.scale not in (1, 2)
        ):
            raise ValueError("Invalid scene animation dimensions")
        if (
            not 1 <= self.deploy_count <= len(self.frames)
            or len(self.frames) != self.deploy_count + self.data["idle_frames"]
        ):
            raise ValueError("Invalid scene frame count")
        for frame in self.frames:
            for field in ("src", "close_src"):
                source = (self.path / frame[field]).resolve()
                if not source.is_relative_to(self.path) or not source.is_file():
                    raise ValueError("Missing or out-of-bundle scene asset")
        # Exercise the canonical .esk loader as part of normal application startup.
        from . import load_skin

        self.skin = load_skin(str(self.path))
        self._masks = {}

    def masks(self, index):
        if index in self._masks:
            return self._masks[index]
        frame = self.frames[index]
        with Image.open(self.path / frame["src"]) as img:
            body = np.asarray(img.convert("RGBA"))[:, :, 3] >= 128
        with Image.open(self.path / frame["close_src"]) as img:
            close = np.asarray(img.convert("L")) >= 128
        if (
            body.shape != (self.size * self.scale, self.size * self.scale)
            or close.shape != body.shape
        ):
            raise ValueError("Frame masks do not match the declared dimensions")
        if len(self._masks) >= 4:
            self._masks.pop(next(iter(self._masks)))
        self._masks[index] = (body, close)
        return body, close

    def hit(self, index, cursor):
        if cursor is None:
            return False, False
        x, y = (int(v * self.scale) for v in cursor)
        if not 0 <= x < self.size * self.scale or not 0 <= y < self.size * self.scale:
            return False, False
        body, close = self.masks(index)
        return bool(body[y, x]), bool(close[y, x])


def run(path):
    import elysium as ely
    from elysium import anim
    from elysium._native import _native as native

    asset = SceneAnimation(path)
    app = ely.App(title=asset.skin.name, identifier="dev.elysium.authored-scene")
    win = app.window(
        transparent=True, title_bar=False, resizable=False, initial_size=(asset.size, asset.size)
    )
    win.set_has_shadow(False)
    win.set_window_level(3)
    started = app.playback_time
    state = {
        "running": True,
        "last_press": win.press_count,
        "drag": None,
        "wing_offset": 0.0,
        "pose": 0.0,
        "last": started,
        "position": None,
        "last_index": None,
        "flight_offset": 0.0,
    }
    clock = anim.AnimationClock()

    def tick():
        if not state["running"]:
            return
        now = app.playback_time
        state["last"] = now
        monitor = state.get("monitor") or win.monitor
        if not monitor:
            return
        state["monitor"] = monitor
        # Monitor and window APIs both use logical coordinates.
        wx, wy, ww, wh = (monitor[k] for k in ("work_x", "work_y", "work_width", "work_height"))
        size = asset.size
        travel = ww + size
        elapsed = now - started
        if state["position"] is None:
            state["position"] = (wx - size, wy + (wh - size) * 0.45)
        # Ping-pong the authored deployment poses continuously during flight.
        # A body click reverses direction without jumping to another pose.
        duration = max((asset.deploy_count - 1) / 60, 0.001)
        hold = asset.data["idle_frames"] / 60
        period = 2 * duration + hold
        phase = (elapsed + state["wing_offset"]) % period
        if phase < duration:
            state["pose"] = phase / duration
        elif phase < duration + hold:
            state["pose"] = 1.0
        else:
            state["pose"] = (period - phase) / duration
        index = round(state["pose"] * (asset.deploy_count - 1))
        if duration <= phase < duration + hold:
            index = asset.deploy_count + min(
                asset.data["idle_frames"] - 1, int((phase - duration) * 60)
            )
        cursor, press, held = win.cursor_position, win.press_count, win.mouse_pressed
        if press != state["last_press"]:
            state["last_press"] = press
            origin = win.left_press_position or cursor
            body, close = asset.hit(index, origin)
            if close:
                state["running"] = False
                app.quit()
                return
            if body:
                state["drag"] = {"origin": origin, "position": state["position"], "moved": False}
        drag = state["drag"]
        if drag is not None:
            if cursor:
                ox, oy = win.outer_position
                gx, gy = ox + cursor[0], oy + cursor[1]
                start_x, start_y = (
                    drag["position"][0] + drag["origin"][0],
                    drag["position"][1] + drag["origin"][1],
                )
                if math.hypot(gx - start_x, gy - start_y) >= 4:
                    drag["moved"] = True
                if drag["moved"]:
                    state["position"] = (
                        max(wx, min(wx + ww - size, gx - drag["origin"][0])),
                        max(wy, min(wy + wh - size, gy - drag["origin"][1])),
                    )
            if not held:
                if not drag["moved"]:
                    reverse_phase = (
                        period - state["pose"] * duration
                        if phase < duration + hold
                        else state["pose"] * duration
                    )
                    state["wing_offset"] = reverse_phase - elapsed
                state["flight_offset"] = state["position"][0] - (wx - size + elapsed / 3 * travel)
                state["drag"] = None
        else:
            x = wx - size + (elapsed / 3 * travel + state["flight_offset"]) % travel
            y = state["position"][1]
            state["position"] = (x, y)
        win.set_outer_position(*(round(v) for v in state["position"]))
        frame = asset.frames[index]
        if index != state["last_index"]:
            win.set_hit_test_path(frame["hit_path"])
            state["last_index"] = index
        dl = native.DisplayList()
        dl.clear(0, 0, 0, 0)
        dl.draw_image_file(str(asset.path / frame["src"]), 0, 0, size, size)
        win.publish_display_list(dl)

    anim.run_animation_thread(clock, tick, target_hz=60, running=lambda: state["running"])
    app.run()
    state["running"] = False
