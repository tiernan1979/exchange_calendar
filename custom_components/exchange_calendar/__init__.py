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
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
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
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CALENDAR]

# Define schema for create_event service
CREATE_EVENT_SCHEMA = vol.Schema(
    {
        vol.Required("subject", default="New Event"): cv.string,
        vol.Required("date_start"): cv.datetime,
        vol.Required("date_end"): cv.datetime,
        vol.Optional("location"): cv.string,
        vol.Optional("body"): cv.string,
    }
)

# Define schema for search_events service
SEARCH_EVENTS_SCHEMA = vol.Schema(
    {
        vol.Required("date_start"): cv.datetime,
        vol.Required("date_end"): cv.datetime,
    }
)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Exchange Calendar from a config entry."""
    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]
    server = entry.data[CONF_SERVER]
    timezone = entry.data[CONF_TIMEZONE]
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
        if "SSLError" in str(err):
            _LOGGER.error(
                "1 SSL certificate verification failed for %s. Fix the server's SSL certificate: %s",
                server,
                err,
            )
        else:
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
    account = hass.data[DOMAIN][entry.entry_id]["account"]
    timezone = hass.data[DOMAIN][entry.entry_id]["timezone"]

    async def create_event(call: ServiceCall) -> ServiceResponse:
        """Create a new calendar event."""
        try:
            # Create a mutable copy of call.data
            data = dict(call.data)

            # Validate input using the schema
            validated_data = CREATE_EVENT_SCHEMA(data)
            subject = validated_data["subject"]
            start_dt = validated_data["date_start"].astimezone(timezone)
            end_dt = validated_data["date_end"].astimezone(timezone)
            location = validated_data.get("location")
            body = validated_data.get("body")

        # Offload all exchangelib operations to a thread executor
            def create_and_save_event():
                try:
                    # Access the calendar folder and create the event in a thread-safe manner
                    calendar_folder = account.calendar  # This is the line causing the issue
                    event = CalendarItem(
                        account=account,
                        folder=calendar_folder,
                        subject=subject,
                        start=start_dt,
                        end=end_dt,
                        location=location,
                        body=body,
                    )
                    event.save()
                    return True, None, subject
                except Exception as e:
                    return False, str(e), None

            # Run the blocking operations in a thread executor
            success, error, saved_subject = await hass.async_add_executor_job(create_and_save_event)

            if not success:
                _LOGGER.error("Failed to create or save event: %s", error)
                return {
                    "entry_id": entry.entry_id,
                    "error": f"Failed to create or save event: {error}",
                    "success": False,
                }

            _LOGGER.info("Created event: %s", saved_subject)
            return {
                "success": True
            }

        except vol.Invalid as err:
            _LOGGER.error("Invalid input for create event: %s", err)
            return {
                "entry_id": entry.entry_id,
                "error": f"Invalid input for create event: {str(err)}",
                "success": False,
            }
        except Exception as err:
            _LOGGER.error("Failed to create event: %s", err)
            return {
                "entry_id": entry.entry_id,
                "error": f"Failed to create event: {str(err)}",
                "success": False,
            }

    async def delete_event(call: ServiceCall) -> ServiceResponse:
        """Delete a calendar event by ID."""
        event_id = call.data.get("event_id")
        try:
            # Fetch the event by item_id using exchangelib
            event = await hass.async_add_executor_job(
                lambda: account.calendar.get(id=event_id)
            )

            if not event:
                raise ValueError(f"No event found with ID: {event_id}")

            # Delete the event
            await hass.async_add_executor_job(event.delete)
            _LOGGER.info("Deleted event: %s", event_id)
            response = {
                "entry_id": entry.entry_id,
                "success": True,
            }
            return response
        except Exception as err:
            _LOGGER.error("Failed to delete event: %s", err)
            response = {
                "entry_id": entry.entry_id ,
                "error": f"Failed to delete event: {str(err)}",
                "success": False,
            }
            return response

    async def search_event(call: ServiceCall) -> ServiceResponse:
        """Search for calendar events in a date range."""
        try:
            # Create a mutable copy of call.data
            data = dict(call.data)

            # Validate input using the schema
            validated_data = SEARCH_EVENTS_SCHEMA(data)
            start_dt = validated_data["date_start"].astimezone(timezone)
            end_dt = validated_data["date_end"].astimezone(timezone)

            def get_events():
                return list(account.calendar.view(start=start_dt, end=end_dt))

            events = await hass.async_add_executor_job(get_events)

            event_list = [
                {
                    "subject": event.subject,
                    "start": event.start.isoformat(),
                    "end": event.end.isoformat(),
                    "location": event.location,
                    "body": event.body,
                    "id": event.id,
                }
                for event in events
            ]
            _LOGGER.info("Found %d events", len(event_list))

            # Respond to the service call with the results
            response = {
                "entry_id": entry.entry_id,
                "events": event_list,
                "count": len(event_list),
                "success": True,
            }
            return response
        except vol.Invalid as err:
            _LOGGER.error("Invalid input for search events: %s", err)
            response = {
                "entry_id": entry.entry_id,
                "error": f"Invalid input: {str(err)}",
                "success": False,
            }
            return response
        except Exception as err:
            _LOGGER.error("Failed to search events: %s", err)
            response = {
                "entry_id": entry.entry_id,
                "error": f"Failed to search events: {str(err)}",
                "success": False,
            }
            return response

    hass.services.async_register(DOMAIN, SERVICE_CREATE_EVENT, create_event, schema=CREATE_EVENT_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DELETE_EVENT, delete_event)
    hass.services.async_register(DOMAIN, SERVICE_SEARCH_EVENT, search_event, schema=SEARCH_EVENTS_SCHEMA, supports_response=SupportsResponse.ONLY)
