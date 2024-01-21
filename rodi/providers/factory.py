from inspect import isawaitable, iscoroutinefunction
from typing import Any, Mapping

from rodi.constants import ServiceLifeStyle
from rodi.context import ActivationScope, ResolutionContext
from rodi.resolvers.factory import FactoryResolver
from rodi.typings import AnyCallable, AnyType, InternalProviderFull


def get_annotations_type_provider(  # noqa: C901
    concrete_type: AnyType,
    resolvers: Mapping[str, AnyCallable],
    life_style: ServiceLifeStyle,
    resolver_context: ResolutionContext,
) -> InternalProviderFull:
    is_async = False
    is_all_async = True

    for resolver in resolvers.values():
        if iscoroutinefunction(resolver):
            is_async = True
        else:
            is_all_async = False

    if not resolvers:

        def factory(context: ActivationScope, parent_type: AnyType) -> Any:
            instance = concrete_type()
            for name, resolver in resolvers.items():
                setattr(instance, name, resolver(context, parent_type))
            return instance

    elif is_all_async:

        async def factory(context: ActivationScope, parent_type: AnyType) -> Any:
            instance = concrete_type()
            for name, resolver in resolvers.items():
                value = await resolver(context, parent_type)
                setattr(instance, name, value)
            return instance
    elif is_async:

        async def factory(context: ActivationScope, parent_type: AnyType) -> Any:
            instance = concrete_type()
            for name, resolver in resolvers.items():
                value = resolver(context, parent_type)
                if isawaitable(value):
                    value = await value
                setattr(instance, name, value)
            return instance

    else:

        def factory(context: ActivationScope, parent_type: AnyType) -> Any:
            instance = concrete_type()
            for name, resolver in resolvers.items():
                setattr(instance, name, resolver(context, parent_type))
            return instance

    return FactoryResolver(concrete_type, factory, life_style)(resolver_context)
