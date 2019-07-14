# Frappucino

Freeze your API.

Frappucino allows you during development to make sure you haven't broken API. By
first taking an imprint of your API at one point in time and then compare it to
the current project state. The goal is to warn you when incompatible changes
have been introduces, and list theses.

You could integrate it in you CI to make sure you don't inadvertently break
things.

Example:

```python
# old function
def read(name, *, options=None):
    with open(name. 'rb') as f:
        return process(data)

# new function
def read(name_or_buffer, *, options=None):
    if isinstance(name, str):
        with open(name, 'rb') as f:
            data = f.read()
    else:
        data = name_or_buffer.read()
    return process(data)
```

There is a subtle breakage of API in the above, as you may not remember
positional parameters can be use a keyword arguments. That is to say one of your customer may use:

```python
read(name='dump.csv')
```

Hence changing the _name_ of the positional parameter from `name` to
`name_or_buffer` is a change of API. There are a number of details like this one
where you _may_ end up breaking API without realizing. It's hard to keep track
of this when working on dev branches, unit test may not catch all of that.
Frappuccino is there to help.


# Example:


```
$ source activate astropy==3.2
$ frappuccino astropy astropy.timeseries --save    astropy.json

$ source activate astropy=master
$ frappuccino astropy astropy.timeseries --compare astropy.json

The following signatures differ between versions:

    astropy.time.core.TimeDelta.to
          - astropy.time.core.TimeDelta.to(self, *args, **kwargs)
          + astropy.time.core.TimeDelta.to(self, unit, equivalencies='[]')

    astropy.table.table.Table.add_column
          - astropy.table.table.Table.add_column(self, col, index='None', name='None', rename_duplicate='False', copy='True')
          + astropy.table.table.Table.add_column(self, col, index='None', name='None', rename_duplicate='False', copy='True', default_name='None')

    astropy.table.table.Table.replace_column
          - astropy.table.table.Table.replace_column(self, name, col)
          + astropy.table.table.Table.replace_column(self, name, col, copy='True')
```
