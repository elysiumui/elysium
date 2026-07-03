# Project Explorer

The Project Explorer occupies the top of the right column. It is
the tree-view answer to "what is in this project?" and switches
between four perspectives via tabs.

![Project Explorer with the Objects tab expanded showing the butterfly tutorial's hierarchy](../assets/interface-project-explorer.png)

## Tabs

| Tab | Shows | Use for |
|---|---|---|
| Objects | Scene graph of placements (Mesh3D / Image / Curve / Light / Camera) | Selection, hierarchy, hide / show, parent / unparent |
| Assets | Files referenced by the project, in groups: Textures, 3D Models, Brushes, Lights, Audio | Find an external asset; reveal in Finder; bundle into `.esk` |
| History | Action log: every undoable change in time order | Undo back to a specific point; bookmark a state |
| Sets | Named collections of placements | Bulk select, hide, render-mask |

## Objects tab

Each row shows an icon (mesh / image / curve / light / camera), the
placement's id, and any markers (lock state, visibility eye, render
mask). Click a row to select; Shift-click to extend selection;
Ctrl-click to toggle.

Right-click a row for:

- Rename
- Duplicate
- Delete
- Parent under… / Unparent
- Convert to (Mesh3D ↔ Image, Curve → Mesh3D, etc.)
- Reveal in View Panel
- Open in Code (jump to paired Python handler)

Expand a row's triangle to see children (a Mesh3D's wing
sub-transforms, an Image's landmark pairs, a Group's contents).

## Assets tab

Lists external file references plus textures baked into the
`.esk`. The top row, `<projectname>.esk · Reveal in Finder`, opens
the bundle folder. Below it, files are grouped by kind:

```
Textures · 3
  textures/butterfly_albedo.png
  textures/butterfly_normal.png
  ../butterfly/iridescentwinged_butterfly.png   ↗ external
3D Models · 1
  _3ds/butterfly.3ds   ↗ external
```

External assets get a ↗ arrow. Click any row to highlight where it
is used in the scene. Drag a row into the View Panel to drop a new
placement instance.

## History tab

A time-ordered list of every action: tool stroke, menu pick, value
edit. Click a row to jump to that state (the rest of the undo
history below is preserved but inactive).

Bookmark a state with the **★** button: useful when you have a
working draft you want to come back to after experimenting.

## Sets tab

A named collection of placement ids. The Designer creates one set
automatically for landmark pairs (`landmarks_butterfly`); you can
create more for your own selections via `Edit > Group Selected…`
or right-click > Add Selection to Set.

Use sets to:

- Bulk hide all the model's helper geometry while you focus on a
  region.
- Apply a render-part mask to a set in one click.
- Animate every placement in a set in sync (the time slider's
  filter dropdown supports filtering by set).

## Search

Press `Cmd+F` (macOS) or `Ctrl+F` (other) with the Project Explorer
focused to fuzzy-search by placement id. Useful when a scene grows
past 50 placements.
