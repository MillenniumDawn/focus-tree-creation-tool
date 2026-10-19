# Wheel redraw coalescing (#324)

Each wheel event immediately updates zoom and its pointer-anchored offset, then
requests the existing 16 ms VIEW frame. Pending SCENE/FOCUS_LIST channels merge
normally. Clamped zoom events request nothing. Event bursts render the latest
view once rather than repeatedly rebuilding intermediate views. Tradeoff: up to
one scheduled frame of visual latency; no claim about OS compositor FPS.

```sh
# Use a private Xvfb display only; never a desktop user's DISPLAY.
DISPLAY=:99 python scripts/bench_focus_wheel.py --repo /path/to/checkout \
  --fixture /path/to/Millennium-Dawn/common/national_focus/05_usa.txt \
  --out /tmp/wheel.json
pytest tests/test_canvas_tk.py
```

Seven fresh-root samples, 776 USA focuses, 1200x800, 12 alternating events,
unchanged parsed models and uncontrolled OS caches: median handler + final frame
111.37 -> 15.49 ms; patched handlers alone 0.12 ms. All final view and focus item
coordinates equal baseline. This harness flushes the queued frame explicitly to
measure rendering work separately from the 16 ms scheduling wait. The regression
test exercises actual wheel events, changing pointer positions, pending SCENE
work, one queued callback, and zoom clamps.
