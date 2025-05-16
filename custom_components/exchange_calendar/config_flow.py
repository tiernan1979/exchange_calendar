import datetime
import logging
import voluptuous as vol
from exchangelib import Account, Credentials, Configuration, DELEGATE, CalendarItem
from homeassistant import config_entries
from homeassistant.core import callback
from exchangelib.protocol import BaseProtocol, NoVerifyHTTPAdapter
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
                    errors["base"] = f"SSL Error"
                    _LOGGER.error(
                        "SSL certificate verification failed for %s. Fix the server's SSL certificate: %s",
                        user_input[CONF_SERVER],
                        err,
                    )
                elif "Unauth" in str(err):
                    errors["base"] = f"Unauthorized"
                    _LOGGER.error(
                        "Authentication failed for %s. Error: %s",
                        user_input[CONF_SERVER],
                        err,
                    )
                else:
                    errors["base"] = f"Connection failed"
                    _LOGGER.error(
                        "Connection failed for %s: %s", user_input[CONF_SERVER], err
                    )


        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Required(CONF_SERVER): str,
                    vol.Required(CONF_TIMEZONE, default="UTC"): vol.In(
                        pytz.all_timezones
                    ),
                    vol.Required(CONF_AUTH_TYPE, default="NTLM"): vol.In(AUTH_TYPES),
                }
            ),
            errors=errors,
            description_placeholders={
                "ssl_error": "SSL certificate verification failed. Ensure the server's certificate is valid."
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ExchangeCalendarOptionsFlow(config_entry)

class ExchangeCalendarOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Exchange Calendar."""
    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry
        
    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                # Validate input explicitly if needed
                if not user_input[CONF_PASSWORD]:
                    errors["base"] = "Password cannot be empty"
                if user_input[CONF_TIMEZONE] not in pytz.all_timezones:
                    errors["base"] = "Invalid timezone"
                if not errors:
                    current_password = self.config_entry.options.get(CONF_PASSWORD, self.config_entry.data.get(CONF_PASSWORD))
                    current_timezone = (
                        self.config_entry.options.get(CONF_TIMEZONE) or
                        self.config_entry.data.get(CONF_TIMEZONE, "UTC")
                    )
                    if (
                        user_input[CONF_PASSWORD] != current_password or
                        user_input[CONF_TIMEZONE] != current_timezone
                    ):
                        return self.async_create_entry(
                            title="",
                            data={
                                CONF_PASSWORD: user_input[CONF_PASSWORD],
                                CONF_TIMEZONE: user_input[CONF_TIMEZONE],
                            }
                        )
                    return self.async_abort(reason="no_changes")
            except vol.Invalid:
                errors["base"] = "Invalid input provided"
        # Default timezone
        default_timezone = (
            self.config_entry.options.get(CONF_TIMEZONE) or
            self.config_entry.data.get(CONF_TIMEZONE, "UTC")
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PASSWORD,
                        default=self.config_entry.data.get(CONF_PASSWORD),
                    ): str,
                    vol.Required(
                        CONF_TIMEZONE,
                        default=default_timezone,
                    ): vol.In(pytz.all_timezones),
                }
            ),
            errors=errors,
        )

                   
