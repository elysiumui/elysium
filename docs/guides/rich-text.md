# Rich text

`elysium.text.richtext` is a styled-run document model plus a view widget — the
equivalent of Qt's `QTextDocument`. Use it for help panes, note bodies, release
notes, anything with mixed styling, inline links or images.

## Building a document

A `RichDocument` holds a list of items. `add_text` appends a styled `Run`;
`add` appends any item (`Run`, `Image`, `Break`). Run style fields: `bold`,
`italic`, `underline`, `size`, `color`, `family`, `link`.

```python
from elysium.text.richtext import RichDocument, Run, Break

doc = RichDocument(default_size=14)
doc.add_text("Net profit ", bold=True)
doc.add_text("is revenue minus every cost. ")
doc.add_text("Learn more", link="https://docs/profit", underline=True)
doc.add(Break())
doc.add_text("Margins below 20% are flagged.", italic=True,
             color=(0xC4, 0x3C, 0x30, 0xFF))
```

## The view

`RichTextView` lays the document into a width and paints it. Wire `on_link` to
handle link clicks and forward pointer events:

```python
from elysium.text.richtext import RichTextView

view = RichTextView(document=doc, x=16, y=16, w=360, h=240,
                    on_link=lambda url: open_url(url))
view.paint(dl)

view.on_click(mx, my)          # fires on_link when a link is hit
view.content_height()          # measured height (for scroll)
```

The view reflows when its width changes (`relayout()`), so it works inside a
splitter or a resizable drawer.

## See also

- API: [`elysium.text.richtext`](../api/richtext.md)
- [Documents and editing](documents.md)
