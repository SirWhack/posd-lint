from service import BigServiceProtocol


def use(svc: BigServiceProtocol) -> int:
    return svc.do_thing()
