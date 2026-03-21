"""Client example — connect and inspect the full agent card.

Start the agent card server first:
    uvicorn examples.agent_card.server:app

Then run this client:
    python -m examples.agent_card.client
"""

import asyncio

from a2akit import A2AClient


async def main():
    async with A2AClient("http://localhost:8000") as client:
        card = client.agent_card
        print(f"Name: {card.name}")
        print(f"Description: {card.description}")
        print(f"Version: {card.version}")
        print(f"Protocol: {card.preferred_transport}")

        if card.provider:
            print(f"\nProvider: {card.provider.organization} ({card.provider.url})")

        if card.capabilities:
            caps = card.capabilities
            print("\nCapabilities:")
            print(f"  Streaming: {caps.streaming}")
            print(f"  Push notifications: {caps.push_notifications}")
            print(f"  State transition history: {caps.state_transition_history}")

        if card.skills:
            print(f"\nSkills ({len(card.skills)}):")
            for skill in card.skills:
                print(f"  - {skill.name}: {skill.description}")
                if skill.tags:
                    print(f"    Tags: {', '.join(skill.tags)}")

        if card.security_schemes:
            print(f"\nSecurity schemes: {list(card.security_schemes.keys())}")

        result = await client.send("Translate this to French")
        print(f"\nResponse: {result.text}")


if __name__ == "__main__":
    asyncio.run(main())
