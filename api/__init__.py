try:
    from .DeviceConfigurator import DeviceConfigurator
except ImportError:
    DeviceConfigurator = None

from .DeviceManager import DeviceManager, PairingManager