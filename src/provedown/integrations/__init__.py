"""Optional verifier integrations live here.

The core package deliberately avoids hard dependencies on external validation
systems. Integrations should implement the standard ``Verifier`` protocol and
register with ``VerifierRegistry`` when the relevant dependency is installed.
"""
