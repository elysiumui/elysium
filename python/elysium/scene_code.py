"""Load user-authored handlers into an exported scene's existing app/window."""
import ast
import inspect
from pathlib import Path
import importlib.util
import sys


def validate_source(path):
    tree = ast.parse(Path(path).read_text(encoding='utf-8'), filename=str(path))
    for node in tree.body:
        value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign, ast.Expr)) else None
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) and value.func.attr in ('App','window','run'):
            raise ValueError('Paired scene code must use the supplied app and win. Guard standalone startup with if __name__ == "__main__".')


class HandlerWindow:
    """Honor legacy no-argument handlers as well as event-taking handlers."""
    def __init__(self, window):
        self.window = window

    def __getattr__(self, name):
        return getattr(self.window, name)

    def on(self, hook):
        def decorate(fn):
            signature = inspect.signature(fn)
            try:
                signature.bind(None)
            except TypeError:
                signature.bind()
                callback = lambda event: fn()
            else:
                callback = fn
            self.window.subscribe(hook, callback)
            return fn
        return decorate


def load(path, app, window):
    """Execute paired source only when the user launches the application."""
    path = Path(path).resolve()
    validate_source(path)
    # Export owns the code root, including local import dependencies.
    root = path.parent
    while (root/'__init__.py').is_file(): root = root.parent
    sys.path.insert(0, str(root))
    proxy = HandlerWindow(window)
    module_name = '.'.join(path.relative_to(root).with_suffix('').parts)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    module.app, module.win = app, proxy
    previous = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        if module.win is not proxy or module.app is not app:
            raise ValueError('Paired scene code replaced app or win instead of registering handlers')
    except BaseException:
        sys.path.remove(str(root))
        if previous is None: sys.modules.pop(module_name, None)
        else: sys.modules[module_name] = previous
        raise
    # Keep source modules and their root available for later callback imports.
    return vars(module)
