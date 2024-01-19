from inspect import currentframe
from typing import Any, Dict, Optional

from rodi.typings import AnyCallable


def inject(
    globalsns: Optional[Dict[str, Any]] = None, localns: Optional[Dict[str, Any]] = None
) -> AnyCallable:
    """
    Marks a class or a function as injected. This method is only necessary if the class
    uses locals and the user uses Python >= 3.10, to bind the function's locals to the
    factory.
    """
    if localns is None or globalsns is None:
        frame = currentframe()
        try:
            if localns is None:
                localns = frame.f_back.f_locals  # type: ignore
            if globalsns is None:
                globalsns = frame.f_back.f_globals  # type: ignore
        finally:
            del frame

    def decorator(f: AnyCallable) -> AnyCallable:
        f._locals = localns
        f._globals = globalsns
        return f

    return decorator
