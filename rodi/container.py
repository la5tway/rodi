from collections import defaultdict
from contextlib import suppress
from inspect import (
    Signature,
    _empty,  # type: ignore
    isabstract,
)
from typing import Any, Dict, Generator, Optional, Set, Tuple, TypeVar

from rodi.annotations import get_factory_annotations_or_throw
from rodi.common import class_name, to_standard_param_name
from rodi.constants import ServiceLifeStyle
from rodi.context import ActivationScope, ResolutionContext
from rodi.exceptions import (
    AbstractNotSupported,
    AliasAlreadyDefined,
    AliasConfigurationError,
    InvalidFactory,
    InvalidOperationInStrictMode,
    MissingTypeException,
    OverridingServiceException,
)
from rodi.resolvers.dynamic import DynamicResolver
from rodi.resolvers.factory import FactoryResolver
from rodi.resolvers.instance import InstanceResolver
from rodi.services import Services
from rodi.typings import (
    AnyCallable,
    AnyType,
    AnyTypeDict,
    InternalProvider,
    InternalProviderFull,
    InternalProviderNoArguments,
    InternalProviderOneArgument,
    Key,
    KeyT,
)

T = TypeVar("T")


class FactoryWrapperNoArgs:
    __slots__ = ("factory",)

    def __init__(self, factory: InternalProviderNoArguments):
        self.factory = factory

    def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        return self.factory()


class FactoryWrapperContextArg:
    __slots__ = ("factory",)

    def __init__(self, factory: InternalProviderOneArgument):
        self.factory = factory

    def __call__(self, context: ActivationScope, parent_type: Key) -> Any:
        return self.factory(context)


class Container:
    """
    Configuration class for a collection of services.
    """

    __slots__ = ("_map", "_aliases", "_exact_aliases", "strict", "_provider")

    def __init__(self, *, strict: bool = False):
        self._map: Dict[AnyType, AnyCallable] = {}
        self._aliases: Dict[str, Set[AnyType]] = defaultdict(set)
        self._exact_aliases: Dict[str, AnyType] = {}
        self._provider: Optional[Services] = None
        self.strict = strict

    def __iter__(self) -> Generator[Tuple[AnyType, AnyCallable], None, None]:
        yield from self._map.items()

    def __contains__(self, key: Any) -> bool:
        return key in self._map

    @property
    def provider(self) -> Services:
        if self._provider is None:
            self._provider = self.build_provider()
        return self._provider

    def register(
        self,
        obj_type: AnyType,
        sub_type: Optional[AnyType] = None,
        instance: Any = None,
        *args: Any,
        **kwargs: Any,
    ) -> "Container":
        """
        Registers a type in this container.
        """
        if instance is not None:
            self.add_instance(instance, declared_class=obj_type)
            return self

        if sub_type is None:
            self._add_exact_transient(obj_type)
        else:
            self.add_transient(obj_type, sub_type)
        return self

    def resolve(
        self,
        obj_type: KeyT[T],
        scope: Optional[ActivationScope] = None,
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        Resolves a service by type, obtaining an instance of that type.
        """
        return self.provider.get(obj_type, scope)  # type: ignore

    async def aresolve(
        self,
        obj_type: KeyT[T],
        scope: Optional[ActivationScope] = None,
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        Resolves a service by type, obtaining an instance of that type.
        """
        return await self.provider.aget(obj_type, scope)  # type: ignore

    def bind_types(
        self,
        obj_type: Any,
        concrete_type: Any = None,
        life_style: ServiceLifeStyle = ServiceLifeStyle.TRANSIENT,
    ):
        with suppress(TypeError):
            assert issubclass(concrete_type, obj_type), (
                f"Cannot register {class_name(obj_type)} for abstract class "
                f"{class_name(concrete_type)}"
            )
        self._bind(obj_type, DynamicResolver(concrete_type, self, life_style))
        return self

    def add_alias(self, name: str, desired_type: AnyType):
        """
        Adds an alias to the set of inferred aliases.

        :param name: parameter name
        :param desired_type: desired type by parameter name
        :return: self
        """
        if self.strict:
            raise InvalidOperationInStrictMode()
        if name in self._aliases or name in self._exact_aliases:
            raise AliasAlreadyDefined(name)
        self._aliases[name].add(desired_type)
        return self

    def add_aliases(self, values: AnyTypeDict):
        """
        Adds aliases to the set of inferred aliases.

        :param values: mapping object (parameter name: class)
        :return: self
        """
        for key, value in values.items():
            self.add_alias(key, value)
        return self

    def set_alias(self, name: str, desired_type: AnyType, override: bool = False):
        """
        Sets an exact alias for a desired type.

        :param name: parameter name
        :param desired_type: desired type by parameter name
        :param override: whether to override existing values, or throw exception
        :return: self
        """
        if self.strict:
            raise InvalidOperationInStrictMode()
        if not override and name in self._exact_aliases:
            raise AliasAlreadyDefined(name)
        self._exact_aliases[name] = desired_type
        return self

    def set_aliases(self, values: AnyTypeDict, override: bool = False):
        """Sets many exact aliases for desired types.

        :param values: mapping object (parameter name: class)
        :param override: whether to override existing values, or throw exception
        :return: self
        """
        for key, value in values.items():
            self.set_alias(key, value, override)
        return self

    def _bind(self, key: AnyType, value: Any) -> None:
        if key in self._map:
            raise OverridingServiceException(key, value)
        self._map[key] = value

        if self._provider is not None:
            self._provider = None

        key_name = class_name(key)

        if self.strict or "." in key_name:
            return

        self._aliases[key_name].add(key)
        self._aliases[key_name.lower()].add(key)
        self._aliases[to_standard_param_name(key_name)].add(key)

    def add_instance(
        self, instance: Any, declared_class: Optional[AnyType] = None
    ) -> "Container":
        """
        Registers an exact instance, optionally by declared class.

        :param instance: singleton to be registered
        :param declared_class: optionally, lets define the class used as reference of
        the singleton
        :return: the service collection itself
        """
        self._bind(
            declared_class if declared_class else instance.__class__,
            InstanceResolver(instance),
        )
        return self

    def add_singleton(
        self, base_type: AnyType, concrete_type: Optional[AnyType] = None
    ) -> "Container":
        """
        Registers a type by base type, to be instantiated with singleton lifetime.
        If a single type is given, the method `add_exact_singleton` is used.

        :param base_type: registered type. If a concrete type is provided, it must
        inherit the base type.
        :param concrete_type: concrete class
        :return: the service collection itself
        """
        if concrete_type is None:
            return self._add_exact_singleton(base_type)

        return self.bind_types(base_type, concrete_type, ServiceLifeStyle.SINGLETON)

    def add_scoped(
        self, base_type: AnyType, concrete_type: Optional[AnyType] = None
    ) -> "Container":
        """
        Registers a type by base type, to be instantiated with scoped lifetime.
        If a single type is given, the method `add_exact_scoped` is used.

        :param base_type: registered type. If a concrete type is provided, it must
        inherit the base type.
        :param concrete_type: concrete class
        :return: the service collection itself
        """
        if concrete_type is None:
            return self._add_exact_scoped(base_type)

        return self.bind_types(base_type, concrete_type, ServiceLifeStyle.SCOPED)

    def add_transient(
        self, base_type: AnyType, concrete_type: Optional[AnyType] = None
    ) -> "Container":
        """
        Registers a type by base type, to be instantiated with transient lifetime.
        If a single type is given, the method `add_exact_transient` is used.

        :param base_type: registered type. If a concrete type is provided, it must
        inherit the base type.
        :param concrete_type: concrete class
        :return: the service collection itself
        """
        if concrete_type is None:
            return self._add_exact_transient(base_type)

        return self.bind_types(base_type, concrete_type, ServiceLifeStyle.TRANSIENT)

    def _add_exact_singleton(self, concrete_type: AnyType) -> "Container":
        """
        Registers an exact type, to be instantiated with singleton lifetime.

        :param concrete_type: concrete class
        :return: the service collection itself
        """
        if isabstract(concrete_type):
            raise AbstractNotSupported(concrete_type)
        self._bind(
            concrete_type,
            DynamicResolver(concrete_type, self, ServiceLifeStyle.SINGLETON),
        )
        return self

    def _add_exact_scoped(self, concrete_type: AnyType) -> "Container":
        """
        Registers an exact type, to be instantiated with scoped lifetime.

        :param concrete_type: concrete class
        :return: the service collection itself
        """
        if isabstract(concrete_type):
            raise AbstractNotSupported(concrete_type)
        self._bind(
            concrete_type, DynamicResolver(concrete_type, self, ServiceLifeStyle.SCOPED)
        )
        return self

    def _add_exact_transient(self, concrete_type: AnyType) -> "Container":
        """
        Registers an exact type, to be instantiated with transient lifetime.

        :param concrete_type: concrete class
        :return: the service collection itself
        """
        if isabstract(concrete_type):
            raise AbstractNotSupported(concrete_type)
        self._bind(
            concrete_type,
            DynamicResolver(concrete_type, self, ServiceLifeStyle.TRANSIENT),
        )
        return self

    def add_singleton_by_factory(
        self, factory: InternalProvider, return_type: Optional[AnyType] = None
    ) -> "Container":
        self.register_factory(factory, return_type, ServiceLifeStyle.SINGLETON)
        return self

    def add_transient_by_factory(
        self, factory: InternalProvider, return_type: Optional[AnyType] = None
    ) -> "Container":
        self.register_factory(factory, return_type, ServiceLifeStyle.TRANSIENT)
        return self

    def add_scoped_by_factory(
        self, factory: InternalProvider, return_type: Optional[AnyType] = None
    ) -> "Container":
        self.register_factory(factory, return_type, ServiceLifeStyle.SCOPED)
        return self

    @staticmethod
    def _check_factory(
        factory: InternalProvider, signature: Signature, handled_type: Optional[AnyType]
    ) -> InternalProviderFull:
        assert callable(factory), "The factory must be callable"

        params_len = len(signature.parameters)

        if params_len == 0:
            return FactoryWrapperNoArgs(factory)  # type: ignore

        if params_len == 1:
            return FactoryWrapperContextArg(factory)  # type: ignore

        if params_len == 2:
            return factory  # type: ignore

        raise InvalidFactory(handled_type)

    def register_factory(
        self,
        factory: InternalProvider,
        return_type: Optional[AnyType],
        life_style: ServiceLifeStyle,
    ) -> None:
        if not callable(factory):
            raise InvalidFactory(return_type)

        sign = Signature.from_callable(factory)
        if return_type is None:
            if sign.return_annotation is _empty:
                raise MissingTypeException()
            return_type = sign.return_annotation

            if isinstance(return_type, str):  # pragma: no cover
                # Python 3.10
                annotations = get_factory_annotations_or_throw(factory)
                return_type = annotations["return"]

        self._bind(
            return_type,  # type: ignore
            FactoryResolver(
                return_type,
                self._check_factory(factory, sign, return_type),
                life_style,
            ),
        )

    def build_provider(self) -> Services:
        """
        Builds and returns a service provider that can be used to activate and obtain
        services.

        The configuration of services is validated at this point, if any service cannot
        be instantiated due to missing dependencies, an exception is thrown inside this
        operation.

        :return: Service provider that can be used to activate and obtain services.
        """
        with ResolutionContext() as context:
            _map: Dict[Any, InternalProviderFull] = {}

            for _type, resolver in self._map.items():
                if isinstance(resolver, DynamicResolver):
                    context.dynamic_chain.clear()

                if _type in context.resolved:
                    # assert _type not in context.resolved, "_map keys must be unique"
                    # check if its in the map
                    if _type in _map:
                        # NB: do not call resolver if one was already prepared for the
                        # type
                        raise OverridingServiceException(_type, resolver)
                    else:
                        resolved = context.resolved[_type]
                else:
                    # add to context so that we don't repeat operations
                    resolved = resolver(context)
                    context.resolved[_type] = resolved

                _map[_type] = resolved

                type_name = class_name(_type)
                if "." not in type_name:
                    _map[type_name] = _map[_type]

            if not self.strict:
                assert self._aliases is not None
                assert self._exact_aliases is not None

                # include aliases in the map;
                for name, _types in self._aliases.items():
                    _type = next(iter(_types), None)
                    _map[name] = self._get_alias_target_type(name, _map, _type)

                for name, _type in self._exact_aliases.items():
                    _map[name] = self._get_alias_target_type(name, _map, _type)

        return Services(_map)

    @staticmethod
    def _get_alias_target_type(
        name: str, _map: Dict[Any, InternalProviderFull], _type: Optional[AnyType]
    ) -> InternalProviderFull:
        try:
            return _map[_type]
        except KeyError as exc:
            raise AliasConfigurationError(name, _type) from exc
