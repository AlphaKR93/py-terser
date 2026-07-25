if __debug__:
    def unreachable(): raise SystemError("Reached to unreachable code")
else:
    def unreachable(): pass
