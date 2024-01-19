import re
from typing import Any, Dict, Optional, Union

from rodi.typings import AnyCallable, AnyType

try:
    from types import UnionType
except ImportError:
    UnionType = None


class Dependency:
    __slots__ = ("name", "annotation")

    def __init__(self, name: str, annotation: AnyType):
        self.name = name
        self.annotation = annotation


def get_obj_locals(obj: Any) -> Optional[Dict[str, Any]]:
    return getattr(obj, "_locals", None)


def class_name(input_type: Any) -> str:
    if input_type in {list, set} and str(  # noqa: E721
        type(input_type) == "<class 'types.GenericAlias'>"
    ):
        # for Python 3.9 list[T], set[T]
        return str(input_type)
    try:
        return input_type.__name__
    except AttributeError:
        # for example, this is the case for List[str], Tuple[str, ...], etc.
        return str(input_type)


def is_union(type_: AnyType) -> bool:
    result = hasattr(type_, "__origin__") and type_.__origin__ is Union
    if result:
        return result
    if UnionType is not None:
        return isinstance(type_, UnionType)
    return False


first_cap_re = re.compile("(.)([A-Z][a-z]+)")
all_cap_re = re.compile("([a-z0-9])([A-Z])")


def to_standard_param_name(name: str):
    value = all_cap_re.sub(r"\1_\2", first_cap_re.sub(r"\1_\2", name)).lower()
    if value.startswith("i_"):
        return "i" + value[2:]
    return value


def get_plain_class_factory(concrete_type: AnyType) -> AnyCallable:
    def factory(*args: Any):
        return concrete_type()

    return factory
