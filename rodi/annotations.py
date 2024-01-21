from typing import Any, Dict, get_type_hints

from rodi.exceptions import FactoryMissingContextException
from rodi.typings import AnyCallable


def get_factory_annotations_or_throw(factory: AnyCallable) -> Dict[str, Any]:
    factory_locals = getattr(factory, "_locals", None)
    factory_globals = getattr(factory, "_globals", None)

    if factory_locals is None:
        raise FactoryMissingContextException(factory)

    return get_type_hints(factory, globalns=factory_globals, localns=factory_locals)
