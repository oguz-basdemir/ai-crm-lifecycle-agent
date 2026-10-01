# Five-minute portfolio walkthrough

1. Start API and dashboard; open CRM Overview. The default seed creates 180 synthetic accounts spanning all nine lifecycle stages. Explain that synthetic purchase value is a fixture, not measured revenue.
2. Open Lead Scoring and select `SYN-00005`. Show how demo intent, fit, engagement, referral source, and recency produce an explainable high score. Each contribution sums to the raw score; the displayed result is capped at 100.
3. In Segments compare high-intent prospects with inactive leads. In At-Risk Customers inspect `SYN-00007`: inactivity, usage decline, and support tickets drive retention risk regardless of acquisition score.
4. In AI Recommendations select `SYN-00005`, run the CRM Agent, and create a draft with AI disabled. Review the subject, email, CTA, and angle. Check the explicit review checkbox, approve, then record a simulated send. Show the audit record. No email is transmitted.
5. In Lifecycle Journeys enroll `SYN-00006` in onboarding. Advance one step: a welcome draft appears in the approval inbox. Approve and simulate that draft, then advance again to schedule education three days later. Move the sidebar simulation date forward to show the delay and engagement check.
6. Enroll `SYN-00003` in lead nurture. Its last step creates a qualification task; SQL readiness depends on current demo intent and score. Edit the synthetic profile to request a demo and re-evaluate to demonstrate qualification.
7. Enroll `SYN-00007` in win-back. On today’s date, edit customer_status to active, last_activity to today, usage_decline to 0, support_tickets to 0, and product_usage to 80. Advance the journey to show exit on reactivation.
8. Build a new uniquely named workflow with the visual step editor. Explain that templates are snapshotted per enrollment and every message remains approval-gated.

Optional: configure the external LLM in `.env` and restart the API, then enable the UI toggle. Compare advisory AI interpretation with the authoritative deterministic score. If a provider is unavailable, the UI labels the fallback.
