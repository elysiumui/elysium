"""Portable copies of paired Python source and its static local imports.

Source is parsed, never imported or executed while saving a project. Third-party
packages and dynamically constructed imports are not copied by this helper.
"""
import ast
from pathlib import Path
import shutil


def source_path(value, project):
    if not value:
        return None
    path = Path(value).expanduser()
    return (path if path.is_absolute() else Path(project)/path).resolve()


def copy_source(value, project, destination):
    source = source_path(value, project)
    if source is None:
        return ''
    if not source.is_file():
        raise ValueError(f'Paired Python file is missing: {source}')
    # Include the containing package root so relative imports retain meaning.
    root = source.parent
    while (root/'__init__.py').is_file():
        root = root.parent
    pending, files = [source], set()

    def add_module(parts):
        if not parts: return
        path = root.joinpath(*parts)
        for candidate in (path.with_suffix('.py'), path/'__init__.py'):
            if candidate.is_file():
                pending.append(candidate)
                for i in range(1,len(parts)):
                    init=root.joinpath(*parts[:i])/'__init__.py'
                    if init.is_file(): pending.append(init)

    while pending:
        path=pending.pop().resolve()
        if path in files: continue
        if not path.is_relative_to(root):
            raise ValueError('A local Python import resolves outside the paired source root')
        files.add(path)
        try:
            tree=ast.parse(path.read_text(encoding='utf-8'),filename=str(path))
        except (SyntaxError,UnicodeError) as exc:
            raise ValueError(f'Cannot copy paired Python source: {path.name}: {exc}') from exc
        relative=path.relative_to(root)
        package=relative.parts[:-1]
        # Copy package initializers even when the entry has no imports.
        for i in range(1,len(package)+1):
            init=root.joinpath(*package[:i])/'__init__.py'
            if init.is_file():pending.append(init)
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                for alias in node.names:add_module(alias.name.split('.'))
            elif isinstance(node,ast.ImportFrom):
                prefix=package[:len(package)-node.level+1] if node.level else ()
                if node.level > len(package):
                    raise ValueError(f'Relative import escapes package in {path.name}')
                parts=(*prefix,*(node.module.split('.') if node.module else ()))
                add_module(parts)
                for alias in node.names:
                    if alias.name!='*':add_module((*parts,alias.name))
    target=Path(destination)/'code'
    for path in sorted(files):
        out=target/path.relative_to(root)
        out.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,out)
    return (Path('code')/source.relative_to(root)).as_posix()
