class __TypedGetter:
    def __getitem__[T](self, item: type[T]) -> Typed[T]: ...

class Typed[T]:
    def getattr[U](self, obj, name: str, default: U = ...) -> T: ...

typed: __TypedGetter
