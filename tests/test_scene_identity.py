from copy import deepcopy
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest
from elysium import scene_identity
from elysium.aether.session import Session


@dataclass
class Entity:
    name: str = "Cube"
    value: int = 2
    entity_id: str = field(default_factory=scene_identity.new_id)


def session_with(placements):
    session = object.__new__(Session)
    session.designer = SimpleNamespace(placements=placements)
    session._id_table, session._rev_id_table = {}, {}
    return session


def test_command_after_rollback_edits_live_object_and_id_survives_restart():
    original = Entity()
    session = session_with([original])
    ident = session.id_for(original)
    restored = deepcopy(original)
    session.designer.placements = [restored]
    session.lookup(ident).value = 5
    assert restored.value == 5
    assert original.value == 2
    restarted = session_with([deepcopy(restored)])
    assert restarted.id_for(restarted.designer.placements[0]) == ident
    assert restarted.lookup(ident).value == 5


def test_deleted_identity_does_not_alias_new_object_with_same_name():
    original = Entity()
    session = session_with([original])
    ident = session.id_for(original)
    session.designer.placements = [Entity(name=ident)]
    with pytest.raises(KeyError):
        session.lookup(ident)


def test_duplicate_identity_is_rejected():
    original = Entity()
    with pytest.raises(ValueError, match="duplicate"):
        scene_identity.validate([original, deepcopy(original)])


@pytest.mark.parametrize("value", ["", "p1", "entity:invalid", 42])
def test_invalid_serialized_identity_is_rejected(value):
    with pytest.raises(ValueError, match="invalid"):
        scene_identity.parse(value)
