from __future__ import annotations

import os

from dotenv import load_dotenv
from uagents import Agent, Context, Model

load_dotenv()


class IrrigationRequest(Model):
    soil_moisture: float
    rain_chance: float


class IrrigationResponse(Model):
    action: str
    liters: float
    urgency: str


agent = Agent(
    name="agrimind-irrigation-agent",
    seed=os.getenv("IRRIGATION_SEED_PHRASE", "replace_with_unique_random_string"),
    port=int(os.getenv("IRRIGATION_AGENT_PORT", "8012")),
    mailbox=os.getenv("ENABLE_MAILBOX", "true").lower() == "true",
    publish_agent_details=os.getenv("PUBLISH_AGENT_DETAILS", "true").lower() == "true",
)


@agent.on_message(model=IrrigationRequest)
async def handle_irrigation(ctx: Context, sender: str, msg: IrrigationRequest) -> None:
    if msg.soil_moisture < 32 and msg.rain_chance < 40:
        response = IrrigationResponse(action="water_now", liters=1.8, urgency="high")
    elif 32 <= msg.soil_moisture <= 58 and msg.rain_chance >= 55:
        response = IrrigationResponse(action="no_watering", liters=0, urgency="low")
    else:
        response = IrrigationResponse(action="light_watering", liters=0.8, urgency="medium")

    await ctx.send(sender, response)


if __name__ == "__main__":
    agent.run()
