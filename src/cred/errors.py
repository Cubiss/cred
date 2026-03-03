class CredError(Exception):
    exit_code = 1

class NotFound(CredError):
    exit_code = 10

class Locked(CredError):
    exit_code = 11

class ProviderMissing(CredError):
    exit_code = 12

class ConfigError(CredError):
    exit_code = 13

class ReadOnly(CredError):
    exit_code = 14