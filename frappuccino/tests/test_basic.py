def test_reference():
    from frappuccino import compare, deserialize_spec

    old = deserialize_spec(open("frappuccino/tests/IPython-7.14.0.json").read())
    new = deserialize_spec(open("frappuccino/tests/IPython-8.0.0.dev.json").read())

    assert compare(old, spec=new) != []
