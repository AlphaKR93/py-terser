def not_none[T](value: T | None) -> T:
    if value is None:
        raise TypeError
    return value
