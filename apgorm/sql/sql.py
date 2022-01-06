# MIT License
#
# Copyright (c) 2021 TrigonDev
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import annotations

from collections import UserString
from typing import TYPE_CHECKING, Any, Generic, TypeVar, Union

if TYPE_CHECKING:
    from apgorm.field import BaseField
    from apgorm.types.base_type import SqlType
    from apgorm.types.boolean import Bool

_T = TypeVar("_T", covariant=True)
_SQLT = TypeVar("_SQLT", bound="SqlType", covariant=True)
_CAST_SQLT = TypeVar("_CAST_SQLT", bound="SqlType")
_PARAM = TypeVar("_PARAM")
SQL = Union[
    "BaseField[SqlType[_T], _T, Any]",
    "Block[SqlType[_T]]",
    "Parameter[_T]",
    _T,
]
"""
A type alias that allows for any field, raw sql, parameter.

If used like `SQL[int]`, then it must have a python type of int.
For example:

```
integer: SQL[int] = p(1)  # works
integer: SQL[int] = p(1).cast(BigInt())  # works
integer: SQL[int] = p("hi")  # fails
"""

CASTED = Union[
    "BaseField[_SQLT, Any, Any]",
    "Block[_SQLT]",
]
"""
A type alias that allows for any field or raw sql with a specified
SQL type. For example:

```
bigint: CASTED[BigInt] = p(1).cast(BigInt())  # works
bigint: CASTED[BigInt] = p(1)  # fails
bigint: CASTED[BigInt] = p(1).cast(SmallInt())  # fails
```
"""


def wrap(*pieces: SQL) -> Block:
    """Return the SQL pieces as a Block, wrapping them in parantheses."""

    return Block(*pieces, wrap=True)


def join(joiner: SQL, *values: SQL, wrap: bool = False) -> Block:
    """SQL version of "delim".join(values). For example:

    ```
    join(r(","), value1, value2, value3)
    ```

    Args:
        joiner (SQL): The joiner or deliminator.

    Kwargs:
        wrap (bool): Whether or not to return the result wrapped. Defaults to
        False.
    """

    new_values: list[SQL] = []
    for x, v in enumerate(values):
        new_values.append(v)
        if x != len(values) - 1:
            new_values.append(joiner)
    return Block(*new_values, wrap=wrap)


def or_(*pieces: SQL[bool]) -> Block[Bool]:
    """Shortcut for `join(r("OR"), value1, value2, ...)`."""

    return join(r("OR"), *pieces)


def and_(*pieces: SQL[bool]) -> Block[Bool]:
    """Shortcut for `join(r("AND"), value1, value2, ...)`."""

    return join(r("AND"), *pieces)


def r(string: str) -> Block:
    """Treat the string as raw SQL and return a Block.

    Never, ever, ever wrap user input in `r()`. A good rule of thumb is that
    if you see a call to `r()`, the input should be text in quotes, not a
    variable.

    ```
    r(somevarthatmightbeuserinput)  # bad
    r("some text")  # good
    ```
    """

    return Block(Raw(string))


def p(param: _PARAM) -> Parameter[_PARAM]:
    return Parameter(param)


class Raw(UserString):
    pass


class Parameter(Generic[_T]):
    def __init__(self, value: _T):
        self.value = value


class Comparable:
    def _get_block(self) -> Block:
        raise NotImplementedError

    def _op(self, op: str, other: SQL) -> Block:
        return wrap(self._get_block(), r(op), other)

    def _func(self, func: str) -> Block:
        return wrap(func, wrap(self._get_block()))

    def _rfunc(self, rfunc: str) -> Block:
        return wrap(wrap(self._get_block()), rfunc)

    def not_(self) -> Block[Bool]:
        return self._func("NOT")

    def is_null(self) -> Block[Bool]:
        return self._rfunc("IS NULL")

    def eq(self, other: SQL) -> Block[Bool]:
        return self._op("=", other)

    def neq(self, other: SQL) -> Block[Bool]:
        return self._op("!=", other)

    def lt(self, other: SQL) -> Block[Bool]:
        return self._op("<", other)

    def gt(self, other: SQL) -> Block[Bool]:
        return self._op(">", other)

    def lteq(self, other: SQL) -> Block[Bool]:
        return self._op("<=", other)

    def gteq(self, other: SQL) -> Block[Bool]:
        return self._op(">=", other)

    def cast(self, type_: _CAST_SQLT) -> Block[_CAST_SQLT]:
        return self._op("::", r(type_.sql))


class Block(Comparable, Generic[_SQLT]):
    """Represents a list of raw sql and parameters."""

    def __init__(self, *pieces: SQL | Raw, wrap: bool = False):
        """Create a Block.

        Kwargs:
            wrap (bool): Whether or not to add `( )` around the result.

        Example:
        ```
        sql = Block(r("SELECT"), "Hello, World", r(","), 17)
        sql.render()  # "SELECT $1, $2", ["Hello, World", 17]
        ```
        """

        self._pieces: list[Raw | Parameter] = []

        if len(pieces) == 1 and isinstance(pieces[0], Block):
            block = pieces[0]
            assert isinstance(block, Block)
            self.wrap: bool = block.wrap or wrap
            self._pieces = block._pieces

        else:
            self.wrap = wrap
            for p in pieces:
                if isinstance(p, Comparable):
                    p = p._get_block()
                if isinstance(p, Block):
                    self._pieces.extend(p.get_pieces())
                elif isinstance(p, (Raw, Parameter)):
                    self._pieces.append(p)
                else:
                    self._pieces.append(Parameter(p))

    def _get_block(self) -> Block:
        return self

    def render(self) -> tuple[str, list[Any]]:
        """Return the rendered result of the Block.

        Returns:
            tuple[str, list[Any]]: The raw SQL (as a string) and the list of
            parameters.
        """

        return Renderer().render(self)

    def render_no_params(self) -> str:
        """Convenience function to get the SQL but not the parameters.

        Although it is technically easier to write `.render()[0]`, this is
        cleaner and more obvious to those reading your code.

        Returns:
            str: The sql.
        """

        return self.render()[0]

    def get_pieces(
        self, force_wrap: bool | None = None
    ) -> list[Raw | Parameter]:
        wrap = self.wrap if force_wrap is None else force_wrap
        if wrap:
            return [Raw("("), *self._pieces, Raw(")")]
        return self._pieces

    def __iadd__(self, other: object):
        if isinstance(other, Block):
            self._pieces.extend(other.get_pieces())
        elif isinstance(other, Parameter):
            self._pieces.append(other)
        else:
            raise TypeError(f"Unsupported type {type(other)}")

        return self


class Renderer:
    def __init__(self):
        self._curr_value_id: int = 0

    @property
    def next_value_id(self) -> int:
        self._curr_value_id += 1
        return self._curr_value_id

    def render(self, sql: Block) -> tuple[str, list[Any]]:
        sql_pieces: list[str] = []
        params: list[Any] = []

        for piece in sql.get_pieces(force_wrap=False):
            if isinstance(piece, Raw):
                sql_pieces.append(str(piece))
            else:
                sql_pieces.append(f"${self.next_value_id}")
                params.append(piece.value)

        return " ".join(sql_pieces), params
