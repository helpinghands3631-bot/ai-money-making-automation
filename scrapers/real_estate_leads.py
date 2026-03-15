"""Real Estate Lead Scraper - finds property listings and generates agent leads"""
import os
import asyncio
import logging
from datetime import datetime
from dataclasses import dataclass
from typing import Optional
import httpx
from notion_client import AsyncClient as NotionClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NOTION_LEADS_DB = os.getenv("NOTION_LEADS_DB", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

notion = NotionClient(auth=NOTION_TOKEN)

SEARCH_LOCATIONS = [
    "Shepparton VIC",
    "Kialla VIC",
    "Mooroopna VIC",
    "Kyabram VIC",
    "Echuca VIC"
]


@dataclass
class PropertyLead:
    address: str
    suburb: str
    price: Optional[float]
    agent_name: Optional[str]
    agent_email: Optional[str]
    agent_phone: Optional[str]
    listing_url: str
    source: str
    created_at: str = ""

    def __post_init__(self):
        self.created_at = datetime.utcnow().isoformat()


class RealEstateLeadScraper:
    """Scraper for real estate agent leads in regional Victoria."""

    def __init__(self):
        self.leads_found = 0
        self.leads_saved = 0

    async def search_domain(self, location: str) -> list[PropertyLead]:
        """Search Domain.com.au for listings in a location."""
        leads = []
        encoded = location.replace(" ", "%20")
        url = f"https://www.domain.com.au/rent/?suburb={encoded}&state=vic"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    content = resp.text
                    # Extract agent data from JSON-LD or meta tags
                    import re
                    emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', content)
                    phones = re.findall(r'0[45]\d{8}', content)
                    agent_emails = [e for e in emails if 'domain.com' not in e][:3]
                    for i, email in enumerate(agent_emails):
                        lead = PropertyLead(
                            address=f"Listing {i+1} - {location}",
                            suburb=location,
                            price=None,
                            agent_name=None,
                            agent_email=email,
                            agent_phone=phones[i] if i < len(phones) else None,
                            listing_url=url,
                            source="domain.com.au"
                        )
                        leads.append(lead)
        except Exception as e:
            logger.error(f"Domain search failed for {location}: {e}")
        return leads

    async def save_to_notion(self, lead: PropertyLead) -> bool:
        """Save lead to Notion database."""
        if not NOTION_LEADS_DB:
            return False
        try:
            await notion.pages.create(
                parent={"database_id": NOTION_LEADS_DB},
                properties={
                    "Name": {"title": [{"text": {"content": lead.address}}]},
                    "Email": {"email": lead.agent_email},
                    "Source": {"select": {"name": lead.source}},
                    "Status": {"select": {"name": "New"}},
                    "Notes": {"rich_text": [{"text": {"content": f"Suburb: {lead.suburb} | URL: {lead.listing_url}"}}]}
                }
            )
            self.leads_saved += 1
            return True
        except Exception as e:
            logger.error(f"Notion save failed: {e}")
            return False

    async def notify_telegram(self, message: str):
        """Send Telegram summary."""
        if not TELEGRAM_BOT_TOKEN:
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        async with httpx.AsyncClient() as client:
            try:
                await client.post(url, json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": message,
                    "parse_mode": "HTML"
                })
            except Exception as e:
                logger.error(f"Telegram error: {e}")

    async def run(self):
        """Run full scrape cycle across all locations."""
        logger.info(f"Starting real estate lead scrape: {len(SEARCH_LOCATIONS)} locations")
        all_leads = []
        for location in SEARCH_LOCATIONS:
            leads = await self.search_domain(location)
            all_leads.extend(leads)
            logger.info(f"{location}: {len(leads)} leads found")
            await asyncio.sleep(2)  # Polite delay

        self.leads_found = len(all_leads)
        tasks = [self.save_to_notion(lead) for lead in all_leads]
        await asyncio.gather(*tasks)

        summary = (
            f"<b>Real Estate Scrape Complete</b>\n"
            f"Locations: {len(SEARCH_LOCATIONS)}\n"
            f"Leads found: {self.leads_found}\n"
            f"Leads saved: {self.leads_saved}"
        )
        await self.notify_telegram(summary)
        logger.info(summary)


if __name__ == "__main__":
    scraper = RealEstateLeadScraper()
    asyncio.run(scraper.run())
