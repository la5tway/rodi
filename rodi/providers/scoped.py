from inspect import isawaitable
from typing import Any, Sequence

from rodi.context import ActivationScope
from rodi.typings import AnyType, InternalProviderFull, Key


class ScopedTypeProvider:
    __slots__ = ("_type",)

    def __init__(self, _type: AnyType):
        self._type = _type

    def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        if self._type in context.scoped_services:
            return context.scoped_services[self._type]

        service = self._type()
        context.scoped_services[self._type] = service
        return service


class ScopedFactoryTypeProvider:
    __slots__ = ("_type", "factory")

    def __init__(self, _type: AnyType, factory: InternalProviderFull):
        self._type = _type
        self.factory = factory

    def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        if self._type in context.scoped_services:
            return context.scoped_services[self._type]

        instance = self.factory(context, parent_type)
        context.scoped_services[self._type] = instance
        return instance


class AsyncScopedFactoryTypeProvider(ScopedFactoryTypeProvider):
    async def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        if self._type in context.scoped_services:
            return context.scoped_services[self._type]

        instance = await self.factory(context, parent_type)
        context.scoped_services[self._type] = instance
        return instance


class ScopedArgsTypeProvider:
    __slots__ = ("_type", "_args_callbacks")

    def __init__(self, _type: AnyType, args_callbacks: Sequence[InternalProviderFull]):
        self._type = _type
        self._args_callbacks = args_callbacks

    def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        if self._type in context.scoped_services:
            return context.scoped_services[self._type]

        service = self._type(*[fn(context, self._type) for fn in self._args_callbacks])
        context.scoped_services[self._type] = service
        return service


class AsyncScopedArgsTypeProvider(ScopedArgsTypeProvider):
    async def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        if self._type in context.scoped_services:
            return context.scoped_services[self._type]

        args = []
        for fn in self._args_callbacks:
            value = fn(context, self._type)
            if isawaitable(value):
                value = await value
            args.append(value)
        service = self._type(*args)
        context.scoped_services[self._type] = service
        return service


class AsyncScopedArgsTypeProviderExplicit(ScopedArgsTypeProvider):
    async def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        if self._type in context.scoped_services:
            return context.scoped_services[self._type]

        args = [await fn(context, self._type) for fn in self._args_callbacks]
        service = self._type(*args)
        context.scoped_services[self._type] = service
        return service


class ScopedContextManagerFactoryTypeProvider:
    __slots__ = ("_type", "factory")

    def __init__(self, _type: AnyType, factory: InternalProviderFull):
        self._type = _type
        self.factory = factory

    def __call__(self, context: ActivationScope, parent_type: Key):
        if self._type in context.scoped_services:
            return context.scoped_services[self._type]

        service = context.stack.enter_context(self.factory(context, parent_type))
        context.scoped_services[self._type] = service
        return service


class AsyncScopedContextManagerFactoryTypeProvider(
    ScopedContextManagerFactoryTypeProvider
):
    async def __call__(self, context: ActivationScope, parent_type: Key):
        if self._type in context.scoped_services:
            return context.scoped_services[self._type]  # type: ignore

        instance = await context.astack.enter_async_context(
            self.factory(context, parent_type)
        )
        context.scoped_services[self._type] = instance  # type: ignore
        return instance
