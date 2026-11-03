from contextvars import ContextVar

_current_tenant = ContextVar('current_tenant', default=None)

def get_current_tenant():
    return _current_tenant.get()

def set_current_tenant(tenant):
    return _current_tenant.set(tenant)

def clear_current_tenant(token=None):
    if token is not None:
        _current_tenant.reset(token)
    else:
        _current_tenant.set(None)
