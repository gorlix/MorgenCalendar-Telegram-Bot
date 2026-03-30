import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    pass


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
        # Force IPv4 to avoid common network issues with dual-stack on some hosts
        transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
        self.client: httpx.AsyncClient = httpx.AsyncClient(
            timeout=15.0, transport=transport
        )

    def _auth_headers(self, api_key: str) -> dict[str, str]:
        """
        Generate the required authorization headers.

        Args:
            api_key (str): The user's Morgen API key.

        Returns:
            Dict[str, str]: Headers including 'accept' and 'Authorization'.
        """
        return {"accept": "application/json", "Authorization": f"ApiKey {api_key}"}

    async def list_calendars(self, api_key: str) -> list[dict[str, Any]]:
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

    async def get_primary_calendar(
        self, api_key: str, preferred_calendar_id: str | None = None
    ) -> dict[str, Any] | None:
        """
        Identify the primary calendar to use.
        If a preferred_calendar_id is given and it is writable, it returns it.
        Otherwise, returns the first writable calendar as fallback.

        Args:
            api_key (str): The user's Morgen API key.
            preferred_calendar_id (Optional[str]): A calendar ID the user prefers.

        Returns:
            Optional[Dict[str, Any]]: The primary calendar object if found, else None.
        """
        try:
            calendars = await self.list_calendars(api_key)

            # First, check if the preferred calendar is valid and writable
            if preferred_calendar_id:
                for cal in calendars:
                    if cal.get("id") == preferred_calendar_id:
                        my_rights = cal.get("myRights", {})
                        if my_rights.get("mayWriteItems", True) or my_rights.get(
                            "mayWriteAll", True
                        ):
                            return cal

            # Fallback: Find a calendar where we can create items
            for cal in calendars:
                my_rights = cal.get("myRights", {})
                if my_rights.get("mayWriteItems", True) or my_rights.get(
                    "mayWriteAll", True
                ):
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
        timezone: str = "UTC",
    ) -> dict[str, Any]:
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
            "showWithoutTime": False,
        }
        logger.debug(f"CREATE EVENT PAYLOAD: {payload}")

        response = await self.client.post(
            url, headers=self._auth_headers(api_key), json=payload
        )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"MORGEN API REJECTED REQUEST (400) - Response Body: {e.response.text}"
            )
            raise

        return response.json()

    async def list_events(
        self,
        api_key: str,
        account_id: str,
        calendar_ids: list[str],
        start_datetime: str,
        end_datetime: str,
    ) -> httpx.Response:
        """
        Retrieve events for a specified time window from multiple calendars.

        Args:
            api_key (str): The user's Morgen API key.
            account_id (str): The Morgen account ID.
            calendar_ids (List[str]): List of calendar IDs to fetch events from.
            start_datetime (str): Datetime string with timezone (e.g. "2023-03-01T00:00:00Z").
            end_datetime (str): Datetime string with timezone (e.g. "2023-03-02T00:00:00Z").

        Returns:
            httpx.Response: The raw httpx response object so caller can read headers.
        """
        url = f"{self.BASE_URL}/events/list"

        # Use a list of tuples to pass multiple identical parameters to httpx correctly
        params = [
            ("accountId", account_id),
            ("start", start_datetime),
            ("end", end_datetime),
        ]
        for cid in calendar_ids:
            params.append(("calendarIds", cid))

        response = await self.client.get(
            url, headers=self._auth_headers(api_key), params=params
        )
        response.raise_for_status()
        return response

    async def get_all_events(
        self, api_key: str, start_datetime: str, end_datetime: str
    ) -> list[dict[str, Any]]:
        """
        Fetch events in batches from ALL calendars available on the user's Morgen
        account, regardless of their visibility state in the Morgen UI.

        Design note — intentional fetch-all behaviour:
            Morgen calendar objects carry a ``selected`` boolean that reflects
            whether the calendar is currently visible/active inside the Morgen
            desktop/mobile app.  A previous iteration of this method skipped
            calendars where ``selected is False``, which caused events from
            secondary or hidden calendars (e.g. a medical appointment calendar
            that a user had toggled off in the UI) to be silently dropped from
            the daily summary without any error or warning.

            Because this bot is a background notification service, it must
            present a *complete* picture of the user's schedule.  A calendar
            that is hidden in the Morgen app UI is not necessarily unimportant
            — the user may simply prefer a cleaner visual in the app while
            still needing to be reminded of its events.  Silently omitting
            those events would constitute data loss from the bot's perspective.

            The ``selected`` field is therefore intentionally disregarded here.
            If calendar exclusion is needed in the future, it should be
            implemented via an explicit bot-side configuration (see TODO below).

        Pagination & rate-limit strategy:
            Calendars are grouped by ``accountId`` and further split into
            batches of up to 5 IDs per API request to stay within Morgen\'s
            URL-length and rate-limit constraints.  A 0.5-second sleep is
            inserted between batches.  On a 429 response the error is surfaced
            as a :class:`RateLimitError` so callers can notify the user.

        Args:
            api_key (str): The user's Morgen API key.
            start_datetime (str): ISO-8601 datetime with UTC offset
                (e.g. ``"2023-03-01T00:00:00Z"``).  Defines the inclusive
                start of the query window.
            end_datetime (str): ISO-8601 datetime with UTC offset
                (e.g. ``"2023-03-02T00:00:00Z"``).  Defines the exclusive
                end of the query window.

        Returns:
            List[Dict[str, Any]]: A flattened list of event dictionaries,
            sorted chronologically by ``start``.  Each entry is augmented
            with a ``calendar_name`` key derived from the calendar list.
            Events with no title, a blank title, or the literal title
            ``"Busy"`` are filtered out before returning.

        Raises:
            RateLimitError: If the Morgen API returns HTTP 429 (rate limited).
        """
        try:
            calendars = await self.list_calendars(api_key)
            if not calendars:
                return []

            # Group calendars by accountId, though typically it's just one account
            account_map = {}
            cal_map = {}
            for cal in calendars:
                # TODO: Implement a proper calendar exclusion feature based on a
                # bot-level configuration (e.g. a per-user blacklist of specific
                # calendar IDs stored in the database) rather than relying on the
                # Morgen API "selected" UI-visibility flag.  Filtering on
                # `selected` caused silent data loss: events from calendars
                # hidden in the Morgen app were dropped with no error or log
                # message, making important appointments (e.g. medical) disappear
                # from the daily summary.  See: fix/missing-events-selected-guard.

                cal_id = cal.get("id")
                if "name" in cal:
                    cal_map[cal_id] = cal["name"]
                else:
                    cal_map[cal_id] = "Unknown Calendar"

                acc_id = cal.get("accountId")
                if acc_id and cal_id:
                    if acc_id not in account_map:
                        account_map[acc_id] = []
                    account_map[acc_id].append(cal_id)

            all_events = []

            # Process batches for each account
            for account_id, cal_ids in account_map.items():
                # Define batch size
                batch_size = 5
                batches = [
                    cal_ids[i : i + batch_size]  # noqa: E203
                    for i in range(0, len(cal_ids), batch_size)
                ]

                for batch in batches:
                    try:
                        response = await self.list_events(
                            api_key=api_key,
                            account_id=account_id,
                            calendar_ids=batch,
                            start_datetime=start_datetime,
                            end_datetime=end_datetime,
                        )

                        # Log rate limits
                        rem = response.headers.get("RateLimit-Remaining")
                        if rem:
                            logger.info(f"Morgen API Points Remaining: {rem}")

                        data = response.json()
                        response_events = data.get("data", {}).get("events", [])

                        for ev in response_events:
                            title = ev.get("title") or ""
                            if (
                                not title
                                or not title.strip()
                                or title.strip() == "Busy"
                            ):
                                continue
                            ev["calendar_name"] = cal_map.get(
                                ev.get("calendarId"), "Unknown Calendar"
                            )
                            all_events.append(ev)

                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 429:
                            reset = e.response.headers.get(
                                "RateLimit-Reset"
                            ) or e.response.headers.get("Retry-After")
                            try:
                                reset_seconds = int(reset)
                            except (TypeError, ValueError):
                                reset_seconds = 900
                            raise RateLimitError(
                                f"API Limit Reached. Please wait {reset_seconds} seconds."
                            )
                        else:
                            logger.warning(f"Error fetching batch {batch}: {e}")
                    except Exception as e:
                        logger.warning(f"Error fetching batch {batch}: {e}")

                    # Sleep to respect rate limits between chunks
                    await asyncio.sleep(0.5)

            # Sort chronologically by start
            all_events.sort(key=lambda x: x.get("start", ""))
            return all_events

        except RateLimitError:
            raise
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                reset = e.response.headers.get(
                    "RateLimit-Reset"
                ) or e.response.headers.get("Retry-After")
                try:
                    reset_seconds = int(reset)
                except (TypeError, ValueError):
                    reset_seconds = 900
                raise RateLimitError(
                    f"API Limit Reached. Please wait {reset_seconds} seconds."
                )
            logger.error(f"HTTP error in get_all_events: {e}")
            return []
        except Exception as e:
            logger.error(f"Error in get_all_events: {e}")
            return []

    async def close(self) -> None:
        """
        Close the underlying httpx client.
        """
        await self.client.aclose()
