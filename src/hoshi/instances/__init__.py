"""实例子包。"""

from .detect import Detection, detect
from .java import JavaInfo, probe, scan
from .model import Instance, InstanceError
from .registry import InstanceNotFound, InstanceRegistry
from .settings import PER_INSTANCE_KEYS, effective, is_per_instance, resolve
from .supervisor import InstanceProcess

__all__ = [
    "Detection",
    "Instance",
    "InstanceError",
    "InstanceNotFound",
    "InstanceProcess",
    "InstanceRegistry",
    "PER_INSTANCE_KEYS",
    "effective",
    "is_per_instance",
    "resolve",
    "JavaInfo",
    "detect",
    "probe",
    "scan",
]
