import requests
from datetime import date
import re
import math


class TogglApi:
    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = f"{base_url}/api/v9"
        self.auth = (api_key, "api_token")

    def get_me(self) -> dict:
        return requests.get(f"{self.base_url}/me", auth=self.auth).json()

    def get_time_entries(self, start_date: date, end_date: date) -> list:
        return requests.get(
            f"{self.base_url}/me/time_entries",
            auth=self.auth,
            params={"start_date": start_date, "end_date": end_date},
        ).json()


class Toggl:
    def __init__(self, toggl_api: TogglApi, jira_project_slug: str) -> None:
        self.toggl_api = toggl_api
        self.time_entry_description_pattern = re.compile(
            rf"^(?P<key>{jira_project_slug}-\d+)\/(?P<comment>.*)$"
        )

    def get_user(self) -> dict:
        return self.toggl_api.get_me()

    def get_time_entries(self, start_date: date, end_date: date) -> list:
        return self.toggl_api.get_time_entries(start_date, end_date)

    def convert_time_entry_to_worklog(self, time_entry: dict) -> dict:
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
        return (
            worklog["issueKey"] is not None
            and math.floor(worklog["timeSpentSeconds"] / 60) > 0
        )
