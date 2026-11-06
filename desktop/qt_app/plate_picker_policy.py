"""Presentation-only source preference for installed 3D printer build plates.

No source catalog data is deleted: conversion, defaults and OPC tests continue
using the original full catalog. The picker shows just one plate per printer.
"""
from __future__ import annotations


def _identity(asset):
    # Vendor IDs are often short codes (e.g. BBL); keep them to avoid merging
    # genuinely different manufacturers with identically named printers.
    return (str(asset.vendor).strip().casefold(),
            ' '.join(str(asset.printer).split()).casefold())


def _rank(asset):
    vendor = str(asset.vendor).casefold().strip()
    printer = str(asset.printer).casefold().strip()
    is_bambu = vendor in {'bbl', 'bambulab', 'bambu lab'} or printer.startswith('bambu lab ')
    source = str(asset.source).casefold().strip()
    if is_bambu:
        preferred = {'bambu studio': 0, 'orcaslicer': 1}
    else:
        preferred = {'orcaslicer': 0, 'bambu studio': 1}
    # Favor an actual original texture when otherwise tied. This does not
    # change eligibility: STL existence has already been validated upstream.
    return (preferred.get(source, 2), 0 if asset.texture else 1,
            str(getattr(asset, 'profile', '')).casefold())


def preferred_plate_assets(plates):
    """Return stable, duplicate-free picker entries; keep unique vendor plates.

    When only one slicer is present its entire list is retained (except exact
    intra-slicer duplicate identities). When both are present, keep one for a
    shared vendor+printer model, preferring Orca for non-Bambu and Bambu for
    Bambu-branded models, while preserving models unique to either source.
    """
    chosen = {}
    for asset in plates:
        key = _identity(asset)
        if key not in chosen or _rank(asset) < _rank(chosen[key]):
            chosen[key] = asset
    return tuple(sorted(chosen.values(), key=lambda a:
        (str(a.printer).casefold(), str(a.vendor).casefold(), str(a.source).casefold())))
