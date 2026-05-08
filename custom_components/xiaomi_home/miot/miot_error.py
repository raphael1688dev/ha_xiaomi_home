# -*- coding: utf-8 -*-
"""
MIoT error code and exception.
"""
from enum import Enum
from typing import Any


class MIoTErrorCode(Enum):
    """MIoT error code."""
    # Base error code
    CODE_UNKNOWN = -10000
    CODE_UNAVAILABLE = -10001
    CODE_INVALID_PARAMS = -10002
    CODE_RESOURCE_ERROR = -10003
    CODE_INTERNAL_ERROR = -10004
    CODE_UNAUTHORIZED_ACCESS = -10005
    CODE_TIMEOUT = -10006
    # OAuth error code
    CODE_OAUTH_UNAUTHORIZED = -10020
    # Http error code
    CODE_HTTP_INVALID_ACCESS_TOKEN = -10030
    # MIoT mips error code
    CODE_MIPS_INVALID_RESULT = -10040
    # MIoT cert error code
    CODE_CERT_INVALID_CERT = -10050
    # MIoT spec error code, -10060
    # MIoT storage error code, -10070
    # MIoT ev error code, -10080
    # Mips service error code, -10090
    # Config flow error code, -10100
    CODE_CONFIG_INVALID_INPUT = -10100
    CODE_CONFIG_INVALID_STATE = -10101
    # Options flow error code , -10110
    # MIoT lan error code, -10120
    CODE_LAN_UNAVAILABLE = -10120


class MIoTError(Exception):
    """MIoT error."""
    code: MIoTErrorCode
    message: Any

    def __init__(
        self,  message: Any, code: MIoTErrorCode = MIoTErrorCode.CODE_UNKNOWN
    ) -> None:
        self.message = message
        self.code = code
        super().__init__(self.message)

    def to_str(self) -> str:
        return f'{{"code":{self.code.value},"message":"{self.message}"}}'

    def to_dict(self) -> dict:
        return {"code": self.code.value, "message": self.message}


class MIoTOauthError(MIoTError):
    ...


class MIoTHttpError(MIoTError):
    ...


class MIoTMipsError(MIoTError):
    ...


class MIoTDeviceError(MIoTError):
    ...


class MIoTSpecError(MIoTError):
    ...


class MIoTStorageError(MIoTError):
    ...


class MIoTCertError(MIoTError):
    ...


class MIoTClientError(MIoTError):
    ...


class MIoTEvError(MIoTError):
    ...


class MipsServiceError(MIoTError):
    ...


class MIoTConfigError(MIoTError):
    ...


class MIoTOptionsError(MIoTError):
    ...


class MIoTLanError(MIoTError):
    ...
