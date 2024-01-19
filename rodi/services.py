import sys
from asyncio import iscoroutinefunction
from inspect import (
    Signature,
    _empty,  # type: ignore
    isawaitable,
)
from typing import Any, Dict, Optional, TypeVar, cast

from rodi.annotations import get_factory_annotations_or_throw
from rodi.common import Dependency, class_name
from rodi.constants import SENTINEL
from rodi.context import ActivationScope
from rodi.exceptions import CannotResolveTypeException, OverridingServiceException
from rodi.typings import (
    AnyCallable,
    AnyType,
    InternalProviderFull,
    Key,
    KeyT,
)

T = TypeVar("T")


class Services:
    """
    Provides methods to activate instances of classes, by cached activator functions.
    """

    __slots__ = ("_map", "_executors")

    def __init__(self, services_map: Optional[Dict[Key, InternalProviderFull]] = None):
        if services_map is None:
            services_map = {}
        self._map = services_map
        self._executors = {}

    def __contains__(self, item: Key):
        return item in self._map

    def __getitem__(self, item: Key) -> Any:
        return self.get(item)

    def __setitem__(self, key: Key, value: Any):
        self.set(key, value)

    def set(self, new_type: Key, value: Any):
        """
        Sets a new service of desired type, as singleton.
        This method exists to increase interoperability of Services class (with dict).

        :param new_type:
        :param value:
        :return:
        """
        type_name = class_name(new_type)
        if new_type in self._map or (
            not isinstance(new_type, str) and type_name in self._map
        ):
            raise OverridingServiceException(self._map[new_type], new_type)

        def resolver(context: ActivationScope, parent_type: Key):
            return value

        self._map[new_type] = resolver
        if not isinstance(new_type, str):
            self._map[type_name] = resolver

    def get(
        self,
        desired_type: KeyT[T],
        scope: Optional[ActivationScope] = None,
        *,
        default: Optional[T] = SENTINEL,
    ) -> T:
        """
        Gets a service of the desired type, returning an activated instance.

        :param desired_type: desired service type.
        :param context: optional context, used to handle scoped services.
        :return: an instance of the desired type
        """
        if scope is None:
            scope = ActivationScope(self)

        scoped_service = scope.scoped_services.get(desired_type)  # type: ignore

        if scoped_service:
            return cast(T, scoped_service)
        resolver = self._map.get(desired_type)
        if resolver:
            return cast(T, resolver(scope, desired_type))
        if default is not SENTINEL:
            return cast(T, default)
        raise CannotResolveTypeException(desired_type)

    async def aget(
        self,
        desired_type: KeyT[T],
        scope: Optional[ActivationScope] = None,
        *,
        default: Optional[T] = SENTINEL,
    ) -> T:
        result = self.get(desired_type, scope, default=default)
        if isawaitable(result):
            return await result
        return result

    def _get_getter(self, key: str, param: Dependency):
        if param.annotation is _empty:

            def getter(context: ActivationScope) -> Any:
                return self.get(key, context)

        else:

            def getter(context: ActivationScope) -> Any:
                return self.get(param.annotation, context)

        getter.__name__ = f"<getter {key}>"
        return getter

    def get_executor(self, method: AnyCallable) -> AnyCallable:
        sig = Signature.from_callable(method)
        params = {
            key: Dependency(key, value.annotation)
            for key, value in sig.parameters.items()
        }

        if sys.version_info >= (3, 10):  # pragma: no cover
            # Python 3.10
            annotations = get_factory_annotations_or_throw(method)
            for key, value in params.items():
                if key in annotations:
                    value.annotation = annotations[key]

        fns = []

        for key, value in params.items():
            fns.append(self._get_getter(key, value))

        if iscoroutinefunction(method):

            async def async_executor(scoped: Optional[Dict[AnyType | str, Any]] = None):
                async with ActivationScope(self, scoped) as context:
                    return await method(*[fn(context) for fn in fns])

            return async_executor

        def executor(scoped: Optional[Dict[AnyType | str, Any]] = None):
            with ActivationScope(self, scoped) as context:
                return method(*[fn(context) for fn in fns])

        return executor

    def exec(
        self,
        method: AnyCallable,
        scoped: Optional[Dict[AnyType, Any]] = None,
    ) -> Any:
        try:
            executor = self._executors[method]
        except KeyError:
            executor = self.get_executor(method)
            self._executors[method] = executor
        return executor(scoped)
