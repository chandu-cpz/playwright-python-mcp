from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from inspect import Parameter, Signature
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .context import Context
    from .response import Response


ToolHandler = Callable[["Context", dict[str, Any], "Response"], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ToolParameter:
    name: str
    annotation: object
    default: object = Parameter.empty


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    capability: str
    handler: ToolHandler
    parameters: tuple[ToolParameter, ...] = ()
    skill_only: bool = False
    clears_modal_state: str | None = None

    def signature(self) -> Signature:
        return Signature(
            parameters=[
                Parameter(
                    parameter.name,
                    Parameter.KEYWORD_ONLY,
                    default=parameter.default,
                    annotation=parameter.annotation,
                )
                for parameter in self.parameters
            ]
        )


def param(name: str, annotation: object, default: object = Parameter.empty) -> ToolParameter:
    return ToolParameter(name=name, annotation=annotation, default=default)
