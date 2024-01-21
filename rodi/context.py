from contextlib import AsyncExitStack, ExitStack
from types import TracebackType
from typing import TYPE_CHECKING, Any, Dict, Optional, Type, TypeVar, Union

from rodi.typings import AnyType, InternalProviderFull, Key

if TYPE_CHECKING:
    from .services import Services

T = TypeVar("T")


class ActivationScope:
    __slots__ = ("scoped_services", "provider", "stack", "astack")

    def __init__(
        self,
        provider: Optional["Services"] = None,
        scoped_services: Optional[Dict[Union[AnyType, str], Any]] = None,
    ) -> None:
        self.provider = provider
        self.scoped_services = scoped_services or {}
        self.stack = ExitStack()
        self.astack = AsyncExitStack()

    def __enter__(self) -> "ActivationScope":
        self.stack.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.stack.__exit__(exc_type, exc_val, exc_tb)
        self.dispose()

    async def __aenter__(self) -> "ActivationScope":
        self.stack.__enter__()
        await self.astack.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.stack.__exit__(exc_type, exc_val, exc_tb)
        await self.astack.__aexit__(exc_type, exc_val, exc_tb)
        self.dispose()

    def get(
        self,
        desired_type: Union[Type[T], str],
        scope: Optional["ActivationScope"] = None,
        *,
        default: Optional[T] = ...,
    ) -> T:
        return self.provider.get(desired_type, scope or self, default=default)

    async def aget(
        self,
        desired_type: Union[Type[T], str],
        scope: Optional["ActivationScope"] = None,
        *,
        default: Optional[Any] = ...,
    ) -> T:
        return await self.provider.aget(desired_type, scope or self, default=default)

    def dispose(self) -> None:
        self.provider = None  # type: Services # type: ignore

        if self.scoped_services:
            self.scoped_services.clear()


class ResolutionContext:
    __slots__ = ("resolved", "dynamic_chain")
    __deletable__ = ("resolved",)

    def __init__(self):
        self.resolved: dict[Key, InternalProviderFull] = {}
        self.dynamic_chain: list[AnyType] = []

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ):
        self.dispose()

    def dispose(self):
        del self.resolved
        self.dynamic_chain.clear()
