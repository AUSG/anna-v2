# 이 클래스를 상속받아 싱글턴을 구현할 수 있다
# 하지만 완벽하게 동시성 문제를 해결하지는 않는 것으로 보임
class SingletonInstance:
    __instance = None

    @classmethod
    def __get_instance(cls):
        return cls.__instance

    @classmethod
    def instance(cls, *args, **kargs):
        cls.__instance = cls(*args, **kargs)
        cls.instance = cls.__get_instance
        return cls.__instance
