from inspect import isawaitable
from typing import Any, Sequence

from rodi.context import ActivationScope
from rodi.typings import AnyType, InternalProviderFull, Key


class ArgsTypeProvider:
    __slots__ = ("_type", "_args_callbacks")

    def __init__(self, _type: AnyType, args_callbacks: Sequence[InternalProviderFull]):
        self._type = _type
        self._args_callbacks = args_callbacks

    def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        return self._type(*[fn(context, self._type) for fn in self._args_callbacks])


class AsyncArgsTypeProvider(ArgsTypeProvider):
    async def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        args = []
        for fn in self._args_callbacks:
            value = fn(context, self._type)
            if isawaitable(value):
                value = await value
            args.append(value)
        return self._type(*args) if args else self._type()


class AsyncArgsTypeProviderExplicit(ArgsTypeProvider):
    async def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        args = [await fn(context, self._type) for fn in self._args_callbacks]
        return self._type(*args) if args else self._type()


class FactoryTypeProvider:
    __slots__ = ("_type", "factory")

    def __init__(self, _type: AnyType, factory: InternalProviderFull):
        self._type = _type
        self.factory = factory

    def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        return self.factory(context, parent_type)


class AsyncFactoryTypeProvider(FactoryTypeProvider):
    async def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        return await self.factory(context, parent_type)


class TypeProvider:
    __slots__ = ("_type",)

    def __init__(self, _type: AnyType):
        self._type = _type

    def __call__(self, context: ActivationScope, parent_type: Key):
        return self._type()


class ContextManagerFactoryTypeProvider:
    __slots__ = ("_type", "factory")

    def __init__(self, _type: AnyType, factory: InternalProviderFull):
        self._type = _type
        self.factory = factory

    def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        return context.stack.enter_context(self.factory(context, parent_type))


class AsyncContextManagerFactoryTypeProvider(ContextManagerFactoryTypeProvider):
    async def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        return await context.astack.enter_async_context(
            self.factory(context, parent_type)
        )
