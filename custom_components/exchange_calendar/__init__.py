"""Home Assistant integration for Exchange calendar events."""
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform

DOMAIN = "exchange_calendar"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Exchange Calendar from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    # Forward setup to the calendar platform
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.CALENDAR])

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    await hass.config_entries.async_unload_platforms(entry, [Platform.CALENDAR])
    hass.data[DOMAIN].pop(entry.entry_id)
    return True
