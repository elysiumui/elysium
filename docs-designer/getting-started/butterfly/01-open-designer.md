# Step 1. Open the Designer and create a project

Time: 3 minutes.

## Launch the app

Open Elysium Designer from your Applications folder (macOS), Start menu
(Windows), or your application launcher (Linux). The first launch shows a
splash screen briefly while the GPU pipeline warms up, then drops you into
an empty canvas.

If the Designer was already open, choose `File > New` from the menu bar to
start a fresh project. The keyboard shortcut is `Cmd+N` on macOS or
`Ctrl+N` on Windows and Linux.

## Name the project

The New Project dialog asks for a name and a parent folder. Name the
project `Butterfly` and pick any parent folder you can write to. The
Designer creates a folder called `Butterfly.esk/` on disk; this is the
`.esk` skin bundle you will export at the end of the tutorial.

For the rest of this tutorial, "your project folder" means the
`Butterfly.esk/` folder you just created.

## Verify the layout

After clicking Create you should see:

- An empty canvas in the center of the window.
- The toolbox running down the left edge with seventeen tools.
- The right column showing the Project Explorer at the top, the Channel
  Box in the middle, and a Properties pane at the bottom.
- The menu bar across the top with eighteen menus from File to Help.
- The time slider at the bottom.

If any of these are missing you can restore the default layout from
`Window > Reset to Default Layout`. The
[Interface tour](../../interface/index.md) covers what each panel does in
detail; you can skim it now or come back later.

## Open the Project Explorer

The Project Explorer is the right column's top panel. It has three tabs:
**Objects**, **Assets**, and **Code**. Click the Objects tab if it is not
already active. This panel will track every placement you add to the
scene; the Assets tab will track your imported model and reference image
once you bring them in; the Code tab will surface the paired Python file
that ships event handlers for your skin.

The Project Explorer is empty at this point. That is correct.

## Checkpoint

You should see an empty canvas, a default layout, and the Objects tab of
the Project Explorer selected with no entries beneath it. Your title bar
shows the project name `Butterfly` and the path to its `.esk` folder.

[Continue to chapter 2 >>](02-import-the-monarch-model.md)
