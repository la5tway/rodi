from typing import TYPE_CHECKING, Any, Callable, Dict, Protocol, Type, TypeVar, Union

if TYPE_CHECKING:
    from rodi.context import ActivationScope

T = TypeVar("T")
AnyCallable = Callable[..., Any]
AnyType = Type[Any]
AnyTypeDict = Dict[str, AnyType]
Key = Union[AnyType, str]
KeyT = Union[Type[T], str]


class ContainerProtocol(Protocol):
    """
    Generic interface of DI Container that can register and resolve services,
    and tell if a type is configured.
    """

    def register(self, obj_type: Union[Type[Any], str], *args: Any, **kwargs: Any):
        """Registers a type in the container, with optional arguments."""

    def resolve(self, obj_type: Union[Type[T], str], *args: Any, **kwargs: Any) -> T:
        """Activates an instance of the given type, with optional arguments."""

    def __contains__(self, item: Any) -> bool:
        """
        Returns a value indicating whether a given type is configured in this container.
        """


class InternalProviderFull(Protocol):
    def __call__(self, context: "ActivationScope", parent_type: Key) -> Any:
        ...


class AsyncInternalProviderFull(Protocol):
    async def __call__(self, context: "ActivationScope", parent_type: Key) -> Any:
        ...


class InternalProviderNoArguments(Protocol):
    def __call__(self) -> Any:
        ...


class InternalProviderOneArgument(Protocol):
    def __call__(self, context: "ActivationScope") -> Any:
        ...


InternalProvider = Union[
    InternalProviderFull,
    InternalProviderNoArguments,
    InternalProviderOneArgument,
    AsyncInternalProviderFull,
]
