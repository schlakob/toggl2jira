"""
Toggl API client and related functionality.
"""

import math
import re
from datetime import date

import requests


class TogglApi:
    """
    Low level API client for Toggl.
    """

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = f"{base_url}/api/v9"
        self.auth = (api_key, "api_token")

    def get_me(self) -> dict:
        """
        Get information about the authenticated user.
        """

        return requests.get(f"{self.base_url}/me", auth=self.auth, timeout=10).json()

    def get_time_entries(self, start_date: date, end_date: date) -> list:
        """
        Get time entries for the authenticated user within a date range.
        """

        return requests.get(
            f"{self.base_url}/me/time_entries",
            auth=self.auth,
            params={"start_date": start_date, "end_date": end_date},
            timeout=10,
        ).json()


class Toggl:
    """
    High level client for Toggl.
    """

    def __init__(self, toggl_api: TogglApi, jira_project_slug: str) -> None:
        self.toggl_api = toggl_api
        self.time_entry_description_pattern = re.compile(
            rf"^(?P<key>{jira_project_slug}-\d+)\/(?P<comment>.*)$"
        )

    def get_user(self) -> dict:
        """
        Get information about the authenticated user.
        """

        return self.toggl_api.get_me()

    def get_time_entries(self, start_date: date, end_date: date) -> list:
        """
        Get time entries for the authenticated user within a date range.
        """

        return self.toggl_api.get_time_entries(start_date, end_date)

    def convert_time_entry_to_worklog(self, time_entry: dict) -> dict:
        """
        Convert a toggl time entry to a jira worklog.
        """

        description_match = self.time_entry_description_pattern.match(
            time_entry["description"]
        )
        comment_suffix = (
            f"\n\n[toggl-track-sync]te-id={time_entry['id']}[/toggl-track-sync]"
        )
        return {
            "issueKey": description_match.group("key") if description_match else None,
            "started": time_entry["start"].split("+")[0] + ".000+0000",
            "timeSpentSeconds": time_entry["duration"] - time_entry["duration"] % 60,
            "comment": (
                description_match.group("comment") + comment_suffix
                if description_match
                else time_entry["description"]
            ),
        }

    def worklog_filter(self, worklog: dict) -> bool:
        """
        Filter function to determine if a worklog should be synced.
        """

        return (
            worklog["issueKey"] is not None
            and math.floor(worklog["timeSpentSeconds"] / 60) > 0
        )
