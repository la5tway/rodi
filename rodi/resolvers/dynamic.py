import sys
from inspect import (
    Signature,
    _empty,  # type: ignore
    isabstract,
    isclass,
    iscoroutinefunction,
)
from typing import TYPE_CHECKING, Any, ClassVar, Dict, Mapping, get_type_hints

from rodi.annotations import get_annotations_type_provider
from rodi.common import (
    Dependency,
    class_name,
    get_obj_locals,
    get_plain_class_factory,
    is_union,
)
from rodi.constants import ServiceLifeStyle
from rodi.context import ResolutionContext
from rodi.exceptions import (
    CannotResolveParameterException,
    CircularDependencyException,
    UnsupportedUnionTypeException,
)
from rodi.providers.scoped import (
    AsyncScopedArgsTypeProvider,
    AsyncScopedArgsTypeProviderExplicit,
    ScopedArgsTypeProvider,
    ScopedTypeProvider,
)
from rodi.providers.singleton import (
    AsyncSingletonTypeProvider,
    AsyncSingletonTypeProviderExplicit,
    SingletonArgsTypeProvider,
    SingletonTypeProvider,
)
from rodi.providers.transient import (
    ArgsTypeProvider,
    AsyncArgsTypeProvider,
    AsyncArgsTypeProviderExplicit,
    TypeProvider,
)
from rodi.resolvers.factory import FactoryResolver
from rodi.typings import AnyType, InternalProviderFull

if TYPE_CHECKING:
    from rodi.container import Container

if sys.version_info >= (3, 8):
    try:
        from typing import _no_init_or_replace_init as _no_init  # type: ignore
    except ImportError:
        from typing import _no_init  # type: ignore


class DynamicResolver:
    __slots__ = ("_concrete_type", "services", "life_style")

    def __init__(
        self,
        concrete_type: AnyType,
        services: "Container",
        life_style: ServiceLifeStyle,
    ):
        assert isclass(concrete_type)
        assert not isabstract(concrete_type)

        self._concrete_type = concrete_type
        self.services = services
        self.life_style = life_style

    @property
    def concrete_type(self) -> AnyType:
        return self._concrete_type

    def _get_resolver(self, desired_type: AnyType, context: ResolutionContext):
        # NB: the following two lines are important to ensure that singletons
        # are instantiated only once per service provider
        # to not repeat operations more than once
        if desired_type in context.resolved:
            return context.resolved[desired_type]

        reg = self.services._map.get(desired_type)  # type: ignore
        assert (
            reg is not None
        ), f"A resolver for type {class_name(desired_type)} is not configured"
        resolver = reg(context)

        # add the resolver to the context, so we can find it
        # next time we need it
        context.resolved[desired_type] = resolver
        return resolver

    def _get_resolvers_for_parameters(
        self,
        concrete_type: AnyType,
        context: ResolutionContext,
        params: Mapping[str, Dependency],
    ) -> tuple[list[InternalProviderFull], bool, bool]:
        fns: list[InternalProviderFull] = []
        services = self.services
        is_async = False
        is_all_async = True

        for param_name, param in params.items():
            if param_name in ("self", "args", "kwargs"):
                continue

            param_type = param.annotation

            if is_union(param_type):
                # NB: we could cycle through possible types using: param_type.__args__
                # Right now Union and Optional types resolution is not implemented,
                # but at least Optional could be supported in the future
                raise UnsupportedUnionTypeException(param_name, concrete_type)

            if param_type is _empty:
                if services.strict:
                    raise CannotResolveParameterException(param_name, concrete_type)

                # support for exact, user defined aliases, without ambiguity
                exact_alias = services._exact_aliases.get(param_name)  # type: ignore

                if exact_alias:
                    param_type = exact_alias
                else:
                    aliases = services._aliases[param_name]  # type: ignore

                    if aliases:
                        assert (
                            len(aliases) == 1
                        ), "Configured aliases cannot be ambiguous"
                        param_type = next(iter(aliases))

            if param_type not in services._map:  # type: ignore
                raise CannotResolveParameterException(param_name, concrete_type)

            param_resolver = self._get_resolver(param_type, context)
            fns.append(param_resolver)
            if iscoroutinefunction(param_resolver.__call__):
                is_async = True
            else:
                is_all_async = False
        return fns, is_async, is_all_async

    def _resolve_by_init_method(self, context: ResolutionContext):  # noqa: C901
        sig = Signature.from_callable(self.concrete_type.__init__)
        params = {
            key: Dependency(key, value.annotation)
            for key, value in sig.parameters.items()
        }

        if sys.version_info >= (3, 10):  # pragma: no cover
            # Python 3.10
            annotations = get_type_hints(
                self.concrete_type.__init__,
                vars(sys.modules[self.concrete_type.__module__]),
                get_obj_locals(self.concrete_type),
            )
            for key, value in params.items():
                if key in annotations:
                    value.annotation = annotations[key]

        concrete_type = self.concrete_type

        if len(params) == 1 and next(iter(params.keys())) == "self":
            if self.life_style == ServiceLifeStyle.SINGLETON:
                return SingletonTypeProvider(concrete_type)

            if self.life_style == ServiceLifeStyle.SCOPED:
                return ScopedTypeProvider(concrete_type)

            return TypeProvider(concrete_type)

        fns, is_async, is_all_async = self._get_resolvers_for_parameters(
            concrete_type, context, params
        )

        if is_all_async:
            if self.life_style == ServiceLifeStyle.SINGLETON:
                return AsyncSingletonTypeProviderExplicit(concrete_type, fns)
            if self.life_style == ServiceLifeStyle.SCOPED:
                return AsyncScopedArgsTypeProviderExplicit(concrete_type, fns)
            return AsyncArgsTypeProviderExplicit(concrete_type, fns)

        if is_async:
            if self.life_style == ServiceLifeStyle.SINGLETON:
                return AsyncSingletonTypeProvider(concrete_type, fns)
            if self.life_style == ServiceLifeStyle.SCOPED:
                return AsyncScopedArgsTypeProvider(concrete_type, fns)
            return AsyncArgsTypeProvider(concrete_type, fns)
        if self.life_style == ServiceLifeStyle.SINGLETON:
            return SingletonArgsTypeProvider(concrete_type, fns)

        if self.life_style == ServiceLifeStyle.SCOPED:
            return ScopedArgsTypeProvider(concrete_type, fns)

        return ArgsTypeProvider(concrete_type, fns)

    def _ignore_class_attribute(self, key: str, value: Any) -> bool:
        """
        Returns a value indicating whether a class attribute should be ignored for
        dependency resolution, by name and value.
        It's ignored if it's a ClassVar or if it's already initialized explicitly.
        """
        is_classvar = getattr(value, "__origin__", None) is ClassVar
        is_initialized = getattr(self.concrete_type, key, None) is not None

        return is_classvar or is_initialized

    def _has_default_init(self):
        init = getattr(self.concrete_type, "__init__", None)

        if init is object.__init__:
            return True

        if sys.version_info >= (3, 8) and init is _no_init:
            return True
        return False

    def _resolve_by_annotations(
        self, context: ResolutionContext, annotations: Dict[str, AnyType]
    ):
        params = {
            key: Dependency(key, value)
            for key, value in annotations.items()
            if not self._ignore_class_attribute(key, value)
        }
        concrete_type = self.concrete_type

        fns = self._get_resolvers_for_parameters(concrete_type, context, params)[0]
        resolvers = {}

        for i, name in enumerate(params.keys()):
            resolvers[name] = fns[i]

        return get_annotations_type_provider(
            self.concrete_type, resolvers, self.life_style, context
        )

    def __call__(self, context: ResolutionContext):
        concrete_type = self.concrete_type

        chain = context.dynamic_chain
        chain.append(concrete_type)

        if self._has_default_init():
            annotations = get_type_hints(
                concrete_type,
                vars(sys.modules[concrete_type.__module__]),
                get_obj_locals(concrete_type),
            )

            if annotations:
                try:
                    return self._resolve_by_annotations(context, annotations)
                except RecursionError as exc:
                    raise CircularDependencyException(chain[0], concrete_type) from exc

            return FactoryResolver(
                concrete_type, get_plain_class_factory(concrete_type), self.life_style
            )(context)

        try:
            return self._resolve_by_init_method(context)
        except RecursionError as exc:
            raise CircularDependencyException(chain[0], concrete_type) from exc
