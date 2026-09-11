"""Application playback must pause flight and authored poses together."""

import pytest
from types import SimpleNamespace

import elysium
from elysium import anim, scene_player


def test_clock_uses_paused_application_time(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(anim, "_app_time", lambda: now[0])
    clock = anim.AnimationClock()
    tween = anim.Tween(0.0, 1.0, duration=1, easing="linear").start(clock)
    clock.tick_realtime()
    now[0] = 0.2
    clock.tick_realtime()
    assert abs(tween.value - 0.2) < 1e-8
    for _ in range(10):
        assert clock.tick_realtime() == 0
    assert abs(tween.value - 0.2) < 1e-8
    now[0] = 0.3
    clock.tick_realtime()
    assert abs(tween.value - 0.3) < 1e-8


@pytest.mark.parametrize("loop", [True,False])
def test_flight_cycles_wings_and_same_time_freezes_position_and_pose(monkeypatch, tmp_path, loop):
    from elysium._native import _native

    records, callbacks = [], []
    window = SimpleNamespace(
        press_count=0,
        cursor_position=None,
        mouse_pressed=False,
        monitor={"work_x": 0, "work_y": 25, "work_width": 1300, "work_height": 700},
        set_has_shadow=lambda _: None,
        set_window_level=lambda _: None,
        set_hit_test_path=lambda path: None,
    )
    window.set_outer_position = lambda x, y: setattr(window, "outer_position", (x, y))
    window.publish_display_list = lambda dl: records.append((window.outer_position, dl.index))
    app = SimpleNamespace(playback_time=0, window=lambda **kw: window, quit=lambda: None)
    times = [0, 0.6, 1.2, 1.8, 2.8, 3.4, 3.4, 3.4, 4.0]

    def app_run():
        for t in times:
            app.playback_time = t
            callbacks[0]()

    app.run = app_run
    monkeypatch.setattr(elysium, "App", lambda **kw: app)
    monkeypatch.setattr(
        anim, "run_animation_thread", lambda clock, tick, **kw: callbacks.append(tick)
    )
    asset = SimpleNamespace(
        size=384,
        deploy_count=73,
        path=tmp_path,
        skin=SimpleNamespace(name="Flight"),
        data={"idle_frames": 60, "loop":loop},
        frames=[{"src": str(i), "hit_path": ""} for i in range(133)],
    )
    monkeypatch.setattr(scene_player, "SceneAnimation", lambda _: asset)

    class Display:
        def clear(self, *args):
            pass

        def draw_image_file(self, path, *args):
            self.index = int(path.split("/")[-1])

    monkeypatch.setattr(_native, "DisplayList", Display)
    scene_player.run(tmp_path)
    assert [r[1] for r in records] == ([0, 36, 73, 109, 36, 0, 0, 0, 36] if loop else [0,36,73,109,36,0,0,0,0])
    assert records[5] == records[6] == records[7]
    assert records[0][0] != records[1][0]
    assert records[7][0] != records[8][0]
