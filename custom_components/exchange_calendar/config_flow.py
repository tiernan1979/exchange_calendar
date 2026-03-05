import logging
import voluptuous as vol
from exchangelib import Account, Credentials, Configuration, DELEGATE
from homeassistant import config_entries
from homeassistant.core import callback
import pytz

from .const import (
    DOMAIN,
    CONF_SERVER,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_TIMEZONE,
    CONF_AUTH_TYPE,
    AUTH_TYPES,
)

_LOGGER = logging.getLogger(__name__)


class ExchangeCalendarConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Exchange Calendar."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            try:
                credentials = Credentials(
                    username=user_input[CONF_EMAIL],
                    password=user_input[CONF_PASSWORD],
                )
                config = Configuration(
                    server=user_input[CONF_SERVER],
                    credentials=credentials,
                    auth_type=user_input[CONF_AUTH_TYPE],
                )
                await self.hass.async_add_executor_job(
                    lambda: Account(
                        primary_smtp_address=user_input[CONF_EMAIL],
                        config=config,
                        autodiscover=False,
                        access_type=DELEGATE,
                    )
                )
                return self.async_create_entry(
                    title=user_input[CONF_EMAIL],
                    data=user_input,
                )
            except Exception as err:
                if "SSLError" in str(err):
                    errors["base"] = "ssl_error"
                    _LOGGER.error("SSL certificate verification failed for %s: %s", user_input[CONF_SERVER], err)
                elif "Unauth" in str(err):
                    errors["base"] = "unauthorized"
                    _LOGGER.error("Authentication failed for %s: %s", user_input[CONF_SERVER], err)
                else:
                    errors["base"] = "cannot_connect"
                    _LOGGER.error("Connection failed for %s: %s", user_input[CONF_SERVER], err)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Required(CONF_SERVER): str,
                    vol.Required(CONF_TIMEZONE, default="UTC"): vol.In(pytz.all_timezones),
                    vol.Required(CONF_AUTH_TYPE, default="NTLM"): vol.In(AUTH_TYPES),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow - DO NOT pass config_entry to constructor."""
        return ExchangeCalendarOptionsFlow()


class ExchangeCalendarOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Exchange Calendar."""

    # NO __init__ that accepts config_entry - HA 2024.x+ injects self.config_entry automatically.
    # Defining __init__(self, config_entry) here causes the 500 error.

    async def async_step_init(self, user_input=None):
        """Handle options form."""
        errors = {}

        if user_input is not None:
            if not user_input.get(CONF_PASSWORD):
                errors[CONF_PASSWORD] = "password_empty"
            if user_input.get(CONF_TIMEZONE) not in pytz.all_timezones:
                errors[CONF_TIMEZONE] = "invalid_timezone"

            if not errors:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_TIMEZONE: user_input[CONF_TIMEZONE],
                    },
                )

        # Read current values - options take priority over original data
        current_password = (
            self.config_entry.options.get(CONF_PASSWORD)
            or self.config_entry.data.get(CONF_PASSWORD, "")
        )
        current_timezone = (
            self.config_entry.options.get(CONF_TIMEZONE)
            or self.config_entry.data.get(CONF_TIMEZONE, "UTC")
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD, default=current_password): str,
                    vol.Required(CONF_TIMEZONE, default=current_timezone): vol.In(pytz.all_timezones),
                }
            ),
            errors=errors,
        )
