# Forms & validation

A form is a set of labelled, validated fields with a sensible focus order and a
submit action. Elysium gives you editable widgets ([`TextField`](../api/text.md),
the [data-entry widgets](../api/dataentry.md)), [validators and masks](../api/text.md),
and one [`InputRouter`](../api/input.md) that delivers keys, IME, and clipboard
to whichever field has focus.

## Build the fields

```python
from elysium.components import TextField
from elysium.components.dataentry import SpinBox, DateEdit, EditableComboBox
from elysium.text import IntValidator, Mask
import datetime as dt

name  = TextField(x=20, y=20, w=300, h=44, label="Name", focus_id="name")
email = TextField(x=20, y=76, w=300, h=44, label="Email", focus_id="email")
phone = TextField(x=20, y=132, w=300, h=44, label="Phone",
                  mask=Mask("(000) 000-0000"), focus_id="phone")
age   = SpinBox(x=20, y=188, w=120, h=40, focus_id="age",
                value=18, minimum=0, maximum=120)
role  = EditableComboBox(x=160, y=188, w=160, h=40, focus_id="role",
                         items=["Engineer", "Researcher", "Designer"])
born  = DateEdit(x=20, y=240, w=160, h=40, focus_id="born", date=dt.date(2000, 1, 1))
```

## Validators and masks

A validator gates what a field accepts as you type; a mask enforces a fixed
shape. Both come from `elysium.text`.

```python
from elysium.text import IntValidator, DoubleValidator, RegexValidator, Mask

qty   = TextField(label="Qty", validator=IntValidator(1, 999).validate)
price = TextField(label="Price", validator=DoubleValidator(0.0, 1e6, decimals=2).validate)
sku   = TextField(label="SKU", validator=RegexValidator(r"[A-Z]{3}-\d{4}").validate)
zip_  = TextField(label="ZIP", mask=Mask("00000"))
```

`validate(text)` returns `Acceptable`, `Intermediate` (a valid prefix — keep
typing), or `Invalid` (rejected).

## Focus order and the router

Register the focusable fields once; `router.tick()` each frame routes typing,
Tab/Shift-Tab navigation, IME composition, and Cmd/Ctrl+C/X/V to the focused
field. Document order is the Tab order.

```python
router = win.input_router()
router.set_widgets([name, email, phone, age, role, born])
router.focus_widget("name")
# each frame, after the window has polled:
router.tick()
```

## Submit

Read `.value` off each field on submit; gate on validators if you kept
references to them.

```python
def submit(name, email, age):
    if not name.value or "@" not in email.value:
        return None
    return {"name": name.value, "email": email.value, "age": age.value}
```

## Test it headlessly

```python
from elysium.testing import UiHarness

h = UiHarness([name, email, age])
h.focus("name").type("Ada")
h.key("Tab").type("ada@example.com")
assert h.find("name").value == "Ada"
assert h.find("email").value == "ada@example.com"
```

See [CRUD app](crud-app.md) to feed a validated form into a table, and
[Dialogs](dialogs.md) to collect a single value in a modal.
