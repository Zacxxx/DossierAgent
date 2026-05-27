# `core`

Tiny composition package for DossierAgent.

## Purpose

`core` lets developers stitch independently maintained packages together without turning a feature package into a dependency hub.

## Owns

- package manifests
- capability registry
- runtime orchestration
- lifecycle wiring

## Does Not Own

- domain algorithms
- database queries
- Elastic mappings
- browser extraction
- UI state
- prompt text

## Public Surface

- `PackageManifest`
- `Capability`
- `PackageRegistry`
- `DossierAgentCore`

