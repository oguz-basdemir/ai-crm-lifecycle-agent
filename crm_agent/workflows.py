"""Declarative journey templates; delays refer to the simulated evaluation date."""

from crm_agent.models import Workflow


def default_workflows() -> list[Workflow]:
    return [
        Workflow.model_validate(w)
        for w in [
            {
                "name": "onboarding",
                "description": "Welcome, educate, evaluate activation, and follow up.",
                "entry_stages": ["Customer"],
                "steps": [
                    {"kind": "message", "label": "Welcome to your workspace"},
                    {
                        "kind": "message",
                        "label": "Education: your first activation milestone",
                        "delay_days": 3,
                    },
                    {"kind": "check", "label": "Engagement check", "delay_days": 4},
                    {
                        "kind": "message",
                        "label": "Follow up with practical onboarding help",
                        "delay_days": 2,
                    },
                ],
            },
            {
                "name": "lead-nurture",
                "description": "Relevant content, engagement check, and sales qualification task.",
                "entry_stages": ["MQL"],
                "steps": [
                    {"kind": "message", "label": "Relevant industry content"},
                    {"kind": "check", "label": "Engagement check", "delay_days": 5},
                    {"kind": "task", "label": "Review SQL qualification"},
                ],
            },
            {
                "name": "win-back",
                "description": "Support offer, reminder, and automatic exit on reactivation.",
                "entry_stages": ["At Risk", "Win-back"],
                "exit_on_reactivation": True,
                "steps": [
                    {
                        "kind": "message",
                        "label": "Personalized incentive: complimentary adoption review",
                    },
                    {"kind": "message", "label": "Reminder: help is available", "delay_days": 7},
                    {"kind": "check", "label": "Reactivation check", "delay_days": 7},
                ],
            },
        ]
    ]
