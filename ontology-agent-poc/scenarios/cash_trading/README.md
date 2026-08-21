# Cash Trading constructed-synthetic scenario

This directory contains the independently buildable cash-trading demo case derived
from the Deloitte HK transcriptions and generated sample received on 2026-08-20.

The original files remain outside the scenario package in `HKEX DTT Input/` and are
never modified. `intake/source-manifest.json` freezes their exact identity.
`governance/assumption-register.json` records every correction, provisional business
definition, synthetic enrichment and internally derived control. The external
confirmation register maps each material uncertainty to the rule currently used by
the PoC, so communication can continue without blocking implementation.

No artifact in this scenario is an HKEX-approved ontology, metric definition,
production binding, entitlement policy or known-correct result.
