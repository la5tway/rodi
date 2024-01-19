from inspect import isawaitable
from typing import Any, Optional, Sequence

from rodi.context import ActivationScope
from rodi.typings import AnyType, InternalProviderFull, Key


class InstanceProvider:
    __slots__ = ("instance",)

    def __init__(self, instance: Any):
        self.instance = instance

    def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        return self.instance


class SingletonFactoryTypeProvider:
    __slots__ = ("_type", "factory", "instance")

    def __init__(self, _type: Optional[AnyType], factory: InternalProviderFull):
        self._type = _type
        self.factory = factory
        self.instance = None

    def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        if self.instance is None:
            self.instance = self.factory(context, parent_type)
        return self.instance


class AsyncSingletonFactoryTypeProvider(SingletonFactoryTypeProvider):
    async def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        if self.instance is None:
            self.instance = await self.factory(context, parent_type)
        return self.instance


class SingletonTypeProvider:
    __slots__ = ("_type", "_instance")

    def __init__(self, _type: AnyType):
        self._type = _type
        self._instance = None

    def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        if self._instance is None:
            self._instance = self._type()
        return self._instance


class SingletonArgsTypeProvider:
    __slots__ = ("_type", "_instance", "_args_callbacks")

    def __init__(self, _type: AnyType, args_callbacks: Sequence[InternalProviderFull]):
        self._type = _type
        self._args_callbacks = args_callbacks
        self._instance = None

    def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        if self._instance is None:
            self._instance = (
                self._type(*[fn(context, self._type) for fn in self._args_callbacks])
                if self._args_callbacks
                else self._type()
            )

        return self._instance


class AsyncSingletonTypeProvider(SingletonArgsTypeProvider):
    async def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        if self._instance is None:
            args = []
            for fn in self._args_callbacks:
                value = fn(context, self._type)
                if isawaitable(value):
                    value = await value
                args.append(value)
            self._instance = self._type(*args)
        return self._instance


class AsyncSingletonTypeProviderExplicit(SingletonArgsTypeProvider):
    async def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        if self._instance is None:
            args = [await fn(context, self._type) for fn in self._args_callbacks]
            self._instance = self._type(*args) if args else self._type()
        return self._instance


class SingletonContextManagerFactoryTypeProvider:
    __slots__ = ("_type", "factory", "instance")

    def __init__(self, _type: Optional[AnyType], factory: InternalProviderFull):
        self._type = _type
        self.factory = factory
        self.instance = None

    def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        if self.instance is None:
            self.instance = context.stack.enter_context(
                self.factory(context, parent_type)
            )
        return self.instance


class AsyncSingletonContextManagerFactoryTypeProvider(
    SingletonContextManagerFactoryTypeProvider
):
    async def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        if self.instance is None:
            self.instance = await context.astack.enter_async_context(
                self.factory(context, parent_type)
            )
        return self.instance
