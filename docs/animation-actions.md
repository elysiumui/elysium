# Named animation actions

A scene may retain multiple named actions. The Animation actions command opens the native editor. Each action contains local transform-channel keys, their interpolation and relative Bezier handles, and start/end/FPS/loop timing. Object identity, geometry, materials, hierarchy, static unkeyed values and desktop-flight duration are shared.

Create empty action uses the entered name and range and starts without keys. Duplicate current action copies all current object keys independently into the entered range; it does not retime them. Rename changes the active action's name. Saved clips switches by stable action ID, pausing native playback and evaluating the selected clip at its start. Delete active action is undoable and activates the first remaining action. The last action cannot be deleted. Names are trimmed, case-insensitively unique and limited to 120 characters.

Existing projects need no migration: they expose a synthesized Default action. Reading does not alter a project. The first action mutation creates the library. Placement `keys3d` remains the authoritative active edit buffer, so existing UI, public API, save/reopen and export paths continue to use current authored keys. Reading or changing the library refreshes the active snapshot from that buffer. Inactive actions persist under the window's version-1 `scene_actions` field. Portable project loaders retain this field. Exports render the active action; runtime action blending and switching are separate features.

Switching validates and evaluates the complete candidate before modifying live objects. An inactive action referencing a deleted object rejects activation with the missing IDs; restoring the object or removing the action resolves it. No object is resurrected implicitly. Shared unkeyed transform components keep their current values, as when a channel has no animation curve.

Public tools: `scene.actions_get`, `scene.action_create`, `scene.action_switch`, `scene.action_rename`, `scene.action_remove`. Native changes use one Undo transaction. Key and handle operations use the same active buffer for every action.
