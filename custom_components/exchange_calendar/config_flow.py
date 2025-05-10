"""Config flow for Exchange Calendar."""
from homeassistant import config_entries
from homeassistant.core import callback
import voluptuous as vol
from exchangelib import Credentials, Configuration, Account, DELEGATE
from zoneinfo import ZoneInfo, available_timezones

class ExchangeCalendarConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Exchange Calendar."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            try:
                # Validate Exchange connection
                credentials = Credentials(
                    username=user_input["username"],
                    password=user_input["password"],
                )
                config = Configuration(
                    server=user_input["server"],
                    credentials=credentials,
                )
                account = Account(
                    primary_smtp_address=user_input["username"],
                    config=config,
                    autodiscover=False,
                    access_type=DELEGATE,
                )
                # Verify calendar access
                account.calendar.all().count()
                # Validate timezone
                if user_input["timezone"] not in available_timezones():
                    errors["timezone"] = "invalid_timezone"
                else:
                    return self.async_create_entry(
                        title=user_input["calendar_name"],
                        data=user_input,
                    )
            except Exception:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("calendar_name", default="Exchange Calendar"): str,
                    vol.Required("server", default="outlook.office365.com"): str,
                    vol.Required("username"): str,
                    vol.Required("password"): str,
                    vol.Required("timezone", default="UTC"): str,
                }
            ),
            errors=errors,
        )
