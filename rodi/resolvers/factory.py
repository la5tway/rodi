from inspect import (
    isasyncgenfunction,
    iscoroutinefunction,
    isgeneratorfunction,
)
from typing import Optional, Union

from rodi.constants import ServiceLifeStyle
from rodi.context import ResolutionContext
from rodi.providers.scoped import (
    AsyncScopedContextManagerFactoryTypeProvider,
    AsyncScopedFactoryTypeProvider,
    ScopedContextManagerFactoryTypeProvider,
    ScopedFactoryTypeProvider,
)
from rodi.providers.singleton import (
    AsyncSingletonContextManagerFactoryTypeProvider,
    AsyncSingletonFactoryTypeProvider,
    SingletonContextManagerFactoryTypeProvider,
    SingletonFactoryTypeProvider,
)
from rodi.providers.transient import (
    AsyncContextManagerFactoryTypeProvider,
    AsyncFactoryTypeProvider,
    ContextManagerFactoryTypeProvider,
    FactoryTypeProvider,
)
from rodi.typings import AnyType, AsyncInternalProviderFull, InternalProviderFull


class FactoryResolver:
    __slots__ = ("concrete_type", "factory", "params", "life_style")

    def __init__(
        self,
        concrete_type: Optional[AnyType],
        factory: Union[InternalProviderFull, AsyncInternalProviderFull],
        life_style: ServiceLifeStyle,
    ):
        self.factory = factory
        self.concrete_type = concrete_type
        self.life_style = life_style

    def __call__(  # noqa: C901
        self, context: ResolutionContext
    ) -> Union[InternalProviderFull, AsyncInternalProviderFull]:
        factory = self._unwrap(self.factory)
        if isasyncgenfunction(factory):
            if self.life_style is ServiceLifeStyle.SINGLETON:
                return AsyncSingletonContextManagerFactoryTypeProvider(
                    self.concrete_type, self.factory
                )
            if not self.concrete_type:
                raise ValueError("Concrete type is not set")
            if self.life_style is ServiceLifeStyle.SCOPED:
                return AsyncScopedContextManagerFactoryTypeProvider(
                    self.concrete_type, self.factory
                )
            return AsyncContextManagerFactoryTypeProvider(
                self.concrete_type, self.factory
            )
        if iscoroutinefunction(factory):
            if self.life_style is ServiceLifeStyle.SINGLETON:
                return AsyncSingletonFactoryTypeProvider(
                    self.concrete_type, self.factory
                )
            if not self.concrete_type:
                raise ValueError("Concrete type is not set")
            if self.life_style is ServiceLifeStyle.SCOPED:
                return AsyncScopedFactoryTypeProvider(self.concrete_type, self.factory)
            return AsyncFactoryTypeProvider(self.concrete_type, self.factory)
        if isgeneratorfunction(factory):
            if self.life_style is ServiceLifeStyle.SINGLETON:
                return SingletonContextManagerFactoryTypeProvider(
                    self.concrete_type, self.factory
                )
            if not self.concrete_type:
                raise ValueError("Concrete type is not set")
            if self.life_style is ServiceLifeStyle.SCOPED:
                return ScopedContextManagerFactoryTypeProvider(
                    self.concrete_type, self.factory
                )
            return ContextManagerFactoryTypeProvider(self.concrete_type, self.factory)
        if self.life_style == ServiceLifeStyle.SINGLETON:
            return SingletonFactoryTypeProvider(self.concrete_type, self.factory)
        if not self.concrete_type:
            raise ValueError("Concrete type is not set")
        if self.life_style == ServiceLifeStyle.SCOPED:
            return ScopedFactoryTypeProvider(self.concrete_type, self.factory)

        return FactoryTypeProvider(self.concrete_type, self.factory)

    def _unwrap(
        self, factory: Union[InternalProviderFull, AsyncInternalProviderFull]
    ) -> Union[InternalProviderFull, AsyncInternalProviderFull]:
        while hasattr(factory, "factory"):  # type: ignore
            factory = factory.factory  # type: ignore
        return factory
