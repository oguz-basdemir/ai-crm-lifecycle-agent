"""Seeded scenario data; no real people, addresses, or company names."""

import random
from datetime import date, timedelta

from crm_agent.models import Contact


def generate_contacts(count: int = 180, seed: int = 42, today: date | None = None) -> list[Contact]:
    rng = random.Random(seed)
    today = today or date.today()
    contacts = []
    for i in range(count):
        # Nine archetypes guarantee all lifecycle stages and meaningful dashboard segments.
        scenario = i % 9
        activity_days = rng.randint(0, 6)
        status = "prospect"
        customer_since = None
        pages, downloads, opens, clicks, demo = 0, 0, 1, 0, False
        size, industry = 15, "Retail"
        usage, decline, tickets, value = 0, 0, 0, 0.0
        source = "Social"
        if scenario == 1:
            pages = 4
            activity_days = 35
        elif scenario == 2:
            size, industry, pages, downloads, opens = 150, "Software", 12, 2, 4
        elif scenario == 3:
            size, industry, pages, demo, activity_days, source = (
                150,
                "Software",
                12,
                True,
                10,
                "Referral",
            )
        elif scenario == 4:
            size, industry, pages, downloads, opens, clicks, demo = (
                250,
                "Software",
                25,
                4,
                8,
                4,
                True,
            )
            source = "Referral"
        else:
            if scenario >= 5:
                status = "active"
                customer_since = today - timedelta(days=90 if i % 2 else 12)
                pages, downloads, opens, clicks = 18, 3, 6, 3
                industry, size, source = "Manufacturing", 300, "Organic Search"
                usage, value = rng.randint(70, 95), float(rng.randint(4, 20) * 1200)
            if scenario == 6:
                status, activity_days, usage, decline, tickets = "inactive", 30, 18, 60, 5
                customer_since = today - timedelta(days=120)
            elif scenario in (7, 8):
                status, activity_days, usage = "churned", 65, 0
                customer_since = today - timedelta(days=180)
        contacts.append(
            Contact(
                contact_id=f"SYN-{i + 1:05d}",
                company=f"Demo {['Northstar', 'Cedar', 'Orbit', 'Aurora'][i % 4]} {i + 1:03d}",
                industry=industry,
                company_size=size + rng.randint(0, 9),
                acquisition_source=source,
                country=rng.choice(
                    ["Finland", "Germany", "United Kingdom", "United States", "Sweden"]
                ),
                pages_viewed=pages,
                content_downloads=downloads,
                email_opens=opens,
                email_clicks=clicks,
                demo_requested=demo,
                last_activity=today - timedelta(days=activity_days),
                created_at=today - timedelta(days=240),
                customer_since=customer_since,
                customer_status=status,
                purchase_value=value,
                product_usage=usage,
                usage_decline=decline,
                support_tickets=tickets,
                winback_eligible=scenario != 7,
                unsubscribed=i > 8 and i % 23 == 0,
                marketing_consent=not (i > 8 and i % 29 == 0),
            )
        )
    return contacts
