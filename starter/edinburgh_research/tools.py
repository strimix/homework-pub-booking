"""Ex5 tools. Four tools the agent uses to research an Edinburgh booking."""

from __future__ import annotations

import json
from pathlib import Path

from sovereign_agent.errors import ToolError
from sovereign_agent.session.directory import Session
from sovereign_agent.tools.registry import ToolRegistry, ToolResult, _RegisteredTool

from starter.edinburgh_research.integrity import _TOOL_CALL_LOG, record_tool_call

_SAMPLE_DATA = Path(__file__).parent / "sample_data"


def _load_json(name: str) -> list | dict:
    path = _SAMPLE_DATA / name
    if not path.is_file():
        raise ToolError(
            code="SA_TOOL_DEPENDENCY_MISSING",
            message=f"fixture missing: {path}",
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ToolError(
            code="SA_TOOL_DEPENDENCY_MISSING",
            message=f"invalid JSON in {path}: {exc}",
        ) from exc


def venue_search(near: str, party_size: int, budget_max_gbp: int = 1000) -> ToolResult:
    arguments = {"near": near, "party_size": party_size, "budget_max_gbp": budget_max_gbp}

    if not isinstance(near, str) or not near.strip():
        result = ToolResult(
            success=False,
            output={"error": "near must be a non-empty string"},
            summary="venue_search: invalid near",
            error=ToolError(code="SA_TOOL_INVALID_INPUT", message="near must be non-empty"),
        )
        record_tool_call("venue_search", arguments, result.output)
        return result

    if not isinstance(party_size, int) or party_size < 1:
        result = ToolResult(
            success=False,
            output={"error": "party_size must be a positive integer"},
            summary="venue_search: invalid party_size",
            error=ToolError(code="SA_TOOL_INVALID_INPUT", message="party_size must be >= 1"),
        )
        record_tool_call("venue_search", arguments, result.output)
        return result

    search_count = sum(1 for r in _TOOL_CALL_LOG if r.tool_name == "venue_search")
    if search_count >= 3:
        result = ToolResult(
            success=False,
            output={"error": "too_many_searches", "count": search_count},
            summary="STOP calling venue_search; use the results you already have.",
        )
        record_tool_call("venue_search", arguments, result.output)
        return result

    venues = _load_json("venues.json")
    near_lower = near.lower().strip()
    results = []
    for venue in venues:
        if not venue.get("open_now"):
            continue
        if near_lower and near_lower not in venue.get("area", "").lower():
            continue
        if venue.get("seats_available_evening", 0) < party_size:
            continue
        venue_cost = venue.get("hire_fee_gbp", 0) + venue.get("min_spend_gbp", 0)
        if venue_cost > budget_max_gbp:
            continue
        results.append(venue)

    output = {
        "near": near,
        "party_size": party_size,
        "results": results,
        "count": len(results),
    }
    summary = f"venue_search({near}, party={party_size}): {len(results)} result(s)"
    record_tool_call("venue_search", arguments, output)
    return ToolResult(success=True, output=output, summary=summary)


def get_weather(city: str, date: str) -> ToolResult:
    arguments = {"city": city, "date": date}
    weather_data = _load_json("weather.json")
    city_key = city.lower().strip()

    if city_key not in weather_data:
        output = {"city": city, "date": date, "error": f"city {city!r} not in fixture"}
        result = ToolResult(
            success=False,
            output=output,
            summary=f"get_weather({city}, {date}): city not found",
            error=ToolError(code="SA_TOOL_INVALID_INPUT", message=output["error"]),
        )
        record_tool_call("get_weather", arguments, result.output)
        return result

    city_forecasts = weather_data[city_key]
    if date not in city_forecasts:
        output = {"city": city, "date": date, "error": f"date {date!r} not in fixture"}
        result = ToolResult(
            success=False,
            output=output,
            summary=f"get_weather({city}, {date}): date not found",
            error=ToolError(code="SA_TOOL_INVALID_INPUT", message=output["error"]),
        )
        record_tool_call("get_weather", arguments, result.output)
        return result

    forecast = city_forecasts[date]
    output = {
        "city": city,
        "date": date,
        "condition": forecast["condition"],
        "temperature_c": forecast["temperature_c"],
        "precip_mm": forecast["precip_mm"],
        "wind_kph": forecast["wind_kph"],
    }
    summary = f"get_weather({city}, {date}): {forecast['condition']}, {forecast['temperature_c']}C"
    record_tool_call("get_weather", arguments, output)
    return ToolResult(success=True, output=output, summary=summary)


def calculate_cost(
    venue_id: str,
    party_size: int,
    duration_hours: int,
    catering_tier: str = "bar_snacks",
) -> ToolResult:
    arguments = {
        "venue_id": venue_id,
        "party_size": party_size,
        "duration_hours": duration_hours,
        "catering_tier": catering_tier,
    }

    catering = _load_json("catering.json")
    venues = {v["id"]: v for v in _load_json("venues.json")}

    if venue_id not in venues:
        output = {"error": f"unknown venue_id {venue_id!r}"}
        result = ToolResult(
            success=False,
            output=output,
            summary=f"calculate_cost: unknown venue {venue_id}",
            error=ToolError(code="SA_TOOL_INVALID_INPUT", message=output["error"]),
        )
        record_tool_call("calculate_cost", arguments, result.output)
        return result

    rates = catering["base_rates_gbp_per_head"]
    if catering_tier not in rates:
        output = {"error": f"unknown catering_tier {catering_tier!r}"}
        result = ToolResult(
            success=False,
            output=output,
            summary="calculate_cost: invalid catering tier",
            error=ToolError(code="SA_TOOL_INVALID_INPUT", message=output["error"]),
        )
        record_tool_call("calculate_cost", arguments, result.output)
        return result

    venue = venues[venue_id]
    base = rates[catering_tier]
    mult = catering["venue_modifiers"].get(venue_id, 1.0)
    hours = max(1, int(duration_hours))
    subtotal_gbp = int(base * mult * party_size * hours)
    service_gbp = int(subtotal_gbp * catering["service_charge_percent"] / 100)
    venue_fees = int(venue.get("hire_fee_gbp", 0) + venue.get("min_spend_gbp", 0))
    total_gbp = subtotal_gbp + service_gbp + venue_fees

    # Deposit applies to catering subtotal + service (food/drink), not venue hire/minimum.
    deposit_base = subtotal_gbp + service_gbp
    if deposit_base < 300:
        deposit_required_gbp = 0
    elif deposit_base <= 1000:
        deposit_required_gbp = int(deposit_base * 0.2)
    else:
        deposit_required_gbp = int(deposit_base * 0.3)

    output = {
        "venue_id": venue_id,
        "party_size": party_size,
        "duration_hours": hours,
        "catering_tier": catering_tier,
        "subtotal_gbp": subtotal_gbp,
        "service_gbp": service_gbp,
        "total_gbp": total_gbp,
        "deposit_required_gbp": deposit_required_gbp,
    }
    summary = (
        f"calculate_cost({venue_id}, {party_size}): "
        f"total £{total_gbp}, deposit £{deposit_required_gbp}"
    )
    record_tool_call("calculate_cost", arguments, output)
    return ToolResult(success=True, output=output, summary=summary)


def generate_flyer(session: Session, event_details: dict) -> ToolResult:
    arguments = {"event_details": event_details}
    required = (
        "venue_name",
        "venue_address",
        "date",
        "time",
        "party_size",
        "condition",
        "temperature_c",
        "total_gbp",
        "deposit_required_gbp",
    )
    missing = [k for k in required if k not in event_details]
    if missing:
        output = {"error": f"missing keys: {missing}"}
        result = ToolResult(
            success=False,
            output=output,
            summary=f"generate_flyer: missing {missing}",
            error=ToolError(code="SA_TOOL_INVALID_INPUT", message=output["error"]),
        )
        record_tool_call("generate_flyer", arguments, result.output)
        return result

    venue_name = event_details["venue_name"]
    venue_address = event_details["venue_address"]
    date = event_details["date"]
    time = event_details["time"]
    party_size = event_details["party_size"]
    condition = str(event_details["condition"]).replace("_", " ")
    temperature_c = event_details["temperature_c"]
    total_gbp = event_details["total_gbp"]
    deposit_required_gbp = event_details["deposit_required_gbp"]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{venue_name} — Event Flyer</title>
  <style>
    body {{ font-family: Georgia, serif; margin: 2rem; background: #f4f0e8; color: #222; }}
    h1 {{ color: #4a2c2a; }}
    .fact {{ margin: 0.4rem 0; }}
    .cost {{ font-size: 1.1rem; font-weight: bold; }}
  </style>
</head>
<body>
  <h1 data-testid="title">{venue_name}</h1>
  <p class="fact" data-testid="address">{venue_address}</p>
  <p class="fact" data-testid="date">{date}</p>
  <p class="fact" data-testid="time">{time}</p>
  <p class="fact" data-testid="party_size">{party_size}</p>
  <p class="fact" data-testid="condition">{condition}</p>
  <p class="fact" data-testid="temperature">{temperature_c}°C</p>
  <p class="cost" data-testid="total">£{total_gbp}</p>
  <p class="cost" data-testid="deposit">£{deposit_required_gbp}</p>
</body>
</html>
"""

    path = session.workspace_dir / "flyer.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    output = {"path": "workspace/flyer.html", "bytes_written": len(html.encode("utf-8"))}
    summary = f"generate_flyer: wrote {path} ({output['bytes_written']} chars)"
    record_tool_call("generate_flyer", arguments, event_details)
    return ToolResult(success=True, output=output, summary=summary)


def build_tool_registry(session: Session) -> ToolRegistry:
    from sovereign_agent.tools.builtin import make_builtin_registry

    reg = make_builtin_registry(session)

    reg.register(
        _RegisteredTool(
            name="venue_search",
            description="Search Edinburgh venues by area, party size, and max budget.",
            fn=venue_search,
            parameters_schema={
                "type": "object",
                "properties": {
                    "near": {"type": "string"},
                    "party_size": {"type": "integer"},
                    "budget_max_gbp": {"type": "integer", "default": 1000},
                },
                "required": ["near", "party_size"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,
            examples=[
                {
                    "input": {"near": "Haymarket", "party_size": 6, "budget_max_gbp": 800},
                    "output": {"count": 1, "results": [{"id": "haymarket_tap"}]},
                }
            ],
        )
    )

    reg.register(
        _RegisteredTool(
            name="get_weather",
            description="Get scripted weather for a city on a YYYY-MM-DD date.",
            fn=get_weather,
            parameters_schema={
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "date": {"type": "string"},
                },
                "required": ["city", "date"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,
            examples=[
                {
                    "input": {"city": "Edinburgh", "date": "2026-04-25"},
                    "output": {"condition": "cloudy", "temperature_c": 12},
                }
            ],
        )
    )

    reg.register(
        _RegisteredTool(
            name="calculate_cost",
            description="Compute total cost and deposit for a booking.",
            fn=calculate_cost,
            parameters_schema={
                "type": "object",
                "properties": {
                    "venue_id": {"type": "string"},
                    "party_size": {"type": "integer"},
                    "duration_hours": {"type": "integer"},
                    "catering_tier": {
                        "type": "string",
                        "enum": [
                            "drinks_only",
                            "bar_snacks",
                            "sit_down_meal",
                            "three_course_meal",
                        ],
                        "default": "bar_snacks",
                    },
                },
                "required": ["venue_id", "party_size", "duration_hours"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,
            examples=[
                {
                    "input": {
                        "venue_id": "haymarket_tap",
                        "party_size": 6,
                        "duration_hours": 3,
                    },
                    "output": {"total_gbp": 540, "deposit_required_gbp": 0},
                }
            ],
        )
    )

    def _flyer_adapter(event_details: dict) -> ToolResult:
        return generate_flyer(session, event_details)

    reg.register(
        _RegisteredTool(
            name="generate_flyer",
            description="Write an HTML flyer for the event to workspace/flyer.html.",
            fn=_flyer_adapter,
            parameters_schema={
                "type": "object",
                "properties": {"event_details": {"type": "object"}},
                "required": ["event_details"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=False,
            examples=[
                {
                    "input": {
                        "event_details": {
                            "venue_name": "Haymarket Tap",
                            "date": "2026-04-25",
                            "party_size": 6,
                        }
                    },
                    "output": {"path": "workspace/flyer.html"},
                }
            ],
        )
    )

    return reg


__all__ = [
    "build_tool_registry",
    "venue_search",
    "get_weather",
    "calculate_cost",
    "generate_flyer",
]
