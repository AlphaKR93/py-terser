class __TypedGetter:
    class Typed[T]:
        def getattr[U](self, obj, name: str, default: U = ...) -> T: ...

    def __getitem__[T](self, item: type[T]) -> Typed[T]: ...

typed: __TypedGetter

__all__ = ("typed",)
