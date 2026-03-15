"""Sales Outreach Automation - AI-powered cold outreach for KeyForAgents B2B"""
import os
import asyncio
import logging
from datetime import datetime
from typing import Optional
from dataclasses import dataclass
import httpx
from notion_client import AsyncClient as NotionClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NOTION_LEADS_DB = os.getenv("NOTION_LEADS_DB", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "dean@keyforagents.com")
FROM_NAME = os.getenv("FROM_NAME", "Dean - KeyForAgents")

notion = NotionClient(auth=NOTION_TOKEN)

EMAIL_TEMPLATES = {
    "initial": {
        "subject": "Quick question about your real estate business, {name}",
        "body": """Hi {name},

I noticed you're a real estate agent in {location} - I wanted to reach out about KeyForAgents.com.

We've built an AI automation platform specifically for real estate agents that:
- Auto-qualifies and follows up with leads 24/7
- Syncs all your contacts to a CRM automatically
- Sends personalised follow-up sequences without any manual work

Would you be open to a quick 15-minute call this week to see if it's a fit?

Best,
{from_name}
KeyForAgents.com
https://keyforagents.com
"""
    },
    "followup_1": {
        "subject": "Re: Quick question about your real estate business, {name}",
        "body": """Hi {name},

Just circling back on my previous email.

I know you're busy - I'll keep this brief. KeyForAgents helps agents like you save 10+ hours per week on lead follow-up.

Worth a quick look? https://keyforagents.com

{from_name}
"""
    },
    "followup_2": {
        "subject": "Last one from me, {name}",
        "body": """Hi {name},

I'll leave you alone after this - promise!

If you ever want to automate your lead follow-up and grow your GCI without working more hours, KeyForAgents is here: https://keyforagents.com

Wishing you a great week,
{from_name}
"""
    }
}


@dataclass
class OutreachContact:
    page_id: str
    name: str
    email: str
    location: str
    sequence_step: int = 0
    last_contact: Optional[str] = None


class SalesOutreach:
    """Automated B2B sales outreach for KeyForAgents."""

    def __init__(self):
        self.sent_count = 0
        self.errors = 0

    async def get_contacts_to_contact(self) -> list[OutreachContact]:
        """Fetch leads ready for outreach from Notion."""
        try:
            resp = await notion.databases.query(
                database_id=NOTION_LEADS_DB,
                filter={
                    "and": [
                        {"property": "Status", "select": {"equals": "Qualified"}},
                        {"property": "Outreach Sent", "checkbox": {"equals": False}}
                    ]
                }
            )
            contacts = []
            for page in resp.get("results", []):
                props = page["properties"]
                name = props.get("Name", {}).get("title", [{}])[0].get("plain_text", "")
                email = props.get("Email", {}).get("email", "")
                location = props.get("Location", {}).get("rich_text", [{}])[0].get("plain_text", "Australia")
                step = props.get("Sequence Step", {}).get("number", 0) or 0
                if email and name:
                    contacts.append(OutreachContact(
                        page_id=page["id"],
                        name=name,
                        email=email,
                        location=location,
                        sequence_step=step
                    ))
            return contacts
        except Exception as e:
            logger.error(f"Failed to fetch contacts: {e}")
            return []

    async def send_email(self, to_email: str, subject: str, body: str) -> bool:
        """Send email via SMTP."""
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        if not SMTP_USER or not SMTP_PASS:
            logger.warning("SMTP not configured - skipping send")
            return False
        try:
            msg = MIMEMultipart()
            msg["From"] = f"{FROM_NAME} <{FROM_EMAIL}>"
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(FROM_EMAIL, to_email, msg.as_string())
            return True
        except Exception as e:
            logger.error(f"Email send failed to {to_email}: {e}")
            return False

    def build_email(self, contact: OutreachContact) -> tuple[str, str]:
        """Build email subject and body for contact's sequence step."""
        step_map = {0: "initial", 1: "followup_1", 2: "followup_2"}
        template_key = step_map.get(contact.sequence_step, "followup_2")
        template = EMAIL_TEMPLATES[template_key]
        ctx = {
            "name": contact.name.split()[0],
            "location": contact.location,
            "from_name": FROM_NAME
        }
        subject = template["subject"].format(**ctx)
        body = template["body"].format(**ctx)
        return subject, body

    async def update_contact(self, page_id: str, step: int):
        """Update outreach step in Notion."""
        try:
            next_step = step + 1
            done = next_step >= 3
            await notion.pages.update(
                page_id=page_id,
                properties={
                    "Sequence Step": {"number": next_step},
                    "Outreach Sent": {"checkbox": done},
                    "Last Contact": {"date": {"start": datetime.utcnow().isoformat()}},
                    "Status": {"select": {"name": "Outreach Complete" if done else "In Sequence"}}
                }
            )
        except Exception as e:
            logger.error(f"Update failed for {page_id}: {e}")

    async def notify_telegram(self, msg: str):
        if not TELEGRAM_BOT_TOKEN:
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        async with httpx.AsyncClient() as client:
            try:
                await client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"})
            except Exception:
                pass

    async def run_cycle(self):
        """Run one outreach cycle - send emails to all ready contacts."""
        contacts = await self.get_contacts_to_contact()
        logger.info(f"Outreach cycle: {len(contacts)} contacts to process")
        for contact in contacts:
            subject, body = self.build_email(contact)
            success = await self.send_email(contact.email, subject, body)
            if success:
                self.sent_count += 1
                await self.update_contact(contact.page_id, contact.sequence_step)
                logger.info(f"Sent step {contact.sequence_step} to {contact.name} <{contact.email}>")
            else:
                self.errors += 1
            await asyncio.sleep(5)  # Rate limit
        summary = f"<b>Outreach Cycle Done</b>\nSent: {self.sent_count} | Errors: {self.errors}"
        await self.notify_telegram(summary)

    async def run_forever(self, interval_hours: int = 12):
        """Run outreach on schedule."""
        logger.info(f"Sales Outreach Agent started - every {interval_hours}h")
        while True:
            try:
                await self.run_cycle()
            except Exception as e:
                logger.error(f"Cycle error: {e}")
            await asyncio.sleep(interval_hours * 3600)


if __name__ == "__main__":
    agent = SalesOutreach()
    asyncio.run(agent.run_forever(interval_hours=12))
