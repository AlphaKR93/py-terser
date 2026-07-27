import argparse
import typing
from dataclasses import is_dataclass
from enum import EnumType
from types import UnionType
from typing import TYPE_CHECKING, Any, Annotated, get_args, get_origin, override

from alpha93.commons.pydantic import dataclasses
from pydantic import BaseModel

if TYPE_CHECKING:
    from pydantic.fields import FieldInfo

    type ArgParse = argparse._ActionsContainer


if TYPE_CHECKING:
    type MutuallyExclusive[T] = Annotated[T, ...]
else:
    class MutuallyExclusive:
        def __class_getitem__(cls, item: Any) -> Any:
            return Annotated[item, cls()]

        @override
        def __hash__(self) -> int:
            return hash(type(self))

UnionConstructor: Any = UnionType
LiteralGenericAlias = getattr(typing, "_LiteralGenericAlias")


def _parse_bool(value: str) -> bool:
    # `type=bool` is a classic argparse footgun: `bool("False")` is `True` (any
    # non-empty string is truthy), so `--flag False` would silently become `True`.
    if value.lower() in ("true", "1"):
        return True
    if value.lower() in ("false", "0"):
        return False

    raise argparse.ArgumentTypeError(f"invalid boolean value: {value!r}")


class _ModelArgumentBuilder:
    __LOCK = object()

    def __init__(self, lock: object, parser: argparse.ArgumentParser):
        if lock is not _ModelArgumentBuilder.__LOCK:
            raise RuntimeError("Lock object does not match")

        self.parser = parser

    @staticmethod
    def from_model(parser: argparse.ArgumentParser, model: type[BaseModel]):
        _ModelArgumentBuilder(_ModelArgumentBuilder.__LOCK, parser).__iter_fields(parser, model)

    def __iter_fields(self, args: ArgParse, model: type[BaseModel]):
        if is_dataclass(model):
            model = dataclasses.to_model(model) # type: ignore[invalid-type]

        model_fields: dict[str, FieldInfo] = model.model_fields
        for field, field_info in model_fields.items():
            annotation: type[BaseModel] = field_info.annotation # type: ignore[invalid-type]
            if MutuallyExclusive in field_info.metadata:
                if BaseModel not in annotation.mro() and not is_dataclass(annotation):
                    raise ValueError

                group = self.parser.add_mutually_exclusive_group(required=field_info.is_required())
                self.__iter_fields(group, annotation)   # type: ignore[invalid-type]
                continue

            types: list[Any] = [annotation]
            if isinstance(annotation, UnionType):
                types = list(get_args(annotation))

            models = set(filter(lambda x: isinstance(x, type(BaseModel)) or is_dataclass(x), types))
            if not len(models):
                self.__add_arg(args, field, field_info, annotation) # type: ignore[invalid-type]
                continue

            group = self.parser.add_argument_group(
                title=field,
                description=field_info.description,
                argument_default=field_info.default,
            )

            if len(type_params := set(types) - models):
                annotation = UnionConstructor[tuple(type_params)]
                self.__add_arg(group, field, field_info, annotation) # type: ignore[invalid-type]

            for type_param in models:
                self.__iter_fields(group, type_param)       # type: ignore[invalid-type]

    def __add_arg(self, parser: ArgParse, field: str, field_info: FieldInfo, model: type):
        if isinstance(model, type(BaseModel)) or is_dataclass(model):
            self.__iter_fields(parser, model)   # type: ignore[invalid-type]
            return

        choices = None
        if model is bool:
            choices = [True, False]
        elif isinstance(model, LiteralGenericAlias):
            choices = get_args(model)
            # `model` itself (the `Literal[...]` alias) isn't callable as a `type=`
            # converter - convert to whatever type the literal's own values are instead.
            model = type(choices[0])
        elif isinstance(model, EnumType):
            choices = list(model.__members__)
            if not len(choices):
                choices = None

        if isinstance(model, UnionType):
            # Resolve `X | None` (e.g. `tuple[int, ...] | None`) to `X` before checking
            # if it's a collection type below - `get_origin` on the union itself never
            # matches `list`/`set`/`tuple`, so this has to happen first.
            non_none = [t for t in get_args(model) if t is not type(None)]
            model = non_none[0] if len(non_none) == 1 else None

        action, nargs = "store", None
        if get_origin(model) in (list, set, frozenset, tuple):
            # 'extend' (not 'append') so repeated uses of the flag accumulate into a
            # flat list matching the field's collection type, instead of a list of lists.
            action, nargs = "extend", '+'
            # argparse's `type=` converts each individual token, so it needs the
            # collection's element type (e.g. `str`), not the collection type itself
            # (calling `set[str]("foo")` would build a set of its characters).
            elem_types = get_args(model)
            model = elem_types[0] if elem_types else str

        default = [] if action == "extend" else field_info.get_default(call_default_factory=True)
        parser.add_argument(
            "--" + field.replace('_', '-'),
            action=action,
            nargs=nargs,
            default=default,
            type=_parse_bool if model is bool else model, # type: ignore[invalid-type]
            choices=choices,
            required=field_info.is_required(),
            help=field_info.description,
            dest=field,
            deprecated=field_info.deprecated,
        )

arguments_from_model = _ModelArgumentBuilder.from_model
