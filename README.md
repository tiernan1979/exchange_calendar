# Home Assistant Exchange Calendar
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)
This custom component for Home Assistant allows you to create/delete and search exchange calendar events.

## Home Assistant Integration
**1.** (Manual) Copy the exchange_calendar folder to your Home Assistant's custom_components directory. If you don't have a custom_components directory, create one in the same directory as your configuration.yaml file.

(HACS) Add this repository to HACS. https://github.com/tiernan1979/exchange_calendar/

**2.** Restart Home Assistant.

## Usage
3 actions are created for this integration.

exchange_calendar.create_event - Create a Calendar event in Exchange
```yaml
action: exchange_calendar.create_event
data:
  date_start: "2025-05-14 00:00:00"
  date_end: "2025-05-14 00:00:00"
  location: test
  body: test
  subject: test
```

exchange_calendar.delete_event - Delete a Calendar event via event ID
```yaml
action: exchange_calendar.delete_event
data:
  event_id: 14908askdj39487y98y49w75q2[o5yP35Yw9q%[q356
```

exchange_calendar.search_event - Search for events in a date period and respond with information
```yaml
action: exchange_calendar.search_event
data:
  date_start: "2025-05-14 00:00:00"
  date_end: "2025-05-16 00:00:00"
```
