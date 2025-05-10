"""Calendar platform for Exchange Calendar."""
from datetime import datetime, timedelta
import logging
from typing import Any, List

from exchangelib import Account, Credentials, Configuration, DELEGATE, EWSTimeZone
from exchangelib.items import CalendarItem
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the calendar platform."""
    config = hass.data[DOMAIN][config_entry.entry_id]
    calendar = ExchangeCalendar(hass, config)
    async_add_entities([calendar])

class ExchangeCalendar(CalendarEntity):
    """A calendar entity that pulls events from an Exchange server."""

    def __init__(self, hass: HomeAssistant, config: dict) -> None:
        """Initialize the calendar."""
        self.hass = hass
        self._config = config
        self._events: List[CalendarEvent] = []
        self._attr_name = config.get("calendar_name", "Exchange Calendar")
        self._attr_unique_id = f"calendar_{config['server']}"
        self._last_event_ids = set()
        self._account = None

    async def _get_account(self) -> Account:
        """Get or create an Exchange account connection."""
        if self._account is None:
            credentials = Credentials(
                username=self._config["username"],
                password=self._config["password"],
            )
            config = Configuration(
                server=self._config["server"],
                credentials=credentials,
            )
            timezone = EWSTimeZone(self._config["timezone"])
            self._account = Account(
                primary_smtp_address=self._config["username"],
                config=config,
                autodiscover=False,
                access_type=DELEGATE,
                default_timezone=timezone,
            )
        return self._account

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        now = dt_util.now()
        for event in sorted(self._events, key=lambda x: x.start):
            if event.start >= now:
                return event
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> List[CalendarEvent]:
        """Get all events in a specific time frame."""
        return [
            event for event in self._events
            if start_date <= event.start <= end_date
        ]

    async def async_update(self) -> None:
        """Update calendar events from Exchange server."""
        try:
            account = await self._get_account()
            now = dt_util.now()
            start = now - timedelta(days=1)
            end = now + timedelta(days=30)

            events = account.calendar.view(start=start, end=end)
            new_events = []
            current_event_ids = set()

            for event in events:
                event_id = event.item_id
                current_event_ids.add(event_id)

                start = event.start
                end = event.end
                summary = event.subject or "No title"
                description = event.body or ""

                calendar_event = CalendarEvent(
                    start=start,
                    end=end,
                    summary=summary,
                    description=description,
                )
                new_events.append(calendar_event)

                # Trigger event for new or updated events
                if event_id not in self._last_event_ids:
                    self.hass.bus.async_fire(
                        "calendar.event_created",
                        {"event_id": event_id, "summary": summary, "start": start},
                    )
                else:
                    self.hass.bus.async_fire(
                        "calendar.event_updated",
                        {"event_id": event_id, "summary": summary, "start": start},
                    )

            self._events = new_events
            self._last_event_ids = current_event_ids

        except Exception as err:
            _LOGGER.error("Error updating calendar: %s", err)

    async def async_create_event(self, **kwargs: Any) -> None:
        """Create a new event in the calendar."""
        try:
            account = await self._get_account()
            summary = kwargs.get("summary", "New Event")
            start = dt_util.parse_datetime(kwargs.get("start")) or dt_util.now()
            end = dt_util.parse_datetime(kwargs.get("end")) or start + timedelta(hours=1)
            description = kwargs.get("description", "")

            event = CalendarItem(
                account=account,
                folder=account.calendar,
                subject=summary,
                body=description,
                start=start,
                end=end,
            )
            event.save()
            _LOGGER.info("Created new event: %s", summary)
            await self.async_update()

        except Exception as err:
            _LOGGER.error("Error creating event: %s", err)

    async def async_delete_event(self, **kwargs: Any) -> None:
        """Delete an event from the calendar by item_id."""
        try:
            account = await self._get_account()
            event_id = kwargs.get("event_id")
            if not event_id:
                _LOGGER.error("No event_id provided")
                return

            events = account.calendar.filter(item_id=event_id)
            for event in events:
                event.delete()
                _LOGGER.info("Deleted event with ID: %s", event_id)
                break
            else:
                _LOGGER.error("Event with ID %s not found", event_id)

            await self.async_update()

        except Exception as err:
            _LOGGER.error("Error deleting event: %s", err)

    async def async_search_events(self, **kwargs: Any) -> List[dict]:
        """Search for events matching a search term within a time range."""
        try:
            account = await self._get_account()
            search_term = kwargs.get("search_term", "").lower()
            start = dt_util.parse_datetime(kwargs.get("start")) or dt_util.now()
            end = dt_util.parse_datetime(kwargs.get("end")) or start + timedelta(days=30)

            events = account.calendar.view(start=start, end=end)
            matching_events = []

            for event in events:
                summary = (event.subject or "").lower()
                description = (event.body or "").lower()
                if search_term in summary or search_term in description:
                    matching_events.append({
                        "event_id": event.item_id,
                        "summary": event.subject or "No title",
                        "description": event.body or "",
                        "start": event.start.isoformat(),
                        "end": event.end.isoformat(),
                    })

            _LOGGER.info("Found %d events matching '%s'", len(matching_events), search_term)
            return matching_events

        except Exception as err:
            _LOGGER.error("Error searching events: %s", err)
            return []"""Calendar platform for Exchange Calendar."""
from datetime import datetime, timedelta
import logging
from typing import Any, List

from exchangelib import Account, Credentials, Configuration, DELEGATE, EWSTimeZone
from exchangelib.items import CalendarItem
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the calendar platform."""
    config = hass.data[DOMAIN][config_entry.entry_id]
    calendar = ExchangeCalendar(hass, config)
    async_add_entities([calendar])

class ExchangeCalendar(CalendarEntity):
    """A calendar entity that pulls events from an Exchange server."""

    def __init__(self, hass: HomeAssistant, config: dict) -> None:
        """Initialize the calendar."""
        self.hass = hass
        self._config = config
        self._events: List[CalendarEvent] = []
        self._attr_name = config.get("calendar_name", "Exchange Calendar")
        self._attr_unique_id = f"calendar_{config['server']}"
        self._last_event_ids = set()
        self._account = None

    async def _get_account(self) -> Account:
        """Get or create an Exchange account connection."""
        if self._account is None:
            credentials = Credentials(
                username=self._config["username"],
                password=self._config["password"],
            )
            config = Configuration(
                server=self._config["server"],
                credentials=credentials,
            )
            timezone = EWSTimeZone(self._config["timezone"])
            self._account = Account(
                primary_smtp_address=self._config["username"],
                config=config,
                autodiscover=False,
                access_type=DELEGATE,
                default_timezone=timezone,
            )
        return self._account

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        now = dt_util.now()
        for event in sorted(self._events, key=lambda x: x.start):
            if event.start >= now:
                return event
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> List[CalendarEvent]:
        """Get all events in a specific time frame."""
        return [
            event for event in self._events
            if start_date <= event.start <= end_date
        ]

    async def async_update(self) -> None:
        """Update calendar events from Exchange server."""
        try:
            account = await self._get_account()
            now = dt_util.now()
            start = now - timedelta(days=1)
            end = now + timedelta(days=30)

            events = account.calendar.view(start=start, end=end)
            new_events = []
            current_event_ids = set()

            for event in events:
                event_id = event.item_id
                current_event_ids.add(event_id)

                start = event.start
                end = event.end
                summary = event.subject or "No title"
                description = event.body or ""

                calendar_event = CalendarEvent(
                    start=start,
                    end=end,
                    summary=summary,
                    description=description,
                )
                new_events.append(calendar_event)

                # Trigger event for new or updated events
                if event_id not in self._last_event_ids:
                    self.hass.bus.async_fire(
                        "calendar.event_created",
                        {"event_id": event_id, "summary": summary, "start": start},
                    )
                else:
                    self.hass.bus.async_fire(
                        "calendar.event_updated",
                        {"event_id": event_id, "summary": summary, "start": start},
                    )

            self._events = new_events
            self._last_event_ids = current_event_ids

        except Exception as err:
            _LOGGER.error("Error updating calendar: %s", err)

    async def async_create_event(self, **kwargs: Any) -> None:
        """Create a new event in the calendar."""
        try:
            account = await self._get_account()
            summary = kwargs.get("summary", "New Event")
            start = dt_util.parse_datetime(kwargs.get("start")) or dt_util.now()
            end = dt_util.parse_datetime(kwargs.get("end")) or start + timedelta(hours=1)
            description = kwargs.get("description", "")

            event = CalendarItem(
                account=account,
                folder=account.calendar,
                subject=summary,
                body=description,
                start=start,
                end=end,
            )
            event.save()
            _LOGGER.info("Created new event: %s", summary)
            await self.async_update()

        except Exception as err:
            _LOGGER.error("Error creating event: %s", err)

    async def async_delete_event(self, **kwargs: Any) -> None:
        """Delete an event from the calendar by item_id."""
        try:
            account = await self._get_account()
            event_id = kwargs.get("event_id")
            if not event_id:
                _LOGGER.error("No event_id provided")
                return

            events = account.calendar.filter(item_id=event_id)
            for event in events:
                event.delete()
                _LOGGER.info("Deleted event with ID: %s", event_id)
                break
            else:
                _LOGGER.error("Event with ID %s not found", event_id)

            await self.async_update()

        except Exception as err:
            _LOGGER.error("Error deleting event: %s", err)

    async def async_search_events(self, **kwargs: Any) -> List[dict]:
        """Search for events matching a search term within a time range."""
        try:
            account = await self._get_account()
            search_term = kwargs.get("search_term", "").lower()
            start = dt_util.parse_datetime(kwargs.get("start")) or dt_util.now()
            end = dt_util.parse_datetime(kwargs.get("end")) or start + timedelta(days=30)

            events = account.calendar.view(start=start, end=end)
            matching_events = []

            for event in events:
                summary = (event.subject or "").lower()
                description = (event.body or "").lower()
                if search_term in summary or search_term in description:
                    matching_events.append({
                        "event_id": event.item_id,
                        "summary": event.subject or "No title",
                        "description": event.body or "",
                        "start": event.start.isoformat(),
                        "end": event.end.isoformat(),
                    })

            _LOGGER.info("Found %d events matching '%s'", len(matching_events), search_term)
            return matching_events

        except Exception as err:
            _LOGGER.error("Error searching events: %s", err)
            return []
