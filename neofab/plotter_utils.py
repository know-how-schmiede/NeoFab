POSTER_SIZE_DEFS = {
    "A3": {"label": "A3", "width_cm": 29.7, "height_cm": 42.0},
    "A2": {"label": "A2", "width_cm": 42.0, "height_cm": 59.4},
    "A1": {"label": "A1", "width_cm": 59.4, "height_cm": 84.1},
    "A0": {"label": "A0", "width_cm": 84.1, "height_cm": 118.9},
}

POSTER_SIZE_OPTIONS = [
    (key, f"{value['label']} ({value['width_cm'] / 100:.3f} x {value['height_cm'] / 100:.3f} m)")
    for key, value in POSTER_SIZE_DEFS.items()
]

DEFAULT_POSTER_SIZE = "A1"


def normalize_poster_size(raw_value: str | None) -> str:
    value = (raw_value or "").strip().upper()
    return value if value in POSTER_SIZE_DEFS else DEFAULT_POSTER_SIZE


def poster_size_area_cm2(raw_value: str | None) -> float:
    size = POSTER_SIZE_DEFS[normalize_poster_size(raw_value)]
    return float(size["width_cm"]) * float(size["height_cm"])


def poster_size_area_m2(raw_value: str | None) -> float:
    return poster_size_area_cm2(raw_value) / 10000.0


def plotter_poster_costs(poster) -> dict[str, float | str]:
    plotter_type = getattr(poster, "plotter_type", None)
    plotter_paper = getattr(poster, "plotter_paper", None)
    quantity = max(1, int(getattr(poster, "quantity", None) or 1))
    size_key = normalize_poster_size(getattr(poster, "poster_size", None))
    area_m2 = poster_size_area_m2(size_key)

    machine_cost = (getattr(plotter_type, "machine_cost_per_poster", 0.0) if plotter_type else 0.0) or 0.0
    maintenance_cost = (getattr(plotter_type, "maintenance_cost_per_poster", 0.0) if plotter_type else 0.0) or 0.0
    ink_price_per_m2 = (getattr(plotter_type, "ink_cost_per_m2", 0.0) if plotter_type else 0.0) or 0.0
    setup_fee = (getattr(plotter_type, "setup_fee", 0.0) if plotter_type else 0.0) or 0.0
    paper_price_per_m2 = (getattr(plotter_paper, "price_per_m2", 0.0) if plotter_paper else 0.0) or 0.0
    coverage_percent = getattr(poster, "coverage_percent", None)
    try:
        coverage_percent = float(coverage_percent)
    except (TypeError, ValueError):
        coverage_percent = 100.0
    coverage_percent = min(100.0, max(0.0, coverage_percent))
    coverage_factor = coverage_percent / 100.0
    paper_cost = area_m2 * paper_price_per_m2
    ink_cost = area_m2 * ink_price_per_m2 * coverage_factor
    cost_per_poster = machine_cost + maintenance_cost + paper_cost + ink_cost

    return {
        "size": size_key,
        "area_m2": area_m2,
        "coverage_percent": coverage_percent,
        "paper_cost": paper_cost,
        "ink_cost": ink_cost,
        "cost_per_poster": cost_per_poster,
        "setup_fee": setup_fee,
        "total_cost": (cost_per_poster * quantity) + setup_fee,
    }
