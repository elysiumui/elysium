# How do I load and display an image with rounded corners?

Two paths.

## Easy: use a Card with `background_image`

```json
{
  "id": "art",
  "kind": "card",
  "x": 20, "y": 20, "width": 140, "height": 140,
  "radius": 12,
  "background_image": "assets/cover.jpg"
}
```

The Card placement does the right thing: image fills the
rounded rectangle, clipped to the card's shape.

## DIY: clip and draw

For full control:

```python
import elysium as ely

img = ely.Image.from_path("assets/cover.jpg")

path = ely.Path()
path.rect(20, 20, 140, 140, radius=12)

dl = ely.DisplayList()
dl.clip(path)
dl.draw_image(img, x=20, y=20, w=140, h=140)
window.art_canvas.publish_display_list(dl)
```

`clip(path)` restricts subsequent draws. The image is drawn at
its full size; the clip mask hides anything outside the rounded
rectangle.

See [Rendering](../guides/rendering.md).
