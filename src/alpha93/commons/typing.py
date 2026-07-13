class typed[T]:
    @staticmethod
    def getattr(self, name: str, default = ...) -> T:
        return getattr(self, name) if default is ... else getattr(self, name, default)
