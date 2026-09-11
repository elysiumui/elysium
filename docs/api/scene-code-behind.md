# Python code behind exported scene objects

An animated scene export owns its paired Python source under `code/`. The
runtime creates the transparent application window, then loads that source
with `app` and `win` already available. Saving or exporting parses and copies
source; it does not execute the source. Launching the application executes it.

For an object named Body, the default click hook is `body.click`:

```python
@win.on('body.click')
def body_clicked(event):
    app.paused = not app.paused
    print(event['object_name'], event['source_frame'], flush=True)
```

The event contains `object_id` (the retained entity identity), `object_name`,
`source_frame`, and `position` (logical pixels within the application window).
The hit map comes from the same rendered pose and depth result as its image.
Transparent pixels do not fire object hooks. Renaming an object changes its
derived hook unless an explicit hook is set in the object's properties.

Handlers can take one event argument or no arguments. A registered handler
replaces the player's default action for that region: a body click normally
reverses the wing cycle, and the configured close object normally quits. The
close region handles its press immediately and never starts a drag. Other
object clicks dispatch on release when the pointer has not become a drag.
Space continues to pause/resume the application clock.

Use the supplied `app` and `win` instead of creating another application or
window at module scope. Existing standalone startup can be guarded by
`if __name__ == '__main__':`. Newly scaffolded handlers use a guard that also
accepts an injected window. An unguarded top-level App/window/run startup is
rejected before rendering the export, with an actionable error.

Save As and animated Export copy static local Python imports, including package
initializers and relative imports. The saved `code_file` path is relative to the
project. Build App asks PyInstaller to analyze the entry module so its imports
are included in the standalone application. The source remains available beside
the runtime assets. Package and module filenames must be Python identifiers.
Third-party dependencies must be installed in the build environment. Dynamic
imports and non-Python data dependencies may need explicit packaging; they are
not automatically inferred by the source-copy helper.

This runtime presents exported frames. Python handlers can control application
behavior, including pause and quit; editing a retained 3D mesh at runtime is not
provided by this frame player. This desktop Python contract does not establish
website-object execution.
