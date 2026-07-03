# Shelf

The shelf is a horizontal toolbar below the menu bar. It exposes the
most-used commands for the current menu set as one-click buttons, so
you do not need to drill into deep submenus. It is the same idea as
Maya's shelves: per-task, customizable, savable.

![Shelf showing the Modeling, Animation, and Rendering tabs](../assets/interface-shelf.png)

## Shelf tabs

The shelf has one tab per menu set, plus a **Custom** tab for your
own commands.

| Tab | Default contents |
|---|---|
| Modeling | New Skin · Import 3D · Import Image · Landmark tool · Transfer Polar · Transfer BBox · Frame All |
| Animation | Set Key · Auto Key · Graph Editor · Step Frame ← / → · Play |
| Rigging | Create Joint Chain · Bind Skin · IK 2-Bone · Paint Weights |
| FX | Hair · nCloth · Bullet Rigidbody |
| Rendering | Render Selected · Render Quality cycle · Light Directional · Color Space cycle · Export .esk |
| Custom | Empty until you fill it |

Switch tabs with the small dropdown on the left of the shelf or by
pressing F2-F6 (which also switches the menu bar's contents).

## Adding a button

Right-click any menu entry and choose **Add to Shelf**. The shelf
gains a new button with the action's icon. Buttons can be reordered
by drag.

For commands that take parameters (e.g. "Set Render Quality to
Production"), the shelf saves the parameter set with the button.
Repeated clicks re-run the command with the same parameters.

## Custom shelves

Right-click the shelf's empty area and choose **New Shelf…**. Name
it (e.g. "Wing Authoring"), then drag any combination of actions
onto it. Custom shelves save to your user data folder and follow
your account.

## Resetting

`File > Preferences > Reset > Shelf to Defaults` puts the five
built-in shelves back to their ship-day contents. Your Custom shelf
is left alone.

## Hide / show

`Window > Toggle Shelf` hides the shelf entirely. The menu set
switcher moves into the menu bar's right edge when the shelf is
hidden. Some users prefer this for the extra vertical room.
