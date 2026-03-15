"""AI Income Agent - Automated revenue generation and opportunity finder"""
import os
import asyncio
import logging
from datetime import datetime
from typing import Optional
import httpx
from notion_client import AsyncClient as NotionClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NOTION_PIPELINE_DB = os.getenv("NOTION_PIPELINE_DB", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")

notion = NotionClient(auth=NOTION_TOKEN)

REVENUE_STREAMS = [
    {"name": "KeyForAgents SaaS", "url": "https://keyforagents.com", "target_mrr": 5000},
    {"name": "Helping Hands NDIS", "url": "https://helpinghands.com.au", "target_mrr": 3000},
    {"name": "AI Automation Consulting", "url": None, "target_mrr": 2000},
    {"name": "n8n Workflow Templates", "url": None, "target_mrr": 1000},
]


class IncomeAgent:
    """Autonomous agent for tracking and growing income streams."""

    def __init__(self):
        self.total_revenue = 0.0
        self.opportunities = []

    async def scan_pipeline(self):
        """Scan Notion Side Hustle Pipeline for active opportunities."""
        try:
            response = await notion.databases.query(
                database_id=NOTION_PIPELINE_DB,
                filter={"property": "Status", "select": {"equals": "Active"}}
            )
            return response.get("results", [])
        except Exception as e:
            logger.error(f"Pipeline scan failed: {e}")
            return []

    async def check_stripe_revenue(self) -> float:
        """Query Stripe for current month revenue."""
        if not STRIPE_SECRET_KEY:
            return 0.0
        try:
            now = datetime.utcnow()
            start_of_month = int(datetime(now.year, now.month, 1).timestamp())
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.stripe.com/v1/balance_transactions",
                    params={"created[gte]": start_of_month, "limit": 100, "type": "charge"},
                    auth=(STRIPE_SECRET_KEY, "")
                )
                data = resp.json()
                total = sum(t["amount"] for t in data.get("data", []) if t.get("status") == "available")
                return total / 100  # Convert cents to dollars
        except Exception as e:
            logger.error(f"Stripe check failed: {e}")
            return 0.0

    async def generate_opportunity_report(self) -> str:
        """Generate a revenue opportunity report."""
        revenue = await self.check_stripe_revenue()
        pipeline = await self.scan_pipeline()

        lines = ["<b>Income Agent Report</b>", f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC", ""]
        lines.append(f"Stripe Revenue (this month): ${revenue:,.2f}")
        lines.append(f"Active pipeline items: {len(pipeline)}")
        lines.append("")
        lines.append("<b>Revenue Streams:</b>")
        for stream in REVENUE_STREAMS:
            lines.append(f"- {stream['name']}: target ${stream['target_mrr']:,}/mo")

        total_target = sum(s["target_mrr"] for s in REVENUE_STREAMS)
        gap = total_target - revenue
        lines.append("")
        lines.append(f"Total MRR target: ${total_target:,}")
        lines.append(f"Current gap: ${gap:,.2f}")

        if gap > 0:
            lines.append(f"Action needed: Close ${gap:,.2f} gap this month")
        else:
            lines.append("TARGET MET! Time to raise the bar.")

        return "\n".join(lines)

    async def notify_telegram(self, message: str):
        """Send Telegram notification."""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
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

    async def run_daily(self):
        """Run daily income check and report."""
        logger.info("Running daily income report...")
        report = await self.generate_opportunity_report()
        await self.notify_telegram(report)
        logger.info(report)

    async def run_forever(self, interval_hours: int = 24):
        """Run agent on schedule."""
        logger.info(f"Income Agent started — reporting every {interval_hours}h")
        while True:
            try:
                await self.run_daily()
            except Exception as e:
                logger.error(f"Error: {e}")
            await asyncio.sleep(interval_hours * 3600)


if __name__ == "__main__":
    agent = IncomeAgent()
    asyncio.run(agent.run_forever(interval_hours=24))
