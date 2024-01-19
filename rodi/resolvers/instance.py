from typing import Any

from rodi.common import class_name
from rodi.context import ResolutionContext
from rodi.providers.singleton import InstanceProvider


class InstanceResolver:
    __slots__ = ("instance",)

    def __init__(self, instance: Any):
        self.instance = instance

    def __repr__(self):
        return f"<Singleton {class_name(self.instance.__class__)}>"

    def __call__(self, context: ResolutionContext):
        return InstanceProvider(self.instance)
