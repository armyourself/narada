"""Outer gateway package marker.

The actual implementation lives in ``gateway.gateway`` (nested).
This marker lets Python resolve ``gateway.gateway`` as a submodule
when the repo root or the gateway directory itself is on
``sys.path`` (e.g. when running tests in place without installing).
"""
