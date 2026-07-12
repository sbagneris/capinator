"""Resolver protocol + registry.

A *resolver* turns a parsed component list into a resolved parts list for one
``component_type``. This is the generalization seam: the web layer only ever talks to
the registry, so new component types (resistors, inductors, …) are added as new resolvers
without touching the app. The MVP ships one resolver — aluminum electrolytic capacitors —
which simply wraps the existing :class:`~capinator.digikey.DigiKeyV4` client.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Protocol, runtime_checkable

from capinator.bom import build_bom, parse_spec


@dataclass
class ResolveResult:
    """What a resolve produces: the CLI-format ``output`` text (ready for DigiKey's bulk
    order form), the per-row ``errors``, and the number of DigiKey queries it cost."""
    output: str
    digikey_calls: int = 0
    errors: List[str] = field(default_factory=list)


@runtime_checkable
class Resolver(Protocol):
    """Interface every component-type resolver implements."""

    component_type: str

    def new_client(self) -> Any:
        """Build the (long-lived, reusable) API client this resolver drives."""
        ...

    def parse(self, spec_text: str) -> List[Dict[str, str]]:
        """Parse pasted spec text into per-component dicts (stored as the JSON column)."""
        ...

    def resolve(self, components: List[Dict[str, Any]], api: Any) -> ResolveResult:
        """Resolve already-parsed components into a :class:`ResolveResult`."""
        ...


class AluminumElectrolyticResolver:
    """MVP resolver: aluminum electrolytic capacitors via the DigiKey v4 client."""

    component_type = "aluminum_electrolytic_capacitor"

    def new_client(self) -> Any:
        # Imported lazily so importing the registry never triggers OAuth/network.
        from capinator.digikey import DigiKeyV4

        return DigiKeyV4()

    def parse(self, spec_text: str) -> List[Dict[str, str]]:
        return parse_spec(spec_text)

    def resolve(self, components: List[Dict[str, Any]], api: Any) -> ResolveResult:
        before = getattr(api, "call_count", 0)
        result = build_bom(components, api)
        calls = getattr(api, "call_count", 0) - before
        return ResolveResult(
            output="\n".join(result.lines),
            digikey_calls=calls,
            errors=result.errors,
        )


# Registry keyed by component_type. Register new resolvers here.
REGISTRY: Dict[str, Resolver] = {
    r.component_type: r
    for r in (AluminumElectrolyticResolver(),)
}

DEFAULT_COMPONENT_TYPE = AluminumElectrolyticResolver.component_type


def get_resolver(component_type: str) -> Resolver:
    """Return the resolver for ``component_type`` or raise ``KeyError`` if unknown."""
    try:
        return REGISTRY[component_type]
    except KeyError:
        raise KeyError(f"No resolver registered for component_type={component_type!r}")
