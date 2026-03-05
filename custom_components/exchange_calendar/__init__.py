import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict

import pytz
from exchangelib import Account, Credentials, Configuration, DELEGATE, CalendarItem
from exchangelib.errors import EWSError, TransportError
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.util import dt as dt_util
from exchangelib.winzone import MS_TIMEZONE_TO_IANA_MAP

import ssl
import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SERVER,
    CONF_TIMEZONE,
    CONF_AUTH_TYPE,
    SERVICE_CREATE_EVENT,
    SERVICE_DELETE_EVENT,
    SERVICE_SEARCH_EVENT,
    SERVICE_EDIT_EVENT,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CALENDAR]

CREATE_EVENT_SCHEMA = vol.Schema(
    {
        vol.Required("subject", default="New Event"): cv.string,
        vol.Required("date_start"): cv.datetime,
        vol.Required("date_end"): cv.datetime,
        vol.Optional("location"): cv.string,
        vol.Optional("body"): cv.string,
    }
)

SEARCH_EVENTS_SCHEMA = vol.Schema(
    {
        vol.Required("date_start"): cv.datetime,
        vol.Required("date_end"): cv.datetime,
    }
)

EDIT_EVENT_SCHEMA = vol.Schema(
    {
        vol.Required("subject"): cv.string,
        vol.Optional("new_subject"): cv.string,
        vol.Optional("new_date_start"): cv.datetime,
        vol.Optional("new_date_end"): cv.datetime,
        vol.Optional("new_location"): cv.string,
        vol.Optional("new_body"): cv.string,
        vol.Optional("search_start"): cv.datetime,
        vol.Optional("search_end"): cv.datetime,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Exchange Calendar from a config entry."""
    email     = entry.data[CONF_EMAIL]
    password  = entry.options.get(CONF_PASSWORD) or entry.data[CONF_PASSWORD]
    server    = entry.data[CONF_SERVER]
    timezone  = entry.options.get(CONF_TIMEZONE) or entry.data.get(CONF_TIMEZONE, "UTC")
    auth_type = entry.data.get(CONF_AUTH_TYPE, "NTLM")

    if "Customized Time Zone" not in MS_TIMEZONE_TO_IANA_MAP:
        MS_TIMEZONE_TO_IANA_MAP["Customized Time Zone"] = timezone

    try:
        credentials = Credentials(username=email, password=password)
        config = Configuration(
            server=server,
            credentials=credentials,
            auth_type=auth_type,
        )
        account = await hass.async_add_executor_job(
            lambda: Account(
                primary_smtp_address=email,
                config=config,
                autodiscover=False,
                access_type=DELEGATE,
            )
        )

        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
            "account": account,
            "timezone": dt_util.get_time_zone(timezone),
        }

        async_register_services(hass, entry)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True

    except TransportError as err:
        _LOGGER.error("Failed to connect to Exchange server %s: %s", server, err)
        raise ConfigEntryNotReady from err
    except EWSError as err:
        _LOGGER.error("Failed to set up Exchange Calendar: %s", err)
        raise ConfigEntryNotReady from err


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


def async_register_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register Exchange Calendar services."""
    account  = hass.data[DOMAIN][entry.entry_id]["account"]
    timezone = hass.data[DOMAIN][entry.entry_id]["timezone"]

    async def create_event(call: ServiceCall) -> ServiceResponse:
        """Create a calendar event, or update it if an event with the same subject already exists."""
        try:
            validated_data = CREATE_EVENT_SCHEMA(dict(call.data))
            subject  = validated_data["subject"]
            start_dt = validated_data["date_start"].astimezone(timezone)
            end_dt   = validated_data["date_end"].astimezone(timezone)
            location = validated_data.get("location")
            body     = validated_data.get("body")

            def upsert_event():
                # Search ±2 years for an existing event with exactly this subject
                now          = datetime.now(tz=timezone)
                search_start = now - timedelta(days=730)
                search_end   = now + timedelta(days=730)

                existing = [
                    e for e in account.calendar.view(start=search_start, end=search_end)
                    if e.subject and e.subject.lower() == subject.lower()
                ]

                if existing:
                    event          = existing[0]
                    event.start    = start_dt
                    event.end      = end_dt
                    event.location = location
                    event.body     = body
                    event.save(update_fields=["start", "end", "location", "body"])
                    _LOGGER.info("Updated existing event: %s", subject)
                    return True, None, "updated"
                else:
                    event = CalendarItem(
                        account=account,
                        folder=account.calendar,
                        subject=subject,
                        start=start_dt,
                        end=end_dt,
                        location=location,
                        body=body,
                    )
                    event.save()
                    _LOGGER.info("Created new event: %s", subject)
                    return True, None, "created"

            success, error, action = await hass.async_add_executor_job(upsert_event)

            if not success:
                _LOGGER.error("Failed to upsert event: %s", error)
                return {"success": False, "error": error}

            return {"success": True, "action": action}

        except vol.Invalid as err:
            _LOGGER.error("Invalid input for create_event: %s", err)
            return {"success": False, "error": str(err)}
        except Exception as err:
            _LOGGER.error("Failed to create/update event: %s", err)
            return {"success": False, "error": str(err)}

    async def delete_event(call: ServiceCall) -> ServiceResponse:
        """Delete a calendar event by ID."""
        event_id = call.data.get("event_id")
        try:
            event = await hass.async_add_executor_job(
                lambda: account.calendar.get(id=event_id)
            )
            if not event:
                raise ValueError(f"No event found with ID: {event_id}")
            await hass.async_add_executor_job(event.delete)
            _LOGGER.info("Deleted event: %s", event_id)
            return {"success": True}
        except Exception as err:
            _LOGGER.error("Failed to delete event: %s", err)
            return {"success": False, "error": str(err)}

    async def search_event(call: ServiceCall) -> ServiceResponse:
        """Search for calendar events in a date range."""
        try:
            validated_data = SEARCH_EVENTS_SCHEMA(dict(call.data))
            start_dt = validated_data["date_start"].astimezone(timezone)
            end_dt   = validated_data["date_end"].astimezone(timezone)

            def get_events():
                return list(account.calendar.view(start=start_dt, end=end_dt))

            events     = await hass.async_add_executor_job(get_events)
            event_list = [
                {
                    "subject":  e.subject,
                    "start":    e.start.isoformat(),
                    "end":      e.end.isoformat(),
                    "location": e.location,
                    "body":     e.body,
                    "id":       e.id,
                }
                for e in events
            ]
            _LOGGER.info("Found %d events", len(event_list))
            return {"success": True, "events": event_list, "count": len(event_list)}

        except vol.Invalid as err:
            _LOGGER.error("Invalid input for search_event: %s", err)
            return {"success": False, "error": str(err)}
        except Exception as err:
            _LOGGER.error("Failed to search events: %s", err)
            return {"success": False, "error": str(err)}

    async def edit_event(call: ServiceCall) -> ServiceResponse:
        """Find a calendar event by subject and edit only the fields provided."""
        try:
            validated_data = EDIT_EVENT_SCHEMA(dict(call.data))
            search_subject = validated_data["subject"]

            now          = datetime.now(tz=timezone)
            search_start = validated_data.get("search_start", now - timedelta(days=365))
            search_end   = validated_data.get("search_end",   now + timedelta(days=365))

            if search_start.tzinfo is None:
                search_start = search_start.replace(tzinfo=timezone)
            else:
                search_start = search_start.astimezone(timezone)

            if search_end.tzinfo is None:
                search_end = search_end.replace(tzinfo=timezone)
            else:
                search_end = search_end.astimezone(timezone)

            def find_and_edit():
                events  = list(account.calendar.view(start=search_start, end=search_end))
                matches = [e for e in events if e.subject and search_subject.lower() in e.subject.lower()]

                if not matches:
                    return False, f"No event found matching subject: '{search_subject}'", None
                if len(matches) > 1:
                    return False, f"Multiple events matched '{search_subject}': {[e.subject for e in matches]}. Use a more specific subject.", None

                event            = matches[0]
                original_subject = event.subject
                changed_fields   = []

                if "new_subject" in validated_data:
                    event.subject = validated_data["new_subject"]
                    changed_fields.append("subject")
                if "new_date_start" in validated_data:
                    event.start = validated_data["new_date_start"].astimezone(timezone)
                    changed_fields.append("start")
                if "new_date_end" in validated_data:
                    event.end = validated_data["new_date_end"].astimezone(timezone)
                    changed_fields.append("end")
                if "new_location" in validated_data:
                    event.location = validated_data["new_location"]
                    changed_fields.append("location")
                if "new_body" in validated_data:
                    event.body = validated_data["new_body"]
                    changed_fields.append("body")

                if not changed_fields:
                    return False, "No new values provided — nothing to update.", None

                event.save(update_fields=changed_fields)
                return True, None, original_subject

            success, error, original_subject = await hass.async_add_executor_job(find_and_edit)

            if not success:
                _LOGGER.error("edit_event failed: %s", error)
                return {"success": False, "error": error}

            _LOGGER.info("Edited event: %s", original_subject)
            return {"success": True, "edited_subject": original_subject}

        except vol.Invalid as err:
            _LOGGER.error("Invalid input for edit_event: %s", err)
            return {"success": False, "error": str(err)}
        except Exception as err:
            _LOGGER.error("Failed to edit event: %s", err)
            return {"success": False, "error": str(err)}

    if not hass.services.has_service(DOMAIN, SERVICE_CREATE_EVENT):
        hass.services.async_register(DOMAIN, SERVICE_CREATE_EVENT, create_event, schema=CREATE_EVENT_SCHEMA, supports_response=SupportsResponse.ONLY)
    if not hass.services.has_service(DOMAIN, SERVICE_DELETE_EVENT):
        hass.services.async_register(DOMAIN, SERVICE_DELETE_EVENT, delete_event)
    if not hass.services.has_service(DOMAIN, SERVICE_SEARCH_EVENT):
        hass.services.async_register(DOMAIN, SERVICE_SEARCH_EVENT, search_event, schema=SEARCH_EVENTS_SCHEMA, supports_response=SupportsResponse.ONLY)
    if not hass.services.has_service(DOMAIN, SERVICE_EDIT_EVENT):
        hass.services.async_register(DOMAIN, SERVICE_EDIT_EVENT, edit_event, schema=EDIT_EVENT_SCHEMA, supports_response=SupportsResponse.ONLY)
