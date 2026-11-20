"""Failures the ingest reports with a specific exit code."""


class ContractError(Exception):
    """A rendered document breaks its contract, so nothing is uploaded."""


class UsageError(Exception):
    """The run was started with missing or ambiguous inputs. The CLI exits with code 2."""


class SyncError(Exception):
    """The corpus could not be brought to the wanted state. The CLI exits with code 1."""
