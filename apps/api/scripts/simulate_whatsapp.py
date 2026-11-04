"""Play a WhatsApp conversation against the bot without WhatsApp, Meta or any charges.

    cd apps/api
    python scripts/simulate_whatsapp.py                 # scripted demo of all three functions
    python scripts/simulate_whatsapp.py --scenario report
    python scripts/simulate_whatsapp.py --interactive   # you type as the WhatsApp user
    python scripts/simulate_whatsapp.py --keep          # keep the rows it creates (default: roll back)

What is real: the PostgreSQL conversation state, the conversation engine, the report intake,
the subscription service and the route check against your database's published alerts.
What is faked: WhatsApp (replies are recorded and printed, never sent), the verification-code
messenger (mock provider; the code is read from it), the place search and the routing engine
(a few Zimbabwean towns and straight-line routes). No OpenAI call is made. Everything runs in one
database transaction that is rolled back at the end unless --keep is given.

In interactive mode type text, ``tap:<id>`` for a button/list row (e.g. ``tap:2``), ``pin:<lat>,<lon>``
for a location pin, ``photo`` for an image, or ``quit``.
"""

import argparse
import itertools
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import get_engine  # noqa: E402
from app.integrations.whatsapp.client import MockWhatsAppClient  # noqa: E402
from app.integrations.whatsapp.messages import LOCATION, MEDIA, REPLY, TEXT, InboundEvent  # noqa: E402
from app.models import WhatsAppInbound  # noqa: E402
from app.services.notifications import get_notification_provider  # noqa: E402
from app.services.routing.mock import MockRoutingProvider  # noqa: E402
from app.services.whatsapp import conversation  # noqa: E402
from app.services.whatsapp.context import Deps, Place  # noqa: E402
from app.services.whatsapp.inbox import StoreResult, store_message  # noqa: E402
from app.services.whatsapp.route_check import StaticResolver  # noqa: E402

TOWNS = {
    "harare": (-17.8292, 31.0522),
    "mutare": (-18.9707, 32.6709),
    "marondera": (-18.1853, 31.5519),
    "bulawayo": (-20.1325, 28.6265),
    "gweru": (-19.4500, 29.8167),
    "masvingo": (-20.0744, 30.8328),
}
SCENARIOS = {
    "report": [
        "hi", "1", "Harare-Mutare road near Marondera", "A kombi overturned and people are injured. Call 0772 123 456.",
        "1", "1",
    ],
    "subscribe": ["menu", "2", "1", "Harare, Mashonaland East", "1", "<OTP>", "stop"],
    "route": ["menu", "3", "Harare", "Mutare"],
}


class Simulator:
    def __init__(self, session: Session, wa_id: str, settings) -> None:
        self.session, self.wa_id, self.settings = session, wa_id, settings
        self.client = MockWhatsAppClient()
        places = {name: [Place(name.title() + ", Zimbabwe", lat, lon)] for name, (lat, lon) in TOWNS.items()}
        self.deps = Deps(resolver=StaticResolver(places), routing_provider=lambda s: MockRoutingProvider(TOWNS))
        self._ids = itertools.count(1)

    def otp(self) -> str:
        provider = get_notification_provider(self.settings, "whatsapp")
        return provider.last_code_for("+" + self.wa_id) or "000000"  # type: ignore[attr-defined]

    def send(self, line: str) -> None:
        if line == "<OTP>":
            line = self.otp()
        fields: dict = {"kind": TEXT, "text": line}
        if line.startswith("tap:"):
            fields = {"kind": REPLY, "reply_id": line[4:], "text": ""}
        elif line.startswith("pin:"):
            lat, lon = (float(x) for x in line[4:].split(","))
            fields = {"kind": LOCATION, "latitude": lat, "longitude": lon}
        elif line == "photo":
            fields = {"kind": MEDIA}
        event = InboundEvent(wamid=f"sim.{next(self._ids)}.{datetime.now(UTC):%H%M%S%f}", wa_id=self.wa_id, sent_at=datetime.now(UTC), **fields)
        print(f"\nUSER> {line}")
        before = len(self.client.sent)
        store_message(self.session, self.settings, event, StoreResult())
        row = self.session.scalar(select(WhatsAppInbound).where(WhatsAppInbound.wamid == event.wamid))
        if row is None:
            print("      (dropped: rate limit)")
            return
        now = datetime.now(UTC)
        conversation.process(self.session, self.settings, self.client, self.deps, row, now=now)
        row.status, row.processed_at, row.payload = "done", now, {}
        self.session.commit()
        for sent in self.client.sent[before:]:
            choices = f"   [{sent.kind}: {', '.join(sent.choices)}]" if sent.choices else ""
            print("BOT> " + sent.body.replace("\n", "\n     ") + choices)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scenario", choices=[*SCENARIOS, "all"], default="all")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--phone", default="263770000999", help="simulated sender (digits, with country code)")
    parser.add_argument("--keep", action="store_true", help="commit instead of rolling back")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")  # emoji in replies; Windows consoles default to cp1252

    settings = get_settings()
    if settings.notification_provider != "mock":
        print("Refusing to run: NOTIFICATION_PROVIDER must be 'mock' for the simulator.")
        return 2

    connection = get_engine().connect()
    outer = connection.begin()
    # Inside the bot, commit() only releases a savepoint, so the whole run can be rolled back.
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        sim = Simulator(session, args.phone, settings)
        if args.interactive:
            print("Type as the WhatsApp user. 'quit' to stop.")
            while (line := input("\nUSER> ").strip()) != "quit":
                if line:
                    sim.send(line)
        else:
            names = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
            for name in names:
                print(f"\n=========== scenario: {name} ===========")
                for line in SCENARIOS[name]:
                    sim.send(line)
        if args.keep:
            outer.commit()
            print("\nKept the rows created by this run.")
        else:
            outer.rollback()
            print("\nRolled back: nothing from this run was saved.")
    finally:
        session.close()
        connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
