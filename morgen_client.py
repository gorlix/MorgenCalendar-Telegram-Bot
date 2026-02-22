import logging
import httpx
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class MorgenClient:
    """
    An asynchronous client for interacting with the Morgen API.

    Handles authentication, calendar listing, and event operations (creating,
    listing). Relies on `httpx.AsyncClient` for non-blocking network requests.
    """
    
    BASE_URL = "https://api.morgen.so/v3"

    def __init__(self) -> None:
        """
        Initialize the MorgenClient.
        """
        self.client: httpx.AsyncClient = httpx.AsyncClient(timeout=10.0)

    def _auth_headers(self, api_key: str) -> Dict[str, str]:
        """
        Generate the required authorization headers.

        Args:
            api_key (str): The user's Morgen API key.

        Returns:
            Dict[str, str]: Headers including 'accept' and 'Authorization'.
        """
        return {
            "accept": "application/json",
            "Authorization": f"ApiKey {api_key}"
        }

    async def list_calendars(self, api_key: str) -> List[Dict[str, Any]]:
        """
        Fetch all calendars associated with the user's Morgen account.

        Args:
            api_key (str): The user's Morgen API key.

        Returns:
            List[Dict[str, Any]]: A list of calendar dictionary objects.
            Raises httpx.HTTPError on failed requests.
        """
        url = f"{self.BASE_URL}/calendars/list"
        response = await self.client.get(url, headers=self._auth_headers(api_key))
        response.raise_for_status()
        data = response.json()
        return data.get("data", {}).get("calendars", [])

    async def get_primary_calendar(self, api_key: str) -> Optional[Dict[str, Any]]:
        """
        Identify the first writable calendar to use as the default/primary calendar.

        Args:
            api_key (str): The user's Morgen API key.

        Returns:
            Optional[Dict[str, Any]]: The primary calendar object if found, else None.
        """
        try:
            calendars = await self.list_calendars(api_key)
            # Find a calendar where we can create items
            for cal in calendars:
                my_rights = cal.get("myRights", {})
                if my_rights.get("mayWriteItems", True) or my_rights.get("mayWriteAll", True):
                    return cal
            return calendars[0] if calendars else None
        except Exception as e:
            logger.error(f"Error fetching primary calendar: {e}")
            return None

    async def create_event(
        self,
        api_key: str,
        account_id: str,
        calendar_id: str,
        title: str,
        start_datetime_iso: str,
        duration_iso: str,
        timezone: str = "UTC"
    ) -> Dict[str, Any]:
        """
        Create a new calendar event.

        Args:
            api_key (str): The user's Morgen API key.
            account_id (str): The Morgen account ID where the calendar lives.
            calendar_id (str): The specific calendar ID.
            title (str): The title of the event.
            start_datetime_iso (str): Event start time, e.g. "2023-03-01T10:15:00".
            duration_iso (str): Duration in ISO format, e.g. "PT30M" for 30 mins.
            timezone (str): the associated timezone. Defaults to "UTC".

        Returns:
            Dict[str, Any]: The JSON response from the API.
        """
        url = f"{self.BASE_URL}/events/create"
        payload = {
            "accountId": account_id,
            "calendarId": calendar_id,
            "title": title,
            "start": start_datetime_iso,
            "duration": duration_iso,
            "timeZone": timezone,
            "showWithoutTime": False
        }
        response = await self.client.post(
            url,
            headers=self._auth_headers(api_key),
            json=payload
        )
        response.raise_for_status()
        return response.json()

    async def list_events(
        self,
        api_key: str,
        account_id: str,
        calendar_ids: List[str],
        start_datetime: str,
        end_datetime: str
    ) -> List[Dict[str, Any]]:
        """
        Retrieve events for a specified time window.

        Args:
            api_key (str): The user's Morgen API key.
            account_id (str): The Morgen account ID.
            calendar_ids (List[str]): List of calendar IDs to fetch events from.
            start_datetime (str): Datetime string with timezone (e.g. "2023-03-01T00:00:00Z").
            end_datetime (str): Datetime string with timezone (e.g. "2023-03-02T00:00:00Z").

        Returns:
            List[Dict[str, Any]]: A list of event dictionary objects.
        """
        url = f"{self.BASE_URL}/events/list"
        cal_ids_str = ",".join(calendar_ids)
        params = {
            "accountId": account_id,
            "calendarIds": cal_ids_str,
            "start": start_datetime,
            "end": end_datetime
        }
        response = await self.client.get(
            url,
            headers=self._auth_headers(api_key),
            params=params
        )
        response.raise_for_status()
        data = response.json()
        return data.get("data", {}).get("events", [])

    async def close(self) -> None:
        """
        Close the underlying httpx client.
        """
        await self.client.aclose()
