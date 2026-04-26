from __future__ import annotations

import os

from dotenv import load_dotenv
from uagents import Agent, Context, Model

load_dotenv()


class SustainabilityRequest(Model):
    action: str
    disease_urgency: str


class SustainabilityResponse(Model):
    water_saved_ml: int
    risk_level: str
    fertilizer_avoided: bool


agent = Agent(
    name="agrimind-sustainability-agent",
    seed=os.getenv("SUSTAINABILITY_SEED_PHRASE", "replace_with_unique_random_string"),
    port=int(os.getenv("SUSTAINABILITY_AGENT_PORT", "8013")),
    mailbox=os.getenv("ENABLE_MAILBOX", "true").lower() == "true",
    publish_agent_details=os.getenv("PUBLISH_AGENT_DETAILS", "true").lower() == "true",
)


@agent.on_message(model=SustainabilityRequest)
async def handle_sustainability(ctx: Context, sender: str, msg: SustainabilityRequest) -> None:
    baseline = 500
    multiplier = {
        "no_watering": 1.0,
        "light_watering": 0.5,
        "water_now": 0.0,
    }.get(msg.action, 0.4)

    response = SustainabilityResponse(
        water_saved_ml=int(baseline * multiplier),
        risk_level="high" if msg.disease_urgency == "high" else "low",
        fertilizer_avoided=msg.disease_urgency in {"low", "medium"},
    )
    await ctx.send(sender, response)


if __name__ == "__main__":
    agent.run()
