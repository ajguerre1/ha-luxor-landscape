"""The guard that would have prevented the incident this integration was designed around.

On 2026-09-09 a method-existence probe posted empty JSON bodies to twelve endpoint names on a live
controller, on the assumption that a request missing its required fields would be rejected. Nine
were. Three were not: `IlluminateAll`, `ExtinguishAll` and `GroupListDelete` take no required
fields, so there was nothing to be missing and the probe *was* the command. All 65 landscape lights
went to full and back off, and every group's colour assignment was destroyed.

These tests are written before the platforms that will use the client, and they assert the two
properties that make that unrepeatable from inside this integration:

1. A method outside the allowlist never reaches the wire.
2. An empty body never reaches a method that has required fields.

Both are asserted by inspecting what the session received, not by trusting a return value. A guard
that has never refused anything cannot be told from one that is incapable of refusing, so every
test here has a positive case that reaches the wire and a negative case that does not.
"""

from __future__ import annotations

import pytest
from luxor import (
    ALLOWED_METHODS,
    ALLOWED_READ_METHODS,
    ALLOWED_WRITE_METHODS,
    DENIED_METHODS,
    PARAMETERLESS_METHODS,
    REQUIRED_FIELDS,
    EmptyBodyError,
    LuxorClient,
    MethodNotAllowedError,
)

#: The one that caused the damage. Named separately so a future edit to DENIED_METHODS that
#: dropped it would fail here rather than silently widen the surface.
THE_DESTRUCTIVE_ONE = "IlluminateAll"


async def test_illuminate_all_is_refused_and_never_sent(client, session):
    """The specific method that wiped 65 groups' colour."""
    with pytest.raises(MethodNotAllowedError) as err:
        await client.request(THE_DESTRUCTIVE_ONE)
    assert session.sent == [], "a denied method reached the wire"
    # The refusal has to say why, or someone reads it as a gap and adds the method.
    assert "Colr 0" in str(err.value)


async def test_illuminate_all_would_still_be_destructive_if_it_got_through(session):
    """The disarmed control.

    Without this, the test above proves only that *something* raised. Driving the simulator
    directly shows the guard is standing in front of a real hazard: the double reproduces the
    measured side effect, so a broken guard would produce a broken fixture state.
    """
    before = {n: g["Colr"] for n, g in session.groups.items()}
    assert any(colr != 0 for colr in before.values())

    session.post("http://192.0.2.10/IlluminateAll.json", json={})

    after = {n: g["Colr"] for n, g in session.groups.items()}
    assert all(colr == 0 for colr in after.values())
    assert all(g["Inten"] == 75 for g in session.groups.values())
    assert after != before


@pytest.mark.parametrize("method", sorted(DENIED_METHODS))
async def test_every_denied_method_is_refused(client, session, method):
    with pytest.raises(MethodNotAllowedError):
        await client.request(method, {"anything": 1})
    assert session.sent == []


async def test_an_unknown_method_is_refused_rather_than_probed(client, session):
    """A method nobody has classified is refused, not tried.

    This is the case the incident was: finding out whether a method exists by calling it. On this
    controller that is not a question, because a method with no required parameters executes.
    """
    with pytest.raises(MethodNotAllowedError):
        await client.request("SomeMethodNobodyHasClassified", {"x": 1})
    assert session.sent == []


async def test_denied_and_allowed_do_not_overlap():
    assert not (ALLOWED_METHODS & DENIED_METHODS.keys())


async def test_every_allowed_method_is_read_or_write():
    assert ALLOWED_READ_METHODS | ALLOWED_WRITE_METHODS == ALLOWED_METHODS
    assert not (ALLOWED_READ_METHODS & ALLOWED_WRITE_METHODS)


async def test_parameterless_methods_are_all_allowed():
    """The empty-body exemption cannot name a method the allowlist does not."""
    assert PARAMETERLESS_METHODS <= ALLOWED_METHODS


async def test_required_fields_are_declared_for_every_non_parameterless_method():
    """Anything that is not exempt must declare what it needs.

    Otherwise a method could be allowed, not exempt, and carry no required fields -- which is the
    exact shape of the hole the incident went through.
    """
    for method in ALLOWED_METHODS - PARAMETERLESS_METHODS:
        assert REQUIRED_FIELDS.get(method), f"{method} declares no required fields"


@pytest.mark.parametrize("method", sorted(ALLOWED_METHODS - PARAMETERLESS_METHODS))
async def test_an_empty_body_never_reaches_a_method_that_needs_fields(client, session, method):
    with pytest.raises(EmptyBodyError):
        await client.request(method, {})
    with pytest.raises(EmptyBodyError):
        await client.request(method, None)
    assert session.sent == []


@pytest.mark.parametrize("method", sorted(REQUIRED_FIELDS))
async def test_a_partially_specified_body_is_refused(client, session, method):
    """Dropping one required field is refused, and the message names the field."""
    required = sorted(REQUIRED_FIELDS[method])
    if len(required) < 2:
        pytest.skip(f"{method} has a single required field; covered by the empty-body test")
    dropped = required[0]
    body = dict.fromkeys(required[1:], 1)
    with pytest.raises(EmptyBodyError) as err:
        await client.request(method, body)
    assert dropped in str(err.value)
    assert session.sent == []


@pytest.mark.parametrize("method", sorted(PARAMETERLESS_METHODS))
async def test_a_parameterless_method_may_send_an_empty_body(client, session, method):
    """The positive case.

    Without this the guard could be "refuse everything", which would pass every test above and
    ship an integration that cannot read the group list.
    """
    await client.request(method)
    assert [s.method for s in session.sent] == [method]
    assert session.sent[0].body == {}


async def test_the_client_cannot_be_talked_past_with_a_url(session):
    """The method name is not user input reaching a URL.

    `request` takes a method name and builds the URL itself, so a caller cannot append a path or
    swap the host. Asserted because the alternative -- taking a URL -- is the obvious refactor and
    it would route straight around the allowlist.
    """
    client = LuxorClient("192.0.2.10", session, min_gap=0.0)
    with pytest.raises(MethodNotAllowedError):
        await client.request("GroupListGet/../IlluminateAll")
    assert session.sent == []
