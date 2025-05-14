from datetime import datetime, timedelta
import logging
from typing import Any, Dict, List

import pytz
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN, CONF_TIMEZONE
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up the calendar platform."""
    account = hass.data[DOMAIN][entry.entry_id]["account"]
    timezone = hass.data[DOMAIN][entry.entry_id]["timezone"]
    async_add_entities([ExchangeCalendarEntity(account, timezone, entry.title)])

class ExchangeCalendarEntity(CalendarEntity):
    """A calendar entity for Exchange Calendar."""

    def __init__(self, account, timezone, name):
        self._account = account
        self._timezone = timezone
        self._name = name
        self._attr_unique_id = f"{DOMAIN}_{name}"
        self._event = None

    @property
    def name(self) -> str:
        """Return the name of the calendar."""
        return self._name

    @property
    def event(self) -> CalendarEvent:
        """Return the next upcoming event."""
        return self._event

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> List[CalendarEvent]:
        """Get events in the given date range."""
        try:
            def fetch_and_materialize_events():
                """Synchronous function to fetch and fully materialize events."""
                # Fetch events and convert generator/iterator to a list to ensure all blocking calls happen here
                events = list(self._account.calendar.view(
                    start=start_date.astimezone(self._timezone),
                    end=end_date.astimezone(self._timezone),
                ))
                # Convert to list of dicts to avoid passing complex objects across threads
                return [
                    {
                        "subject": event.subject,
                        "start": event.start,
                        "end": event.end,
                        "body": event.body,
                        "location": event.location,
                        "item_id": event.id,
                    }
                    for event in events
                ]

            # Run the blocking operation in a thread pool
            event_dicts = await hass.loop.run_in_executor(None, fetch_and_materialize_events)

            # Convert event dicts to CalendarEvent objects in async context
            return [
                CalendarEvent(
                    summary=event_dict["subject"],
                    start=event_dict["start"],
                    end=event_dict["end"],
                    description=event_dict["body"],
                    location=event_dict["location"],
                    uid=event_dict["item_id"],
                )
                for event_dict in event_dicts
            ]
        except Exception as err:
            _LOGGER.error("Failed to fetch events: %s", err)
            return []

    async def async_update(self) -> None:
        """Update the next event."""
        now = dt_util.now()

        events = await self.async_get_events(
            hass=self.hass,
            start_date=now,
            end_date=now + timedelta(days=30),
        )
        self._event = min(events, key=lambda x: x.start) if events else None
