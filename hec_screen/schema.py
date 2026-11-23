"""HEC-DB fields and explicit unit conversions for scalar properties."""

COLUMNS = (
    "material_id", "composition", "family", "material_class", "crystal_structure",
    "constituents", "synthesis_method", "processing_conditions", "specimen_form",
    "applications", "property", "value", "unit", "uncertainty", "uncertainty_type",
    "temperature_c", "temperature_start_c", "frequency_hz", "pressure_kpa",
    "method", "basis", "measurement_conditions", "cohort", "replicate_id",
    "data_type", "publication_title", "doi", "source_url", "source_locator",
)

REQUIRED = {
    "material_id", "composition", "family", "material_class", "applications",
    "property", "value", "unit", "data_type", "publication_title", "source_locator",
}

CONDITION_FIELDS = (
    "specimen_form", "method", "basis", "temperature_c", "temperature_start_c",
    "frequency_hz", "pressure_kpa", "measurement_conditions",
)

NUMERIC = (
    "value", "uncertainty", "temperature_c", "temperature_start_c", "frequency_hz", "pressure_kpa",
)

# Each entry contains the canonical unit and accepted input units as (factor, offset).
UNITS = {
    "thermal_conductivity": ("W/(m*K)", {"mW/(m*K)": (0.001, 0), "W/(cm*K)": (100, 0)}),
    "thermal_expansion": ("1e-6/K", {"1/K": (1e6, 0), "ppm/K": (1, 0), "1e-6/degC": (1, 0)}),
    "melting_temperature": ("degC", {"K": (1, -273.15), "°C": (1, 0)}),
    "glass_transition_temperature": ("degC", {"K": (1, -273.15), "°C": (1, 0)}),
    "crystallization_temperature": ("degC", {"K": (1, -273.15), "°C": (1, 0)}),
    "density": ("g/cm3", {"kg/m3": (0.001, 0), "g/cm^3": (1, 0)}),
    "relative_density": ("%", {"1": (100, 0)}),
    "hardness": ("GPa", {"MPa": (0.001, 0)}),
    "youngs_modulus": ("GPa", {"MPa": (0.001, 0)}),
    "fracture_toughness": ("MPa*m^0.5", {}),
    "dielectric_constant": ("1", {"dimensionless": (1, 0)}),
    "dielectric_loss": ("1", {"%": (0.01, 0), "dimensionless": (1, 0)}),
    "breakdown_strength": ("kV/mm", {"kV/cm": (0.1, 0), "MV/m": (1, 0)}),
    "energy_storage_density": ("J/cm3", {"MJ/m3": (1, 0), "J/cm^3": (1, 0)}),
    "efficiency": ("%", {"1": (100, 0)}),
    "electrical_conductivity": ("S/m", {"S/cm": (100, 0)}),
    "refractive_index": ("1", {"dimensionless": (1, 0)}),
}

ORIGINS = {"experimental", "computational", "synthetic"}

POSITIVE_PROPERTIES = {
    "thermal_conductivity", "density", "relative_density", "hardness", "youngs_modulus",
    "fracture_toughness", "dielectric_constant", "breakdown_strength", "refractive_index",
}


def unit_conversion(property_name, unit):
    """Return canonical unit, multiplicative factor and additive offset."""
    if property_name not in UNITS:
        raise ValueError(f"Unknown property {property_name!r}")
    canonical, aliases = UNITS[property_name]
    if unit == canonical:
        return canonical, 1.0, 0.0
    if unit not in aliases:
        raise ValueError(f"Unsupported unit {unit!r} for {property_name} (use {canonical})")
    factor, offset = aliases[unit]
    return canonical, factor, offset
