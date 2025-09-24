import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_N8N_URL,
    CONF_MQTT_HOST,
    CONF_MQTT_USERNAME,
    CONF_MQTT_PASSWORD,
    CONF_CONTEXT_WINDOW,
    CONF_MAX_HISTORY,
    CONF_KEEP_ALIVE,
    CONF_ALLOW_THINKING,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_CONTEXT_WINDOW = 5
DEFAULT_MAX_HISTORY = 10
DEFAULT_KEEP_ALIVE = 60
DEFAULT_ALLOW_THINKING = False


class MqttN8nAgentConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MQTT N8N Agent."""

    VERSION = 2

    def __init__(self):
        self._n8n_url = None
        self._mqtt_host = None
        self._mqtt_username = None
        self._mqtt_password = None
        self._model = None

    async def async_step_user(self, user_input=None):
        """Step 1: Ask for N8N URL and MQTT connection details."""

        errors = {}

        if user_input is not None:
            self._n8n_url = user_input[CONF_N8N_URL]
            self._mqtt_host = user_input[CONF_MQTT_HOST]
            self._mqtt_username = user_input.get(CONF_MQTT_USERNAME)
            self._mqtt_password = user_input.get(CONF_MQTT_PASSWORD)

            # Run both checks in executor to avoid blocking
            try:
                model = await self.hass.async_add_executor_job(
                    self._fetch_model_from_n8n_blocking, self._n8n_url
                )
            except Exception as err:
                _LOGGER.error("Failed to fetch model from N8N: %s", err)
                errors["base"] = "n8n_connection_failed"
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._get_user_data_schema(),
                    errors=errors,
                )

            try:
                await self.hass.async_add_executor_job(
                    self._test_mqtt_connection_blocking,
                    self._mqtt_host,
                    self._mqtt_username,
                    self._mqtt_password,
                )
            except Exception as err:
                _LOGGER.error("Failed to connect to MQTT broker: %s", err)
                errors["base"] = "mqtt_connection_failed"
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._get_user_data_schema(),
                    errors=errors,
                )

            self._model = model

            return await self.async_step_options()

        return self.async_show_form(
            step_id="user", data_schema=self._get_user_data_schema()
        )

    async def async_step_options(self, user_input=None):
        """Step 2: Configure agent options."""

        errors = {}

        if user_input is not None:
            if user_input[CONF_KEEP_ALIVE] <= 0:
                errors["keep_alive"] = "invalid_keep_alive"

            if not errors:
                data = {
                    CONF_N8N_URL: self._n8n_url,
                    CONF_MQTT_HOST: self._mqtt_host,
                    CONF_MQTT_USERNAME: self._mqtt_username,
                    CONF_MQTT_PASSWORD: self._mqtt_password,
                    "model": self._model,
                    "instructions": user_input.get("instructions", ""),
                    CONF_CONTEXT_WINDOW: user_input[CONF_CONTEXT_WINDOW],
                    CONF_MAX_HISTORY: user_input[CONF_MAX_HISTORY],
                    CONF_KEEP_ALIVE: user_input[CONF_KEEP_ALIVE],
                    CONF_ALLOW_THINKING: user_input[CONF_ALLOW_THINKING],
                }
                return self.async_create_entry(title="MQTT N8N Agent", data=data)

        defaults = {
            CONF_CONTEXT_WINDOW: DEFAULT_CONTEXT_WINDOW,
            CONF_MAX_HISTORY: DEFAULT_MAX_HISTORY,
            CONF_KEEP_ALIVE: DEFAULT_KEEP_ALIVE,
            CONF_ALLOW_THINKING: DEFAULT_ALLOW_THINKING,
        }

        data_schema = vol.Schema(
            {
                vol.Required("model", default=self._model): str,
                vol.Required("instructions", default="You are a voice assistant for Home Assistant."): str,
                vol.Required(CONF_CONTEXT_WINDOW, default=defaults[CONF_CONTEXT_WINDOW]): int,
                vol.Required(CONF_MAX_HISTORY, default=defaults[CONF_MAX_HISTORY]): int,
                vol.Required(CONF_KEEP_ALIVE, default=defaults[CONF_KEEP_ALIVE]): int,
                vol.Required(CONF_ALLOW_THINKING, default=defaults[CONF_ALLOW_THINKING]): bool,
            }
        )

        return self.async_show_form(
            step_id="options",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"model": self._model or "unknown"},
        )

    def _get_user_data_schema(self):
        return vol.Schema(
            {
                vol.Required(CONF_N8N_URL): str,
                vol.Required(CONF_MQTT_HOST): str,
                vol.Optional(CONF_MQTT_USERNAME): str,
                vol.Optional(CONF_MQTT_PASSWORD): str,
            }
        )

    def _fetch_model_from_n8n_blocking(self, n8n_url: str) -> str:
        """Blocking method to fetch model name from N8N."""
        import requests  # safe in executor
        try:
            resp = requests.get(f"{n8n_url.rstrip('/')}/api/model", timeout=5)
            resp.raise_for_status()
            data = resp.json()
            model = data.get("model")
            if not model:
                raise ValueError("No model found in response")
            return model
        except Exception as e:
            raise e

    def _test_mqtt_connection_blocking(self, host, username=None, password=None):
        """Blocking test MQTT connection using asyncio-mqtt, run in executor."""
        import asyncio
        from asyncio_mqtt import Client as MQTTClient
        import asyncio_mqtt

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def connect_test():
            async with MQTTClient(hostname=host, username=username, password=password):
                pass

        try:
            loop.run_until_complete(connect_test())
        finally:
            loop.close()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return MqttN8nAgentOptionsFlow(config_entry)
